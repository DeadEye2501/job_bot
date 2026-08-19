"""Сведение разобранной из вакансии компании с уже заведённой."""

import logging
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import Company
from backend.payloads import str_list
from backend.repository.companies_card import add_company_spellings, create_company
from backend.repository.companies_keys import (
    hosts_compatible,
    normalize_company_name,
    normalize_host,
    real_corporate_website,
    signal_host,
)

logger = logging.getLogger(__name__)


def _known_spellings(company: Company) -> tuple[str, list[str]]:
    """Известные написания компании, приведённые к сравнимому виду.

    Имя и прозвища отдаются порознь, а не общим набором: отбор правилами
    различает, чем именно совпало — своим именем или прозвищем, — и ярлык
    сведения от этого разный. Обязательство при этом одно: что считать
    написанием и как его сравнивать, — и порознь эти две половины
    («известное написание» против «нового») разошлись бы молча.
    """
    return (
        normalize_company_name(company.name),
        [normalize_company_name(a) for a in str_list(company.aliases)],
    )


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

    if not normalize_company_name(parsed_name):
        return
    add_company_spellings(company, [parsed_name])


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


def _keep_pre_create_stage(decision: dict) -> None:
    """Сохранить стадию, с которой пришли к созданию строки.

    Если в решении уже стоит сигнал «модель звали, и она не свела»
    (`llm_no_match`), исход создания его перезапишет — и разбор по одной
    базе перестанет отличать «модель пробовали» от «модель не звали».
    """
    prior_stage = decision.get("stage")
    if prior_stage and prior_stage != "skip":
        decision["pre_create_stage"] = prior_stage


async def _insert_company(
    session: AsyncSession, name: str, website: str | None, decision: dict
) -> Company | None:
    """Завести строку компании; пусто — имя уже занято.

    Вложенная сделка нужна только здесь: срыв по UNIQUE(name) разбирается
    зовущим на два исхода, и без точки отката сорвавшаяся вставка утащила
    бы за собой всю запись вакансии.
    """
    try:
        async with session.begin_nested():
            company = await create_company(
                session, name=name, website=website
            )
    except IntegrityError:
        return None
    decision["stage"] = "create"
    decision["matched_id"] = company.id
    logger.info(
        "company_dedup: created id=%d name=%r website=%r",
        company.id,
        name,
        website,
    )
    return company


async def _company_by_exact_name(
    session: AsyncSession, name: str
) -> Company | None:
    """Строка, столкнувшаяся с нами по имени.

    Ищем ровно тем написанием, которым пытались вставить: UNIQUE(name) в
    SQLite чувствителен к регистру, и поиск по приведённому имени вернул бы
    строку, которая столкновения не вызывала.
    """
    return (
        await session.scalars(select(Company).where(Company.name == name))
    ).first()


async def _create_company_row(
    session: AsyncSession,
    name: str,
    website: str | None,
    decision: dict,
    seen_ids: set[int],
) -> tuple[Company | None, dict]:
    """Создание новой строки. На срыве по UNIQUE(name) — поиск точного
    совпадения (детерминированный, без модели, чтобы не закольцеваться) и
    обогащение найденной тем же образом, что в ветках сведения: иначе
    разбор, пришедший вторым, потерял бы разобранные им данные.

    ``seen_ids`` — строки, которые разбор видел в своей выборке; по ним
    срыв и делится на два исхода. Найденная среди них означает сведение по
    имени: правила её не взяли (у неё другой сайт), а уникальность имени
    свела — это ежедневный путь. Не найденная означает настоящую гонку:
    строка появилась между выборкой и вставкой.
    """
    # Aggregator-URL'ы НЕ персистим как website новой компании по тем же
    # причинам, что в _enrich_company_with_parsed: «канальная» ссылка не
    # является корпоративным сайтом. None в этой колонке честнее, чем
    # ложный t.me/AcmeChannel, и не отравляет будущий host-match.
    persisted_website = real_corporate_website(website)
    _keep_pre_create_stage(decision)
    name_clean = name.strip()
    company = await _insert_company(
        session, name_clean, persisted_website, decision
    )
    if company is not None:
        return company, decision
    company = await _company_by_exact_name(session, name_clean)
    if company is None:
        return None, decision
    # Исход тот же, что у трёх правил выше — использованная чужая строка, —
    # поэтому и оформляется он тем же объявлением: со своим enrichment и
    # своей строкой аудита эта ветка разошлась бы с ними молча.
    stage = (
        "rule_name_unique" if company.id in seen_ids else "create_race_fallback"
    )
    return _accept_company_match(company, name, website, decision, stage)


