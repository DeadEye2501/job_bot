"""Ведение агрегаторов: заведение, включение, вход, удаление, порядок обхода."""

from backend.models import Aggregator, Application, TrashEvent, Vacancy
from backend.repository.aggregators import (
    WEB_SEARCH_NAME, applications_of, create_aggregator, delete_aggregator, list_aggregators,
    round_sources, set_aggregator_active, set_logged_in,
)
from tests.dbio import all_rows, only_row, put
from tests.factories import vacancy_row
from tests.factories_aggregators import aggregator_row, application_row, web_search_row


async def test_an_address_is_stored_as_its_host_under_the_given_name(session):
    async with session.begin():
        row, outcome = await create_aggregator(session, "https://www.Site.test/jobs", "Пример", None)
    assert (outcome, row.host, row.name, row.is_active, row.is_logged_in) == (
        "created", "site.test", "Пример", False, False
    )


async def test_the_same_site_typed_differently_is_not_doubled(session, session_factory):
    await put(session_factory, aggregator_row(host="site.test"))
    async with session.begin():
        _, outcome = await create_aggregator(session, "site.test/", "Пример", None)
    assert outcome == "exists"
    assert len(await all_rows(session_factory, Aggregator)) == 1


async def test_an_address_without_a_host_is_refused(session):
    async with session.begin():
        _, outcome = await create_aggregator(session, "   ", "Пример", None)
    assert outcome == "invalid"


async def test_an_aggregator_without_login_cannot_be_switched_on(session, session_factory):
    row = aggregator_row(is_logged_in=False)
    await put(session_factory, row)
    async with session.begin():
        assert await set_aggregator_active(session, row.id, True) == "not_logged_in"
    assert (await only_row(session_factory, Aggregator)).is_active is False


async def test_a_lost_login_keeps_the_switch_and_leaves_the_round(session, session_factory):
    """Вход слетел — агрегатор не обходится, но после нового входа снова в деле."""
    row = aggregator_row(is_logged_in=True, is_active=True)
    await put(session_factory, row)
    async with session.begin():
        await set_logged_in(session, row.id, False)
        assert await round_sources(session) == []
    assert (await only_row(session_factory, Aggregator)).is_active is True
    async with session.begin():
        await set_logged_in(session, row.id, True)
        assert [a.id for a in await round_sources(session)] == [row.id]


async def test_applications_through_its_button_count_before_deletion(session, session_factory):
    """Отклик кнопкой агрегатора на вакансию из сети — тоже его отклик."""
    row = aggregator_row()
    await put(session_factory, row)
    vacancy = vacancy_row()
    await put(session_factory, vacancy)
    await put(session_factory, application_row(vacancy.id, aggregator_id=row.id))
    async with session.begin():
        assert await applications_of(session, row.id) == 1


async def test_web_search_cannot_be_deleted(session, web_search):
    async with session.begin():
        assert await delete_aggregator(session, web_search.id) == "protected"


async def test_a_deleted_aggregator_leaves_its_vacancies_and_applications(
    session, session_factory
):
    row = aggregator_row()
    await put(session_factory, row)
    vacancy = vacancy_row(source_aggregator_id=row.id, source_key="v/1")
    await put(session_factory, vacancy)
    await put(session_factory, application_row(vacancy.id, aggregator_id=row.id),
              TrashEvent(source_aggregator_id=row.id, source_key="v/2"))

    async with session.begin():
        assert await applications_of(session, row.id) == 1
        assert await delete_aggregator(session, row.id) == "ok"

    assert [v.source_aggregator_id for v in await all_rows(session_factory, Vacancy)] == [None]
    assert [a.aggregator_id for a in await all_rows(session_factory, Application)] == [None]
    assert [t.source_aggregator_id for t in await all_rows(session_factory, TrashEvent)] == [None]
    assert await all_rows(session_factory, Aggregator) == []


async def test_web_search_is_listed_first(session, session_factory):
    """Первым, хотя заведён позже сайта: порядок задаёт не номер строки."""
    await put(session_factory, aggregator_row(host="a.test"))
    await put(session_factory, web_search_row())
    names = [a.name for a in await list_aggregators(session)]
    assert names == [WEB_SEARCH_NAME, "HeadHunter"]


async def test_the_round_takes_active_logged_in_sites_then_web_search(
    session, session_factory, web_search
):
    await put(session_factory,
              aggregator_row(host="on.test", is_active=True, is_logged_in=True),
              aggregator_row(host="off.test", is_active=False, is_logged_in=True),
              aggregator_row(host="out.test", is_active=True, is_logged_in=False))
    async with session.begin():
        await set_aggregator_active(session, web_search.id, True)

    assert [a.host for a in await round_sources(session)] == ["on.test", None]
