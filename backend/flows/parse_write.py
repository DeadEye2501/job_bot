"""Запись исхода разбора: строка вакансии, её контакт, компания и собеседник.

Отделено от самого разбора: там решают, чем объявление кончилось, здесь это
кладут в базу. Приговоров тут не выносят — исход приходит доводом (`Outcome`),
и знание идёт в одну сторону: разбор зовёт отсюда `persist_parse_outcome`,
обратных зовов нет.
"""

import logging
from dataclasses import dataclass

from backend.domain.salary import parse_salary
from backend.models import HR
from backend.models import Vacancy
from backend.models import VacancyStatus
from backend.payloads import DIRECT_PARSED_FIELDS, ParsedVacancy
from backend.repository.companies_matching import find_or_create_company
from backend.repository.hr_identify import find_or_create_hr
from backend.repository.vacancies_life import add_vacancy_event
from backend.repository.vacancy_contacts import replace_parsed_contact
from backend.repository.vacancy_status import apply_parse_outcome
from backend.telegram_lookup import fetch_telegram_avatar
from backend.telegram_lookup import resolve_hr_telegram

logger = logging.getLogger(__name__)



@dataclass(frozen=True, slots=True)
class Outcome:
    """Чем кончился разбор объявления и что из этого следует для записи.

    ``keep_previous_stack`` разводит две ветки. У обычного разбора пустой
    стек означает осечку модели, и прежние теги вместе с прежней оценкой
    перезапись переживают. У пустышки он означает сам приговор, и в
    строку идёт то, что пришло.
    """

    status: VacancyStatus
    skip_reason: str | None
    score: int
    keep_previous_stack: bool


async def _resolve_hr(pipeline, parsed: ParsedVacancy | None):
    """Разыскать HR в Telegram и забрать заодно его аватар.

    Идёт до открытия сессии: иначе SQLite ждал бы ответа сети в
    незакоммиченном состоянии.
    """
    if parsed is None or not parsed.hr_contact:
        return None, None
    user = await resolve_hr_telegram(pipeline.client, parsed.hr_contact)
    if user is None:
        return None, None
    return user, await fetch_telegram_avatar(pipeline.client, user)


def _clear_parsed_fields(v: Vacancy, score: int) -> None:
    """Стереть прошлый разбор: колонки в пусто, стек — пустым списком.

    Оценка приходит доводом, а не нулём по месту: «разобрать не вышло» —
    тоже исход разбора, и число ему назначает тот, кто исход вынес.
    """
    for name in DIRECT_PARSED_FIELDS:
        setattr(v, name, None)
    v.stack = []
    v.score = score
    v.salary_min = None
    v.salary_max = None
    v.salary_currency = None


def _apply_parsed_fields(
    v: Vacancy, parsed: ParsedVacancy | None, outcome: Outcome
) -> None:
    """Перенести разобранное в строку вакансии.

    Разбора нет вовсе — прежние поля стираются: иначе в карточке рядом с
    причиной «пусто» висел бы прошлый разбор, и это читалось бы как
    поломка приложения.
    """
    if parsed is None:
        _clear_parsed_fields(v, outcome.score)
        return
    for name in DIRECT_PARSED_FIELDS:
        setattr(v, name, getattr(parsed, name))
    if parsed.stack or not outcome.keep_previous_stack:
        v.stack = parsed.stack
        v.score = outcome.score
    else:
        # Стек и оценка держатся парой: оценка считается от стека, и
        # записав пустой стек с нулевой оценкой, карточка показала бы
        # ноль баллов рядом с прежними тегами.
        v.stack = v.stack or []
        if v.score is None:
            v.score = outcome.score
    v.salary_min, v.salary_max, v.salary_currency = parse_salary(parsed.salary)


def _fields_filled(v: Vacancy) -> list[str]:
    """Чем строка вакансии после записи заполнена — это уходит в ленту.

    Стек в общий перечень не входит — он не переносится из разбора, а
    пересчитывается вместе с оценкой, — но встаёт сразу за контактом HR, а не
    в хвост: порядок здесь не оформление, а часть уже записанных строк ленты,
    и перестановка развела бы новые строки со старыми молча.
    """
    names = list(DIRECT_PARSED_FIELDS)
    names.insert(names.index("hr_contact") + 1, "stack")
    return [name for name in names if getattr(v, name)]


