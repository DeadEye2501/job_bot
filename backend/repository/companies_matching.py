"""Сведение разобранной из вакансии компании с уже заведённой."""

import logging
from difflib import SequenceMatcher
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import Company
from backend.repository.companies_card import create_company
from backend.repository.companies_keys import (
    hosts_compatible,
    normalize_company_name,
    normalize_host,
    real_corporate_website,
    signal_host,
)

logger = logging.getLogger(__name__)


def _enrich_company_with_parsed(
    company: Company,
    parsed_name: str,
    parsed_website: str | None,
) -> None:
    """Подсасываем parsed-данные в существующую строку:
    1. website — если в БД пусто и у нас приехал НАСТОЯЩИЙ корпоративный
       домен (не aggregator-URL: aggregator пропускаем через
       `real_corporate_website`, чтобы не оседали как «официальный сайт
       компании» — это и неверная семантика для UI, и испорченный сигнал
       для будущих host-match'ей).
    2. parsed_name — добавляем в aliases, если такого написания ещё не
       было (ни в name, ни в существующих aliases).
    Не трогает decision/log — это чистая мутация модели, чтобы её можно
    было переиспользовать и из match-веток, и из race-fallback пути.
    """
    real_website = real_corporate_website(parsed_website)
    if real_website and not company.website:
        company.website = real_website

    parsed_norm = normalize_company_name(parsed_name)
    if parsed_norm:
        existing_norms = {normalize_company_name(company.name)}
        existing_norms.update(
            normalize_company_name(a) for a in (company.aliases or [])
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
        normalize_host(parsed_website),
        company.name,
    )
    return company, decision


async def _create_company_row(
    session: AsyncSession,
    name: str,
    website: str | None,
    decision: dict,
    seen_ids: set[int],
) -> tuple[Company | None, dict]:
    """Создание новой строки. На срыве по UNIQUE(name) — re-lookup точного
    совпадения (детерминированное, без LLM, чтобы не закольцеваться) и
    обогащение найденной строки тем же enrichment'ом, что в match-ветках
    (website-fill / alias-fold) — чтобы concurrent ingest не терял
    parsed-данные.

    ``seen_ids`` — строки, которые разбор видел в своей выборке; по ним
    срыв и делится на два исхода. Найденная среди них означает сведение по
    имени: правила её не взяли (у неё другой сайт), а уникальность имени
    свела — это ежедневный путь, ради которого enrichment здесь и стоит.
    Не найденная означает настоящую гонку: строка появилась между выборкой
    и вставкой.

    Если decision["stage"] уже несёт сигнал «LLM был вызван и не
    сматчил» (`llm_no_match`), сохраняем его в `pre_create_stage` ДО того,
    как исход перезапишет стадию, иначе DB-only audit не отличит «LLM
    пробовали» от «LLM не вызывался»."""
    # Aggregator-URL'ы НЕ персистим как website новой компании по тем же
    # причинам, что в _enrich_company_with_parsed: «канальная» ссылка не
    # является корпоративным сайтом. None в этой колонке честнее, чем
    # ложный t.me/AcmeChannel, и не отравляет будущий host-match.
    persisted_website = real_corporate_website(website)
    prior_stage = decision.get("stage")
    if prior_stage and prior_stage not in ("skip", None):
        decision["pre_create_stage"] = prior_stage
    name_clean = name.strip()
    try:
        # Вложенная сделка нужна только здесь: срыв по UNIQUE(name) тут
        # разбирается на два исхода, и без точки отката сорвавшаяся вставка
        # утащила бы за собой всю запись вакансии.
        async with session.begin_nested():
            company = await create_company(
                session, name=name_clean, website=persisted_website
            )
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
            # Исход тот же, что у трёх правил выше — использованная чужая
            # строка, — поэтому и оформляется он тем же объявлением: со
            # своим enrichment и своей строкой аудита эта ветка разошлась
            # бы с ними молча.
            return _accept_company_match(
                company,
                name,
                website,
                decision,
                "rule_name_unique"
                if company.id in seen_ids
                else "create_race_fallback",
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
                  "rule_name_unique" | "create_race_fallback" | "skip"
                  `rule_name_unique` и `create_race_fallback` — два исхода
                  сорвавшейся вставки, и различает их то, была ли строка
                  видна в выборке: первое — рядовое сведение однофамильцев,
                  второе — настоящая гонка вставок.
                  Ярлык уезжает в ленту вакансии навсегда, поэтому одним
                  словом они не зовутся; в уже записанных событиях гонкой
                  названо и то, и другое.
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

    parsed_norm = normalize_company_name(raw_name)
    # Hard-rule по host'ам должен опираться только на «настоящие» сигналы:
    # агрегаторы (t.me, linkedin, hh.ru…) обращаемся как с пустым host'ом —
    # иначе попавшая в company_website ссылка на канал/профиль ломала бы
    # name-match для одной и той же компании. Coerce делаем здесь, дальше
    # везде используем уже очищенный host.
    parsed_host = signal_host(normalize_host(website))

    rows = list((await session.scalars(select(Company))).all())
    # Pre-вычисляем нормализованные представления каждой компании, чтобы не
    # повторять normalize в трёх внутренних циклах. c_host тоже сразу
    # пропускаем через signal_host — для legacy-данных, где в БД могла
    # лечь ссылка на t.me как website.
    norms: list[tuple[Company, str, list[str], str]] = []
    for c in rows:
        norms.append(
            (
                c,
                normalize_company_name(c.name),
                [normalize_company_name(a) for a in (c.aliases or [])],
                signal_host(normalize_host(c.website)),
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
                and hosts_compatible(c_host, parsed_host)
            ):
                return _accept_company_match(
                    c, raw_name, website, decision, "rule_name"
                )

        # Stage 1b — алиас совпал.
        for c, _name, c_aliases, c_host in norms:
            if any(
                a and a == parsed_norm for a in c_aliases
            ) and hosts_compatible(c_host, parsed_host):
                return _accept_company_match(
                    c, raw_name, website, decision, "rule_alias"
                )

    # Stage 1c — точный match по хосту. Агрегаторы уже скоэрсены в "" в
    # signal_host, поэтому если parsed_host здесь непустой — это реальный
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
            if not hosts_compatible(c_host, parsed_host):
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
                normalize_host(website),
                [c.id for c in shortlist],
                reasoning,
            )

    # Stage 3 — создаём новую.
    return await _create_company_row(
        session, raw_name, website, decision, {c.id for c in rows}
    )
