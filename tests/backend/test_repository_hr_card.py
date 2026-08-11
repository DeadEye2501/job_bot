"""Следствия сборки карточки HR для боковой панели контактов.

Карточка складывается из четырёх отдельных запросов вокруг одной строки:
сколько у HR вакансий, какая компания была последней, сколько непрочитанных
сообщений и стоит ли он в чёрном списке.
"""

from backend.repository.hr_card import get_hr_detail
from tests.dbio import put
from tests.factories import (
    at,
    company_row,
    hr_row,
    message_row,
    unread_probe,
    vacancy_row,
)


async def test_a_missing_hr_has_no_card(session, session_factory):
    """У несуществующего HR карточки нет, и это не ошибка."""
    await put(session_factory, hr_row())

    assert await get_hr_detail(session, 10_000) is None


async def test_a_fresh_hr_has_zeroes_rather_than_emptiness(session, session_factory):
    """У свежего HR счётчики нулевые, а компании и отметки списка нет."""
    hr = hr_row()
    await put(session_factory, hr)

    card = await get_hr_detail(session, hr.id)

    assert card.vacancy_count == 0
    assert card.unread_count == 0
    assert card.last_company_id is None
    assert card.last_company_name is None
    assert card.blacklist_value is None


async def test_the_vacancy_count_covers_the_unparsed_ones_too(
    session, session_factory
):
    """Счётчик вакансий считает и недоразобранные, в отличие от мини-списка.

    Мини-список под счётчиком их отсеивает, и расхождение здесь настоящее:
    счётчик покажет больше, чем видно строк. Тест закрепляет сегодняшнее
    поведение обеих сторон.
    """
    hr = hr_row()
    other = hr_row(name="соседний")
    await put(session_factory, hr, other)
    await put(
        session_factory,
        vacancy_row(hr_id=hr.id, is_parsed=True),
        vacancy_row(hr_id=hr.id, is_parsed=False),
        vacancy_row(hr_id=other.id, is_parsed=True),
        vacancy_row(hr_id=None, is_parsed=True),
    )

    card = await get_hr_detail(session, hr.id)

    assert card.vacancy_count == 2


async def test_the_last_company_comes_from_the_freshest_vacancy(
    session, session_factory
):
    """Последняя компания берётся с самой свежей вакансии этого HR."""
    hr = hr_row()
    await put(session_factory, hr)
    was = company_row(name="Контур")
    now = company_row(name="Ромашка")
    await put(session_factory, was, now)
    await put(
        session_factory,
        vacancy_row(hr_id=hr.id, company_id=was.id, created_at=at(10)),
        vacancy_row(hr_id=hr.id, company_id=now.id, created_at=at(50)),
    )

    card = await get_hr_detail(session, hr.id)

    assert card.last_company_id == now.id
    assert card.last_company_name == "Ромашка"


async def test_a_vacancy_without_a_company_leaves_the_card_without_one(
    session, session_factory
):
    """Вакансия без привязанной компании компанию в карточку не приносит."""
    hr = hr_row()
    await put(session_factory, hr)
    await put(session_factory, vacancy_row(hr_id=hr.id, company_name="Контур"))

    card = await get_hr_detail(session, hr.id)

    assert card.last_company_id is None
    assert card.last_company_name is None


async def test_only_unread_incoming_messages_are_counted(session, session_factory):
    """В непрочитанные идут только входящие, непрочтённые и неудалённые."""
    hr = hr_row()
    other = hr_row(name="соседний")
    await put(session_factory, hr, other)
    await put(
        session_factory,
        *unread_probe(hr.id),
        message_row(hr_id=other.id, is_incoming=True, read_at=None),
    )

    card = await get_hr_detail(session, hr.id)

    assert card.unread_count == 1
