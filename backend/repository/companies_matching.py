"""Сведение разобранной из вакансии компании с уже заведённой."""

import logging
import re
from difflib import SequenceMatcher
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import Company

logger = logging.getLogger(__name__)


# Минимальная транслитерация русского кириллического алфавита в латиницу
# для дедупа имён вида «МТС» / «MTS». Ё → e (как в большинстве passport
# transliteration — для match'а это надёжнее, чем yo).
_CYR_TO_LAT = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e",
    "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m",
    "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "kh", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "shch",
    "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
}


def _translit_cyr_to_latin(s: str) -> str:
    return "".join(_CYR_TO_LAT.get(ch, ch) for ch in s.lower())


# Юр.формы вырезаются из имени до сравнения: «ПАО Сбербанк» → «sberbank».
# Регистр и кириллица — после lower() и transliterate.
_LEGAL_SUFFIX_RE = re.compile(
    r"\b(pao|oao|ao|zao|ooo|jsc|llc|ltd|inc|corp|gmbh|sa|ag|nv|bv|plc|sas)\b\.?"
)


_QUOTE_CHARS = set("«»\"'`“”„‚‘’")


def _normalize_company_name(s: str | None) -> str:
    """Нормализованная форма имени для deterministic match: lowercase +
    транслитерация + срезанные юр.суффиксы + сглаженные пробелы."""
    if not s:
        return ""
    s = "".join(ch for ch in s.strip() if ch not in _QUOTE_CHARS)
    s = _translit_cyr_to_latin(s)
    s = _LEGAL_SUFFIX_RE.sub(" ", s)
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return " ".join(s.split())


def _normalize_host(url: str | None) -> str:
    """Хост сайта без схемы / www. / порта / пути / query / fragment /
    завершающей точки. Пустая строка для None или невалидного URL.
    Полный host (а не registrable domain) — чтобы `pay.yandex.ru` ≠
    `yandex.ru` (subsidiary trap)."""
    if not url:
        return ""
    s = url.strip().lower()
    s = re.sub(r"^[a-z][a-z0-9+.\-]*://", "", s)
    s = s.lstrip("/")
    # Срезаем path / query / fragment ДО того, как лезть в port:
    # "sber.ru?utm=foo" без strip-а query превратился бы в host
    # "sber.ru?utm=foo" и сломал бы host-match.
    s = s.split("/", 1)[0]
    s = s.split("?", 1)[0]
    s = s.split("#", 1)[0]
    s = s.split(":", 1)[0]
    if s.startswith("www."):
        s = s[4:]
    # FQDN с завершающей точкой ("example.com.") — нормализуем к
    # "example.com", иначе host-match отказывает на пустяковом расхождении.
    s = s.rstrip(".")
    return s


# Хосты, которые НЕ являются «домашним сайтом компании»: агрегаторы
# вакансий, соцсети, мессенджеры, блог-платформы. Если parser ошибся и
# сунул в `company_website` ссылку на канал/профиль/пост, Stage 1c (host-
# match) мог бы склеить две разные компании по этому общему host'у. Для
# таких host'ов host-match пропускается; останутся только name/alias-match
# и Stage 2 LLM.
_AGGREGATOR_HOSTS = frozenset({
    "t.me",
    "telegram.me",
    "telegram.org",
    "linkedin.com",
    "hh.ru",
    "habr.com",
    "vc.ru",
    "github.com",
    "gitlab.com",
    "avito.ru",
    "superjob.ru",
    "facebook.com",
    "instagram.com",
    "twitter.com",
    "x.com",
    "vk.com",
    "ok.ru",
    "youtube.com",
    "behance.net",
    "dribbble.com",
    "medium.com",
    # Шеринговые хостинги job-страниц / резидент-каталоги: на одном
    # хосте сидит много разных компаний → Stage 1c (website-match) на
    # таком общем домене склеит их в одну. Любой *.potok.io,
    # *.huntflow.io и т.п. — это резюме-/job-board, а не сайт компании.
    "potok.io",
    "huntflow.io",
    "huntflow.ru",
    "amazingjobs.ru",
    "getmatch.ru",
    "jobs.ru",
    "talantix.ru",
    "rabota.ru",
    "trudvsem.ru",
    "career.ru",
})