@dataclass(frozen=True, slots=True)
class _Parsed:
    """Разобранная пара «имя и сайт», приведённая к сравнимому виду.

    Четыре значения об одном предмете, и порознь они не ходят: имя как
    написано — для записи и журнала, нормализованное — для сравнения, хост —
    для правил, исходная ссылка — для обогащения найденной строки.

    Хост уже пропущен через `signal_host`: агрегаторы (t.me, linkedin, hh.ru)
    считаются пустым хостом, иначе попавшая в поле сайта ссылка на канал
    ломала бы сведение по имени у одной и той же компании.
    """

    raw_name: str
    norm: str
    host: str
    website: str | None

    @classmethod
    def of(cls, raw_name: str, website: str | None) -> "_Parsed":
        """Привести пришедшее из разбора к сравнимому виду."""
        return cls(
            raw_name=raw_name,
            norm=normalize_company_name(raw_name),
            host=signal_host(normalize_host(website)),
            website=website,
        )


def _new_decision() -> dict:
    """Пустой протокол сведения — то, что уедет в ленту вакансии.

    Поля:
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

    Ещё два поля кладутся не всегда, и потому их нет в пустом протоколе:

        pre_create_stage:   str — стадия, с которой пришли к заведению строки.
                            Без неё исход «create» стёр бы след от `llm_no_match`,
                            и разбор по одной базе перестал бы отличать
                            «модель звали» от «модель не звали».
        llm_hallucinated_id: int — номер, который арбитр назвал в ответе, но
                            которого не было в показанном ему списке. Иначе
                            след от него остался бы только в свободном тексте
                            рассуждения.
    """
    return {
        "stage": "skip",
        "matched_id": None,
        "candidates": None,
        "llm_reasoning": None,
    }


async def _companies_in_order(session: AsyncSession) -> list[Company]:
    """Все компании в порядке заведения — по возрастанию номера.

    Порядок здесь и есть правило: отбор берёт первое сработавшее, а
    столкновение по имени выигрывает первый. Кто первый, без `order_by`
    решала бы выдача базы, которой никто не назначил порядка: две строки с
    одним ключом («Acme» и «acme») меняли бы победителя от `VACUUM` к
    `VACUUM`, а с ним — и карточку, в которую уедет вакансия.
    """
    return list(
        (await session.scalars(select(Company).order_by(Company.id.asc()))).all()
    )


def _company_norms(rows) -> list[tuple[Company, str, list[str], str]]:
    """Нормализованные представления каждой компании, посчитанные один раз.

    Три прохода отбора спрашивают об одном и том же — имя, прозвища, хост, —
    и нормализация в каждом стоила бы втрое. `signal_host` здесь же: у старых
    строк в поле сайта могла лежать ссылка на канал, и без коэрса она
    сработала бы как настоящий корпоративный домен.
    """
    return [
        (c, *_known_spellings(c), signal_host(normalize_host(c.website)))
        for c in rows
    ]


def _same_name(norms, parsed: _Parsed) -> Company | None:
    """Компания с тем же нормализованным именем и несопротивляющимся хостом.

    Ловит только варианты одного написания: МТС/MTС/MTS после транслитерации,
    «ПАО Сбербанк» → «Сбербанк» после снятия юр.формы. «Бренд против полного
    названия» (Сбер против Сбербанк) сюда не попадает — норм-формы у них
    разные, — это территория арбитра.
    """
    for c, c_name_norm, _aliases, c_host in norms:
        if (
            c_name_norm
            and c_name_norm == parsed.norm
            and hosts_compatible(c_host, parsed.host)
        ):
            return c
    return None


def _same_alias(norms, parsed: _Parsed) -> Company | None:
    """Компания, у которой это имя записано прозвищем."""
    for c, _name, c_aliases, c_host in norms:
        if any(a and a == parsed.norm for a in c_aliases) and hosts_compatible(
            c_host, parsed.host
        ):
            return c
    return None


def _same_host(norms, parsed: _Parsed) -> Company | None:
    """Компания с тем же корпоративным доменом.

    Агрегаторы уже сведены к пустоте в `signal_host`, поэтому непустой хост
    здесь — настоящий корпоративный домен, с обеих сторон.

    Асимметрия с правилом «одинаковое имя и разные сайты — разные компании»
    намеренная: обратный случай — разные имена при одном сайте — склеивается
    без обращения к модели. Домен тут сильный сигнал: ребрендинг, бренд
    против юр.названия, вариация разбора одной и той же страницы.
    """
    for c, _name, _aliases, c_host in norms:
        if c_host and c_host == parsed.host:
            return c
    return None


def _rule_match(norms, parsed: _Parsed):
    """Кто из компаний сведён правилами; отдаёт его и ярлык сработавшего.

    Три правила подряд — имя, прозвище, хост, — и порядок у них по силе
    сигнала: первое сработавшее решает.

    Пустое нормализованное имя до первых двух не доходит: на входе была одна
    юр.форма («ПАО», «LLC») без бренд-ядра, и пустая строка совпала бы с любой
    другой такой же, склеив заведомо разные компании. Отбор по хосту при этом
    работает как обычно — он безопаснее.
    """
    if parsed.norm:
        by_name = _same_name(norms, parsed)
        if by_name is not None:
            return by_name, "rule_name"
        by_alias = _same_alias(norms, parsed)
        if by_alias is not None:
            return by_alias, "rule_alias"
    if parsed.host:
        found = _same_host(norms, parsed)
        if found is not None:
            return found, "rule_website"
    return None