async def _write_parsed_row(
    session, vacancy_id: int, parsed: ParsedVacancy | None, outcome: Outcome
) -> Vacancy | None:
    """Записать исход разбора в саму строку вакансии и её найденный контакт;
    отдать строку или пустоту.

    Контакт пишется той же транзакцией, что и поля: найденное разбором не
    расходится с разобранной строкой. Заметки принадлежат человеку — разбор
    их не пишет и не стирает.

    Пустота означает «строки больше нет»: пользователь мог удалить её из
    окна, пока шёл разбор. Отвечать на это исключением нечем — исход уже
    вынесен, писать его некуда, и работа на этом кончается.

    Признак «разобрано» ставится здесь же, в той же транзакции, что и поля:
    упади запись между ними, строка осталась бы помеченной разобранной с
    полями от прошлого раза.
    """
    v = await session.get(Vacancy, vacancy_id)
    if v is None:
        return None
    apply_parse_outcome(v, outcome.status)
    v.skip_reason = outcome.skip_reason
    v.is_parsed = True
    _apply_parsed_fields(v, parsed, outcome)
    await replace_parsed_contact(
        session, vacancy_id, parsed.other_contact if parsed is not None else None
    )
    return v


async def _resolve_company(pipeline, parsed) -> tuple[int | None, dict | None]:
    """Свести компанию из разбора со своей строкой; отдать номер и решение.

    Идёт своей короткой сделкой до открытия сессии записи — как и розыск HR, и
    по той же причине: сведение спрашивает языковую модель, а ответа её ждут
    до трёх минут. Внутри начатой сделки база всё это время не приняла бы ни
    одной записи, и входящее письмо HR, пришедшее в тот же миг, потерялось бы
    вовсе.

    Решение отдаётся наружу затем, что уходит в ленту: по чему именно модель
    свела компании, разбирают потом по строке ленты, а не по журналу.

    Заведённая компания переживает пропавшую вакансию, и это верно: заводят её
    по имени из объявления, а не по самой строке.

    Компания привязывается и у непригодной вакансии — как и собеседник:
    ссылки из карточки в «Компании» и «HR» должны работать одинаково у любой
    строки, иначе имя компании в карточке есть, а перехода на неё нет.
    """
    if parsed is None or not parsed.company_name:
        return None, None
    async with pipeline.session_factory() as session:
        company, decision = await find_or_create_company(
            session,
            parsed.company_name,
            website=parsed.company_website,
            lm_client=pipeline.lm_client,
            lm_model=pipeline.lm_chat_model,
        )
        company_id = company.id if company is not None else None
        await session.commit()
    return company_id, decision


async def _link_resolved_hr(session, v: Vacancy, resolved) -> tuple[HR | None, bool]:
    """Привязать разысканного собеседника; отдать его и признак «только заведён».

    Признак нужен зовущему, а не здесь: по нему решается, догонять ли
    переписку, и догон обязан идти уже после закрытия сессии.
    """
    user, avatar = resolved
    if user is None:
        return None, False
    hr, created = await find_or_create_hr(session, user, avatar=avatar)
    v.hr_id = hr.id
    return hr, created


def _parsed_event_payload(v: Vacancy, outcome: Outcome, decision) -> dict:
    """Что уходит в ленту строкой «разобрано».

    Решение о сведении компании кладётся только когда оно было: пустое
    поле в ленте читалось бы как «сводили и не свели».
    """
    payload: dict = {
        "score": outcome.score,
        "status": outcome.status.value,
        "fields_filled": _fields_filled(v),
        "skip_reason": outcome.skip_reason,
    }
    if decision is not None:
        payload["company_dedup"] = decision
    return payload


async def persist_parse_outcome(
    pipeline, vacancy_id: int, parsed: ParsedVacancy | None, outcome: Outcome
) -> tuple[HR | None, bool] | None:
    """Провести исход разбора через сессию: розыск, запись, оповещение окна.

    Сама запись разложена по объявлениям выше; здесь остаётся чужое им:
    сессия, поломка посреди записи и оповещение окна после. Розыск
    собеседника и сведение компании идут первыми, каждый своей дорогой: это
    самые медленные и ломкие части работы, и в сессии записи им не место.

    Отдаёт HR и признак «только что заведён»: отклик пустышке не положен, а
    догон переписки обязан идти и после закрытия сессии, и после отправки
    отклика — иначе он вытащит наше же письмо раньше, чем оно запишется. Вне
    сессии HR пригоден: ``expire_on_commit=False``. Пустота вместо пары
    означает, что записи не было вовсе: строка пропала или запись сорвалась.
    """
    resolved = await _resolve_hr(pipeline, parsed)
    company_id, decision = await _resolve_company(pipeline, parsed)
    async with pipeline.session_factory() as session:
        try:
            v = await _write_parsed_row(session, vacancy_id, parsed, outcome)
            if v is None:
                return None
            if company_id is not None:
                v.company_id = company_id
            hr, hr_created = await _link_resolved_hr(session, v, resolved)
            await add_vacancy_event(
                session, vacancy_id, "parsed",
                _parsed_event_payload(v, outcome, decision),
            )
            await session.commit()
        except Exception:
            logger.exception(
                "vacancy %s: parse persist failed", vacancy_id,
                extra={"vacancy_id": vacancy_id},
            )
            return None

    pipeline.fire_contacts_changed()
    pipeline.fire_vacancies_changed()
    return hr, hr_created
