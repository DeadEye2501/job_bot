"""Что база держит у резюме на агрегаторах: ссылку и отметку «откликаться этим»."""

import pytest
from sqlalchemy.exc import IntegrityError

from backend.models import AggregatorResume
from tests.dbio import all_rows, put
from tests.factories_aggregators import aggregator_resume_row, aggregator_row


async def test_one_resume_link_twice_on_one_site_is_refused(session_factory):
    hh = aggregator_row()
    await put(session_factory, hh)
    await put(session_factory, aggregator_resume_row(hh.id, url="https://hh.ru/resume/1"))

    with pytest.raises(IntegrityError):
        await put(session_factory, aggregator_resume_row(hh.id, url="https://hh.ru/resume/1"))


async def test_two_chosen_resumes_on_one_site_are_refused(session_factory):
    hh = aggregator_row()
    await put(session_factory, hh)
    await put(session_factory, aggregator_resume_row(hh.id, url="https://hh.ru/resume/1",
                                                     is_chosen=True))

    with pytest.raises(IntegrityError):
        await put(session_factory, aggregator_resume_row(hh.id, url="https://hh.ru/resume/2",
                                                         is_chosen=True))


async def test_each_site_has_its_own_chosen_resume(session_factory):
    hh, habr = aggregator_row(), aggregator_row(name="Хабр Карьера", host="career.habr.com")
    await put(session_factory, hh, habr)

    await put(
        session_factory,
        aggregator_resume_row(hh.id, url="https://hh.ru/resume/1", is_chosen=True),
        aggregator_resume_row(hh.id, url="https://hh.ru/resume/2"),
        aggregator_resume_row(habr.id, url="https://career.habr.com/r/1", is_chosen=True),
    )

    assert len(await all_rows(session_factory, AggregatorResume)) == 3