def _is_aggregator_host(host: str) -> bool:
    """True если host — агрегатор/соцсеть/мессенджер, а не корпоративный
    сайт. Suffix-match: ловит и `linkedin.com`, и `m.linkedin.com`,
    `careers.hh.ru` и т.п."""
    if not host:
        return False
    for h in _AGGREGATOR_HOSTS:
        if host == h or host.endswith("." + h):
            return True
    return False


def _signal_host(host: str) -> str:
    """Хост, очищенный от «нет сигнала о компании». Для всего, что
    является агрегатором/соцсетью/мессенджером, возвращает пустую
    строку: hard-rule по хостам тогда не вето́рит, а обращается с этим
    как с «website не указан». Альтернатива (вето́рить) ломала бы
    очевидные кейсы вроде `(Acme, acme.com)` vs `(Acme, t.me/Acme)`,
    где парсер сунул в company_website ссылку на канал — на самом деле
    это та же компания, и решение должно приниматься по name-match."""
    if not host or _is_aggregator_host(host):
        return ""
    return host


def _real_corporate_website(url: str | None) -> str | None:
    """Возвращает очищенный URL ТОЛЬКО если это настоящий корпоративный
    домен. Для aggregator/соцсеть/мессенджер ссылок (t.me/Acme,
    linkedin.com/Acme, hh.ru/employer/...) вернёт None — такие URL'ы
    не должны попадать в `company.website`, иначе UI показал бы юзеру
    ссылку-на-канал как «официальный сайт компании», а будущие парсы
    ничего полезного из этого host'а извлечь не смогут.
    Используется как enrichment-гейт И как фильтр при создании новой
    строки — оба пути иначе персистили бы aggregator-URL'ы."""
    cleaned = (url or "").strip() or None
    if not cleaned:
        return None
    if not _signal_host(_normalize_host(cleaned)):
        return None
    return cleaned


def _hosts_compatible(a: str, b: str) -> bool:
    """Hard-rule: разные непустые хосты = разные компании. Если один
    хост пустой (компания без указанного сайта) — не блокируем match."""
    if not a or not b:
        return True
    return a == b


def _enrich_company_with_parsed(
    company: Company,
    parsed_name: str,
    parsed_website: str | None,
) -> None:
    """Подсасываем parsed-данные в существующую строку:
    1. website — если в БД пусто и у нас приехал НАСТОЯЩИЙ корпоративный
       домен (не aggregator-URL: aggregator пропускаем через
       `_real_corporate_website`, чтобы не оседали как «официальный сайт
       компании» — это и неверная семантика для UI, и испорченный сигнал
       для будущих host-match'ей).
    2. parsed_name — добавляем в aliases, если такого написания ещё не
       было (ни в name, ни в существующих aliases).
    Не трогает decision/log — это чистая мутация модели, чтобы её можно
    было переиспользовать и из match-веток, и из race-fallback пути.
    """
    real_website = _real_corporate_website(parsed_website)
    if real_website and not company.website:
        company.website = real_website

    parsed_norm = _normalize_company_name(parsed_name)
    if parsed_norm:
        existing_norms = {_normalize_company_name(company.name)}
        existing_norms.update(
            _normalize_company_name(a) for a in (company.aliases or [])
        )
        if parsed_norm not in existing_norms:
            aliases = list(company.aliases or [])
            aliases.append(parsed_name.strip())
            company.aliases = aliases


