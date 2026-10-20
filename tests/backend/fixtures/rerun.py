"""Обстановка для проверок повторного прогона вакансии.

Своим модулем, а не в теле проверок: прогон разошёлся на два предмета — сам
разбор заново и отпечаток, — и обстановка у обоих одна: вакансия с сохранённым
текстом, канал-источник и конвейер, у которого разбор подставной.
"""

import pytest

from backend.flows import embeddings as embeddings_mod
from backend.models import TelegramChannel, Vacancy
from tests.backend.fixtures.parse_stub import parse_into
from tests.dbio import only_row, put
from tests.factories import channel_row, vacancy_row
@pytest.fixture
async def rerunning(make_pipeline, session_factory):
    """Вакансия с сохранённым текстом и каналом-источником."""
    await put(session_factory, channel_row(username="jobs"))
    channel = await only_row(session_factory, TelegramChannel)
    await put(
        session_factory,
        vacancy_row(
            title="старый разбор",
            raw_text="сохранённый текст",
            source_channel_id=channel.id,
            source_msg_id=42,
        ),
    )
    vacancy = await only_row(session_factory, Vacancy)
    return session_factory, vacancy, make_pipeline


async def prepare(monkeypatch, make_pipeline, client):
    """Конвейер с подставным разбором и без перезагрузки настроек."""
    pipeline = await make_pipeline(client)
    pipeline.parsed = []
    pipeline.parse_done = True

    async def reload():
        pipeline.parsed.append("настройки")

    async def embed(pipeline, text, what):
        pipeline.embedded.append(text)
        return pipeline.vector

    pipeline.embedded = []
    pipeline.vector = [0.5, 0.25]

    monkeypatch.setattr(embeddings_mod, "embed_text", embed)
    parse_into(monkeypatch, pipeline.parsed, done=lambda: pipeline.parse_done)
    pipeline.reload_resources = reload
    return pipeline
