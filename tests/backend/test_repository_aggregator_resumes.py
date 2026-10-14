"""Резюме агрегатора в базе: сверка со сканом, отметка «откликаться этим», удаление."""

from backend.models import Aggregator, AggregatorResume
from backend.payloads import SeenResume
from backend.repository.aggregator_resumes import (
    choose_resume, chosen_resume, drop_resume, resumes_of, sync_resumes,
)
from backend.repository.aggregators import delete_aggregator
from tests.dbio import all_rows, only_row, put
from tests.factories_aggregators import aggregator_resume_row, aggregator_row


async def _site(session_factory) -> int:
    row = aggregator_row()
    await put(session_factory, row)
    return row.id


async def _titles(session_factory, aggregator_id: int) -> list[tuple[str, bool]]:
    async with session_factory() as session:
        return [(r.title, r.is_chosen) for r in await resumes_of(session, aggregator_id)]


async def test_the_first_scan_adds_every_resume_unchosen_in_site_order(session, session_factory):
    site = await _site(session_factory)
    async with session.begin():
        await sync_resumes(session, site, [SeenResume("Дизайнер", "https://hh.ru/r/2"),
                                           SeenResume("Повар", "https://hh.ru/r/1")], can_add=True)
    assert await _titles(session_factory, site) == [("Дизайнер", False), ("Повар", False)]
    assert (await only_row(session_factory, Aggregator)).can_add_resume is True


async def test_a_resume_with_the_same_link_stays_the_same_record_with_its_mark(
    session, session_factory
):
    site = await _site(session_factory)
    kept = aggregator_resume_row(site, title="Старое", url="https://hh.ru/r/1", is_chosen=True)
    await put(session_factory, kept)
    async with session.begin():
        await sync_resumes(session, site, [SeenResume("Новое имя", "https://hh.ru/r/1")],
                           can_add=False)
    row = await only_row(session_factory, AggregatorResume)
    assert (row.id, row.title, row.is_chosen) == (kept.id, "Новое имя", True)
    assert (await only_row(session_factory, Aggregator)).can_add_resume is False


async def test_a_vanished_resume_takes_its_mark_and_another_is_not_chosen(
    session, session_factory
):
    site = await _site(session_factory)
    await put(session_factory,
              aggregator_resume_row(site, title="Ушло", url="https://hh.ru/r/1", is_chosen=True),
              aggregator_resume_row(site, title="Осталось", url="https://hh.ru/r/2", position=1))
    async with session.begin():
        await sync_resumes(session, site, [SeenResume("Осталось", "https://hh.ru/r/2"),
                                           SeenResume("Пришло", "https://hh.ru/r/3")],
                           can_add=True)
    assert await _titles(session_factory, site) == [("Осталось", False), ("Пришло", False)]
    async with session_factory() as fresh:
        assert await chosen_resume(fresh, site) is None


async def test_known_resumes_follow_the_site_when_it_reorders_them(session, session_factory):
    site = await _site(session_factory)
    await put(session_factory,
              aggregator_resume_row(site, title="Первое", url="https://hh.ru/r/1", position=0),
              aggregator_resume_row(site, title="Второе", url="https://hh.ru/r/2", position=1))
    async with session.begin():
        await sync_resumes(session, site, [SeenResume("Второе", "https://hh.ru/r/2"),
                                           SeenResume("Первое", "https://hh.ru/r/1")],
                           can_add=True)
    assert await _titles(session_factory, site) == [("Второе", False), ("Первое", False)]


async def test_a_link_reported_twice_is_one_resume_at_its_first_place(session, session_factory):
    site = await _site(session_factory)
    async with session.begin():
        await sync_resumes(session, site, [SeenResume("Первое", "https://hh.ru/r/1"),
                                           SeenResume("Второе", "https://hh.ru/r/2"),
                                           SeenResume("Повтор", "https://hh.ru/r/1")],
                           can_add=True)
    assert await _titles(session_factory, site) == [("Первое", False), ("Второе", False)]


async def test_a_scan_touches_only_its_own_site(session, session_factory):
    site = await _site(session_factory)
    other = aggregator_row(host="other.test")
    await put(session_factory, other)
    await put(session_factory, aggregator_resume_row(other.id, url="https://other.test/r/1"))
    async with session.begin():
        await sync_resumes(session, site, [], can_add=True)
    assert await _titles(session_factory, other.id) == [("Разработчик", False)]


async def test_choosing_a_resume_moves_the_mark(session, session_factory):
    site = await _site(session_factory)
    first = aggregator_resume_row(site, url="https://hh.ru/r/1", is_chosen=True)
    second = aggregator_resume_row(site, title="Другое", url="https://hh.ru/r/2", position=1)
    await put(session_factory, first, second)
    async with session.begin():
        await choose_resume(session, site, second.id)
    async with session_factory() as fresh:
        assert (await chosen_resume(fresh, site)).id == second.id
    assert await _titles(session_factory, site) == [("Разработчик", False), ("Другое", True)]


async def test_choosing_on_one_site_keeps_the_mark_on_another(session, session_factory):
    site = await _site(session_factory)
    other = aggregator_row(host="other.test")
    await put(session_factory, other)
    mine = aggregator_resume_row(site, url="https://hh.ru/r/1")
    await put(session_factory, mine,
              aggregator_resume_row(other.id, url="https://other.test/r/1", is_chosen=True))
    async with session.begin():
        await choose_resume(session, site, mine.id)
    assert await _titles(session_factory, other.id) == [("Разработчик", True)]
    async with session_factory() as fresh:
        assert (await chosen_resume(fresh, site)).id == mine.id


async def test_a_dropped_resume_leaves_the_site_without_a_chosen_one(session, session_factory):
    site = await _site(session_factory)
    gone = aggregator_resume_row(site, url="https://hh.ru/r/1", is_chosen=True)
    await put(session_factory, gone,
              aggregator_resume_row(site, title="Другое", url="https://hh.ru/r/2", position=1))
    async with session.begin():
        await drop_resume(session, gone.id)
    assert await _titles(session_factory, site) == [("Другое", False)]


async def test_a_deleted_aggregator_takes_its_resumes_with_it(session, session_factory):
    site = await _site(session_factory)
    await put(session_factory, aggregator_resume_row(site, is_chosen=True))
    async with session.begin():
        assert await delete_aggregator(session, site) == "ok"
    assert await all_rows(session_factory, AggregatorResume) == []
    assert await all_rows(session_factory, Aggregator) == []