def _accept_company_match(
    company: Company,
    parsed_name: str,
    parsed_website: str | None,
    decision: dict,
    stage: str,
) -> tuple[Company, dict]:
    """Использует существующую строку: enrich + decision.stage/matched_id."""
    _enrich_company_with_parsed(company, parsed_name, parsed_website)
    decision["stage"] = stage
    decision["matched_id"] = company.id
    # Аудит-лог: каждое склеивание необратимо на уровне vacancy.company_id.
    # Логируем явно, чтобы post-hoc grep по `company_dedup` показал, как
    # пайплайн пришёл к решению. Лог-host — raw-нормализованный (не
    # signal-coerced), чтобы видеть в логе исходный URL вакансии.
    logger.info(
        "company_dedup: matched stage=%s id=%d parsed_name=%r parsed_host=%r company_name=%r",
        stage,
        company.id,
        parsed_name,
        _normalize_host(parsed_website),
        company.name,
    )
    return company, decision


async def _create_company_row(
    session: AsyncSession,
    name: str,
    website: str | None,
    decision: dict,
) -> tuple[Company | None, dict]:
    """Создание новой строки. На race по UNIQUE(name) — re-lookup точного
    совпадения (детерминированное, без LLM, чтобы не закольцеваться) и
    обогащение найденной строки тем же enrichment'ом, что в match-ветках
    (website-fill / alias-fold) — чтобы concurrent ingest не терял
    parsed-данные.

    Если decision["stage"] уже несёт сигнал «LLM был вызван и не
    сматчил» (`llm_no_match`), сохраняем его в `pre_create_stage` ДО
    перезаписи на `create`, иначе DB-only audit не отличит «LLM пробовали»
    от «LLM не вызывался»."""
    # Aggregator-URL'ы НЕ персистим как website новой компании по тем же
    # причинам, что в _enrich_company_with_parsed: «канальная» ссылка не
    # является корпоративным сайтом. None в этой колонке честнее, чем
    # ложный t.me/AcmeChannel, и не отравляет будущий host-match.
    persisted_website = _real_corporate_website(website)
    prior_stage = decision.get("stage")
    if prior_stage and prior_stage not in ("skip", None):
        decision["pre_create_stage"] = prior_stage
    name_clean = name.strip()
    try:
        async with session.begin_nested():
            company = Company(
                name=name_clean,
                aliases=[],
                website=persisted_website,
            )
            session.add(company)
            await session.flush()
        decision["stage"] = "create"
        decision["matched_id"] = company.id
        logger.info(
            "company_dedup: created id=%d name=%r website=%r",
            company.id,
            name_clean,
            persisted_website,
        )
        return company, decision
    except IntegrityError:
        # UNIQUE(name) в SQLite case-sensitive: IntegrityError срабатывает
        # только на точное совпадение. Re-lookup делаем по той же точной
        # строке, что и пытались insert'ить — иначе case-insensitive lower()
        # мог бы вернуть row, который НЕ был причиной race-collision.
        company = (
            await session.scalars(
                select(Company).where(Company.name == name_clean)
            )
        ).first()
        if company is not None:
            # Race produced a row with same name. Применяем тот же
            # enrichment, что в match-ветках: parsed-данные не должны
            # теряться от того, что concurrent ingest нас опередил.
            _enrich_company_with_parsed(company, name, website)
            decision["stage"] = "create_race_fallback"
            decision["matched_id"] = company.id
            logger.info(
                "company_dedup: race fallback id=%d name=%r",
                company.id,
                name_clean,
            )
        return company, decision


