"""Что база держит у резюме на агрегаторах: ссылку."""

import pytest
from sqlalchemy.exc import IntegrityError

from tests.dbio import put
from tests.factories_aggregators import aggregator_resume_row, aggregator_row


async def test_one_resume_link_twice_on_one_site_is_refused(session_factory):
    hh = aggregator_row()
    await put(session_factory, hh)
    await put(session_factory, aggregator_resume_row(hh.id, url="https://hh.ru/resume/1"))

    with pytest.raises(IntegrityError):
        await put(session_factory, aggregator_resume_row(hh.id, url="https://hh.ru/resume/1"))

