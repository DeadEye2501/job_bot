"""Следствия удаления записи об HR.

Удаление выборочное: переписка уходит вместе с человеком — без него разговор
и правда ничей, — а вакансии остаются. Вакансия принадлежит каналу, откуда
пришла, а не тому, кто о ней написал.
"""

from sqlalchemy import select

from backend.models import HR, Message, Vacancy
from backend.repository import delete_hr
from tests.dbio import put
from tests.factories import hr_row, message_row, vacancy_row


async def test_deleting_a_missing_hr_reports_failure(session):
    """Удалить несуществующего HR нельзя, и вызов об этом сообщает."""
    assert await delete_hr(session, 10_000) is False


async def test_the_conversation_goes_with_the_person(session, session_factory):
    """Переписка удаляется вместе с человеком, но только его.

    Соседний HR в наборе не для полноты: без него «удалились все сообщения»
    и «удалились его сообщения» дали бы один ответ.
    """
    doomed = hr_row(name="под нож")
    spared = hr_row(name="рядом стоял")
    await put(session_factory, doomed, spared)
    await put(
        session_factory,
        message_row(text="его разговор", hr_id=doomed.id),
        message_row(text="чужой разговор", hr_id=spared.id),
    )

    assert await delete_hr(session, doomed.id) is True

    assert [m.text for m in (await session.scalars(select(Message))).all()] == [
        "чужой разговор"
    ]
    assert [h.name for h in (await session.scalars(select(HR))).all()] == [
        "рядом стоял"
    ]


async def test_the_vacancies_survive_without_their_hr(session, session_factory):
    """Вакансии переживают удаление HR, потеряв только ссылку на него."""
    doomed = hr_row(name="под нож")
    spared = hr_row(name="рядом стоял")
    await put(session_factory, doomed, spared)
    await put(
        session_factory,
        vacancy_row(title="была его", hr_id=doomed.id),
        vacancy_row(title="чужая", hr_id=spared.id),
    )

    await delete_hr(session, doomed.id)

    rows = (await session.scalars(select(Vacancy))).all()
    assert {v.title: v.hr_id for v in rows} == {
        "была его": None,
        "чужая": spared.id,
    }