async def find_or_create_company(
    session: AsyncSession,
    name: str,
    *,
    website: str | None = None,
    lm_client: Any = None,
    lm_model: str | None = None,
) -> tuple[Company | None, dict]:
    """Резолв распарсенной (name, website) пары к существующей компании
    или создание новой. Возвращает кортеж (company, decision).

    decision — dict с полями:
        stage:    "rule_name" | "rule_alias" | "rule_website" |
                  "llm_match" | "llm_no_match" | "create" |
                  "create_race_fallback" | "skip"
        matched_id:    int | None — id того row'а, к которому свелось
        candidates:    [{id, name, website}, ...] | None — shortlist для
                       LLM (заполняется только когда LLM вызывался)
        llm_reasoning: str | None — короткий ответ LLM

    ``lm_client`` / ``lm_model`` опциональны: без них Stage 2 пропускается,
    схема вырождается в чистые правила + create. Это удобно для тестов и
    для путей, где LLM-вызов нежелателен.
    """
    decision: dict = {
        "stage": "skip",
        "matched_id": None,
        "candidates": None,
        "llm_reasoning": None,
    }
    raw_name = (name or "").strip()
    if not raw_name:
        return None, decision

    parsed_norm = _normalize_company_name(raw_name)
    # Hard-rule по host'ам должен опираться только на «настоящие» сигналы:
    # агрегаторы (t.me, linkedin, hh.ru…) обращаемся как с пустым host'ом —
    # иначе попавшая в company_website ссылка на канал/профиль ломала бы
    # name-match для одной и той же компании. Coerce делаем здесь, дальше
    # везде используем уже очищенный host.
    parsed_host = _signal_host(_normalize_host(website))

    rows = list((await session.scalars(select(Company))).all())
    # Pre-вычисляем нормализованные представления каждой компании, чтобы не
    # повторять normalize в трёх внутренних циклах. c_host тоже сразу
    # пропускаем через _signal_host — для legacy-данных, где в БД могла
    # лечь ссылка на t.me как website.
    norms: list[tuple[Company, str, list[str], str]] = []
    for c in rows:
        norms.append(
            (
                c,
                _normalize_company_name(c.name),
                [_normalize_company_name(a) for a in (c.aliases or [])],
                _signal_host(_normalize_host(c.website)),
            )
        )

    # Если нормализация ужала имя в пустую строку — это значит на входе
    # пришёл только legal-suffix (например, "SAS"/"LLC"/"ПАО") без бренд-
    # ядра, либо имя из символов, которые мы выкинули как пунктуацию. Не
    # пускаем в name/alias-match: пустая строка совпала бы с любой другой
    # такой же пустой и склеила бы заведомо разные «голые» юр.формы.
    # Хост-match (Stage 1c) работает дальше как обычно — это безопаснее.
    if parsed_norm:
        # Stage 1a — точное совпадение нормализованного имени.
        # NB: ловит только варианты одного и того же написания (МТС/MTС/MTS
        # после транслитерации, ПАО Сбербанк → Сбербанк после strip'а суффикса).
        # «Бренд vs полное юр.название» (Сбер vs Сбербанк) сюда не
        # попадает — норм-формы у них разные ("sber" vs "sberbank") — это
        # территория Stage 2 (LLM-арбитр).
        for c, c_name_norm, _aliases, c_host in norms:
            if (
                c_name_norm
                and c_name_norm == parsed_norm
                and _hosts_compatible(c_host, parsed_host)
            ):
                return _accept_company_match(
                    c, raw_name, website, decision, "rule_name"
                )

        # Stage 1b — алиас совпал.
        for c, _name, c_aliases, c_host in norms:
            if any(
                a and a == parsed_norm for a in c_aliases
            ) and _hosts_compatible(c_host, parsed_host):
                return _accept_company_match(
                    c, raw_name, website, decision, "rule_alias"
                )

    # Stage 1c — точный match по хосту. Агрегаторы уже скоэрсены в "" в
    # _signal_host, поэтому если parsed_host здесь непустой — это реальный
    # corporate-домен. То же по c_host у каждого row.
    #
    # Намеренная асимметрия с user-rule «одинаковое имя + разные сайты =
    # разные компании»: ОБРАТНЫЙ кейс — «разные имена + одинаковый сайт» —
    # здесь склеивается без обращения к LLM. Логика: corporate-домен —
    # это сильный сигнал (rebrand / brand-vs-legal-name / parser-вариация
    # на одной и той же странице). Если в будущем выяснится, что и этот
    # путь даёт false-positives, можно ввести Левенштейн-порог по имени и
    # роутить low-similarity случаи через Stage 2.
    if parsed_host:
        for c, _name, _aliases, c_host in norms:
            if c_host and c_host == parsed_host:
                return _accept_company_match(
                    c, raw_name, website, decision, "rule_website"
                )

    # Stage 2 — LLM-арбитр. Кандидатами идут только те, кто прошёл по
    # similarity И не нарушает hard-rule по хостам. Иначе LLM не вызываем.
    # При пустом parsed_norm (имя свелось к пустоте после нормализации)
    # SequenceMatcher вернул бы 1.0 на любую другую пустую — и склеил бы
    # «голые» legal-suffix-имена. Skip'аем Stage 2, идём в create.
    if parsed_norm and lm_client is not None and lm_model:
        candidates: list[tuple[Company, float]] = []
        for c, c_name_norm, c_aliases, c_host in norms:
            if not _hosts_compatible(c_host, parsed_host):
                continue
            ratio_name = (
                SequenceMatcher(None, parsed_norm, c_name_norm).ratio()
                if c_name_norm
                else 0.0
            )
            ratio_alias = max(
                (
                    SequenceMatcher(None, parsed_norm, a).ratio()
                    for a in c_aliases
                    if a
                ),
                default=0.0,
            )
            best = max(ratio_name, ratio_alias)
            if best >= 0.7:
                candidates.append((c, best))
        candidates.sort(key=lambda x: -x[1])
        candidates = candidates[:5]
        if candidates:
            # Lazy import: repo не должен жёстко зависеть от llm-модуля при
            # импорте; LLM нужен только в этой ветке.
            from backend.llm.company import dedupe_company_with_llm

            shortlist = [c for c, _ in candidates]
            matched_id, reasoning = await dedupe_company_with_llm(
                lm_client,
                lm_model,
                parsed_name=raw_name,
                parsed_website=website,
                candidates=shortlist,
            )
            decision["candidates"] = [
                {"id": c.id, "name": c.name, "website": c.website}
                for c in shortlist
            ]
            decision["llm_reasoning"] = reasoning
            if matched_id is not None:
                # Hallucination-guard: LLM может вернуть id, которого мы
                # ему не давали. Принимаем только то, что было в shortlist.
                match = next(
                    (c for c in shortlist if c.id == matched_id), None
                )
                if match is not None:
                    return _accept_company_match(
                        match, raw_name, website, decision, "llm_match"
                    )
                # Galлюцинация: LLM ответил id'шник, которого мы ему не
                # давали. Сохраняем его в decision для post-hoc grep'а —
                # иначе следы только в reasoning-тексте, нечитаемо.
                decision["llm_hallucinated_id"] = matched_id
                logger.warning(
                    "company_dedup: LLM hallucinated id=%r outside shortlist=%r",
                    matched_id,
                    [c.id for c in shortlist],
                )
            decision["stage"] = "llm_no_match"
            # Аудит-лог: LLM был вызван, но решил «не то». Без отдельной
            # записи следующий logger.info("created ...") выглядит так,
            # будто LLM не вызывался вовсе. parsed_host логируем raw-
            # нормализованный (не signal-coerced) — чтобы видеть, какой
            # URL пришёл из вакансии, а не пустую строку после coercion.
            logger.info(
                "company_dedup: llm_no_match parsed_name=%r parsed_host=%r "
                "shortlist_ids=%r reasoning=%r",
                raw_name,
                _normalize_host(website),
                [c.id for c in shortlist],
                reasoning,
            )

    # Stage 3 — создаём новую.
    return await _create_company_row(session, raw_name, website, decision)
