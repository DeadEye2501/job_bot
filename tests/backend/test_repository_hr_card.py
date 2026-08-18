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
    unread_probe_with_a_neighbour,
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


async def test_the_vacancy_count_matches_the_list_under_it(
    session, session_factory
):
    """Счётчик вакансий считает то же, что показывает мини-список под ним.

    Недоразобранные отсеивают оба: счётчик, разошедшийся со списком, читается
    как пропавшие строки. Сегодня такая вакансия и владельца не имеет —
    разбор ставит признак и хозяина одной сделкой, — но держаться этому на
    удаче устройства конвейера незачем.
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

    assert card.vacancy_count == 1


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


async def test_an_unlinked_freshest_vacancy_leaves_the_card_without_a_company(
    session, session_factory
):
    """Если самая свежая вакансия ни к какой компании не привязана, компании нет.

    То же правило, что у строки списка: важно, с кем этот человек работает
    сейчас, а не с кем работал когда-то. Прежде карточка брала компанию с
    той, что постарше, и два экрана называли разные компании — расхождение
    не удерживалось ничем.

    Непривязанная вакансия вставлена раньше привязанной: иначе отбор по
    времени можно было бы снять — по идентификатору победила бы та же
    строка, и ответ не изменился бы.
    """
    hr = hr_row()
    await put(session_factory, hr)
    company = company_row(name="Контур")
    await put(session_factory, company)
    await put(
        session_factory,
        vacancy_row(hr_id=hr.id, company_id=None, created_at=at(50)),
        vacancy_row(hr_id=hr.id, company_id=company.id, created_at=at(10)),
    )

    card = await get_hr_detail(session, hr.id)

    assert card.last_company_id is None
    assert card.last_company_name is None


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
    await put(session_factory, *unread_probe_with_a_neighbour(hr.id, other.id))

    card = await get_hr_detail(session, hr.id)

    assert card.unread_count == 1
