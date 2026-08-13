"""Следствия наполнения строки списка HR.

Счётчик вакансий, последняя компания, счётчик непрочитанных и отметка чёрного
списка собираются отдельными запросами и раскладываются по строкам одним
проходом — вместо запроса на каждого.
"""

from backend.repository.hr_list import list_hr_with_counts
from tests.dbio import put
from tests.factories import (
    at,
    blacklist_row,
    company_row,
    hr_row,
    unread_probe_with_a_neighbour,
    vacancy_row,
)


async def test_the_row_carries_its_counts_and_last_company(session, session_factory):
    """В строке списка едут счётчики и последняя компания.

    Свежая вакансия вставлена раньше старой: иначе «взята свежая» совпало бы
    со «взята последняя вставленная», и отбор по времени можно было бы снять
    незаметно.

    Непрочитанным считается только входящее, непрочтённое и неудалённое, и
    рядом с подходящим лежит по одному нарушителю каждого условия — иначе
    любое из трёх снималось бы молча.
    """
    hr = hr_row(name="Анна")
    other = hr_row(name="Борис")
    await put(session_factory, hr, other)
    was = company_row(name="Контур")
    now = company_row(name="Ромашка")
    await put(session_factory, was, now)
    await put(
        session_factory,
        vacancy_row(hr_id=hr.id, company_id=now.id, created_at=at(50)),
        vacancy_row(hr_id=hr.id, company_id=was.id, created_at=at(10)),
        vacancy_row(hr_id=other.id),
        *unread_probe_with_a_neighbour(hr.id, other.id),
    )

    found, _ = await list_hr_with_counts(session)
    row = next(r for r in found if r.hr.id == hr.id)

    assert row.vacancy_count == 2
    assert row.last_company_name == "Ромашка"
    assert row.unread_count == 1
    assert row.is_blacklisted is False


async def test_vacancies_of_the_same_moment_are_broken_by_id(
    session, session_factory
):
    """Из двух вакансий одного момента компанию даёт заведённая позже.

    Времена создания проставляет база одним `CURRENT_TIMESTAMP`, и две
    вакансии, вставленные подряд, легко получают одну метку. Без разрешителя
    компания в строке менялась бы от загрузки к загрузке.
    """
    hr = hr_row(name="Анна")
    await put(session_factory, hr)
    first = company_row(name="Контур")
    second = company_row(name="Ромашка")
    await put(session_factory, first, second)
    await put(
        session_factory,
        vacancy_row(hr_id=hr.id, company_id=first.id, created_at=at(20)),
        vacancy_row(hr_id=hr.id, company_id=second.id, created_at=at(20)),
    )

    found, _ = await list_hr_with_counts(session)
    row = next(r for r in found if r.hr.id == hr.id)

    assert row.last_company_name == "Ромашка"


async def test_an_unlinked_freshest_vacancy_leaves_the_company_empty(
    session, session_factory
):
    """Если самая свежая вакансия ни к какой компании не привязана, компании нет.

    Взять компанию с той, что постарше, было бы обманом: в выборщике важно,
    с кем этот HR работает сейчас.

    Непривязанная вакансия вставлена раньше привязанной: иначе отбор по
    времени можно было бы снять — по идентификатору победила бы та же
    строка, и ответ не изменился бы.
    """
    hr = hr_row(name="Анна")
    await put(session_factory, hr)
    company = company_row(name="Контур")
    await put(session_factory, company)
    await put(
        session_factory,
        vacancy_row(hr_id=hr.id, company_id=None, created_at=at(50)),
        vacancy_row(hr_id=hr.id, company_id=company.id, created_at=at(10)),
    )

    found, _ = await list_hr_with_counts(session)
    row = next(r for r in found if r.hr.id == hr.id)

    assert row.last_company_name is None


async def test_the_blacklist_mark_is_set_under_either_spelling(
    session, session_factory
):
    """Отметка чёрного списка ставится по любому из двух написаний."""
    by_username = hr_row(name="Анна", telegram_username="anna", telegram_user_id=111)
    by_id = hr_row(name="Борис", telegram_username="boris", telegram_user_id=222)
    clean = hr_row(name="Виктор", telegram_username="vik", telegram_user_id=333)
    await put(session_factory, by_username, by_id, clean)
    await put(
        session_factory,
        blacklist_row("hr", "@anna"),
        blacklist_row("hr", "user_id:222"),
        blacklist_row("hr", "@vik", active=False),
        blacklist_row("channel", "@vik"),
    )

    found, _ = await list_hr_with_counts(session)
    marks = {r.hr.name: r.is_blacklisted for r in found}

    assert marks == {"Анна": True, "Борис": True, "Виктор": False}