def _llm_shortlist(norms, parsed: _Parsed) -> list[Company]:
    """Кого показать арбитру: похожие по имени и не спорящие по хосту.

    Порог схожести и длина списка стоят здесь, а не доводами: задавать их
    по-своему некому, а доводов у зовущего и так пять.

    Пустое нормализованное имя сюда не приходит, и это забота зовущего:
    `SequenceMatcher` вернул бы на нём единицу против любой другой пустой
    строки и показал бы арбитру все «голые» юр.формы разом.
    """
    scored: list[tuple[Company, float]] = []
    for c, c_name_norm, c_aliases, c_host in norms:
        if not hosts_compatible(c_host, parsed.host):
            continue
        ratio_name = (
            SequenceMatcher(None, parsed.norm, c_name_norm).ratio()
            if c_name_norm
            else 0.0
        )
        ratio_alias = max(
            (SequenceMatcher(None, parsed.norm, a).ratio() for a in c_aliases if a),
            default=0.0,
        )
        best = max(ratio_name, ratio_alias)
        if best >= 0.7:
            scored.append((c, best))
    scored.sort(key=lambda x: -x[1])
    return [c for c, _ in scored[:5]]


def _log_no_match(parsed: _Parsed, shortlist, reasoning: str | None) -> None:
    """Модель звали, и она решила «не то».

    Без этой записи следующая строка про заведение выглядела бы так, будто
    модель не звали вовсе. Хост пишется до коэрса — чтобы видеть, какая
    ссылка пришла из вакансии, а не пустоту после него.
    """
    logger.info(
        "company_dedup: llm_no_match parsed_name=%r parsed_host=%r "
        "shortlist_ids=%r reasoning=%r",
        parsed.raw_name,
        normalize_host(parsed.website),
        [c.id for c in shortlist],
        reasoning,
    )


async def _llm_arbitrate(
    lm_client: Any, lm_model: str, parsed: _Parsed, shortlist
) -> tuple[Company | None, dict]:
    """Спросить модель, кто из показанных — та же компания.

    Отдаёт найденного и приписку к протоколу, а не правит протокол сам: чем
    кончилось дело, решает зовущий, а приписка ложится при любом исходе.
    Номер вне списка — модель возвращает и такой — сохраняется в протоколе:
    иначе след от него остаётся только в свободном тексте рассуждения. Ввоз
    слоя модели внутри тела: репозиторий не должен зависеть от него на
    импорте, а нужен он только здесь и только когда до арбитра дошло.
    """
    from backend.llm.company import dedupe_company_with_llm

    matched_id, reasoning = await dedupe_company_with_llm(
        lm_client,
        lm_model,
        parsed_name=parsed.raw_name,
        parsed_website=parsed.website,
        candidates=shortlist,
    )
    patch: dict = {
        "candidates": [
            {"id": c.id, "name": c.name, "website": c.website} for c in shortlist
        ],
        "llm_reasoning": reasoning,
    }
    if matched_id is not None:
        match = next((c for c in shortlist if c.id == matched_id), None)
        if match is not None:
            return match, patch
        patch["llm_hallucinated_id"] = matched_id
        logger.warning(
            "company_dedup: LLM hallucinated id=%r outside shortlist=%r",
            matched_id,
            [c.id for c in shortlist],
        )
    _log_no_match(parsed, shortlist, reasoning)
    return None, patch


async def find_or_create_company(
    session: AsyncSession,
    name: str,
    *,
    website: str | None = None,
    lm_client: Any = None,
    lm_model: str | None = None,
) -> tuple[Company | None, dict]:
    """Свести разобранную пару «имя и сайт» с компанией или завести новую.

    Ступени идут по силе сигнала: правила, арбитр из языковой модели по
    короткому списку похожих, заведение. Без клиента модели арбитр
    пропускается; протокол описан у `_new_decision`.
    """
    decision = _new_decision()
    raw_name = (name or "").strip()
    if not raw_name:
        return None, decision
    parsed = _Parsed.of(raw_name, website)
    rows = await _companies_in_order(session)
    norms = _company_norms(rows)
    ruled = _rule_match(norms, parsed)
    if ruled is not None:
        matched, stage = ruled
        return _accept_company_match(matched, raw_name, website, decision, stage)

    if parsed.norm and lm_client is not None and lm_model:
        shortlist = _llm_shortlist(norms, parsed)
        if shortlist:
            match, patch = await _llm_arbitrate(lm_client, lm_model, parsed, shortlist)
            decision.update(patch)
            if match is not None:
                return _accept_company_match(
                    match, raw_name, website, decision, "llm_match"
                )
            decision["stage"] = "llm_no_match"

    return await _create_company_row(
        session, raw_name, website, decision, {c.id for c in rows}
    )
