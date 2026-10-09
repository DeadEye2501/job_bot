"""Строка «Поиск по сети»: миграция заводит её раз, а стенд чистит таблицы после каждого теста."""

import pytest

from backend.models import Aggregator
from backend.repository.aggregators import WEB_SEARCH_NAME
from tests.dbio import put
from tests.factories_aggregators import aggregator_row


@pytest.fixture
async def web_search(session_factory) -> Aggregator:
    row = aggregator_row(name=WEB_SEARCH_NAME, host=None, is_logged_in=True)
    await put(session_factory, row)
    return row
