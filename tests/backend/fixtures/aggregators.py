"""Строка «Поиск по сети»: миграция заводит её раз, а стенд чистит таблицы после каждого теста."""

import pytest

from backend.models import Aggregator
from tests.dbio import put
from tests.factories_aggregators import web_search_row


@pytest.fixture
async def web_search(session_factory) -> Aggregator:
    row = web_search_row(is_logged_in=True)
    await put(session_factory, row)
    return row
