"""Следствия удаления компании.

Вакансии переживают удаление, потеряв только ссылку: вакансия принадлежит
каналу, откуда пришла, а не ярлыку компании, привязанному к ней позже.
"""

from sqlalchemy import select

from backend.models import Company, Vacancy
from backend.repository import delete_company
from tests.dbio import put
from tests.factories import company_row, vacancy_row


async def test_deleting_a_missing_company_reports_failure(session):
    """Удалить несуществующую компанию нельзя, и вызов об этом сообщает."""
    assert await delete_company(session, 10_000) is False


async def test_the_vacancies_survive_without_their_company(session, session_factory):
    """Вакансии переживают удаление компании, потеряв только ссылку на неё.

    Вакансия принадлежит каналу, откуда пришла, а не ярлыку компании,
    который мы к ней привязали.
    """
    doomed = company_row(name="под нож")
    spared = company_row(name="рядом стояла")
    await put(session_factory, doomed, spared)
    await put(
        session_factory,
        vacancy_row(title="была её", company_id=doomed.id),
        vacancy_row(title="чужая", company_id=spared.id),
    )

    assert await delete_company(session, doomed.id) is True

    rows = (await session.scalars(select(Vacancy))).all()
    assert {v.title: v.company_id for v in rows} == {
        "была её": None,
        "чужая": spared.id,
    }
    assert [c.name for c in (await session.scalars(select(Company))).all()] == [
        "рядом стояла"
    ]
