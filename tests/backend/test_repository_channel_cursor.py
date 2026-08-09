"""Следствия сброса отметки разобранного у канала.

Отметка хранит номер последнего разобранного сообщения. Сброс заставляет
следующий обход перечитать недавнюю историю заново.
"""

from backend.models import TelegramChannel
from backend.repository.channels import reset_channel_cursor
from tests.dbio import put
from tests.factories import channel_row


async def test_resetting_the_cursor_of_a_missing_channel_reports_failure(session):
    """Сбросить отметку у несуществующего канала нельзя."""
    assert await reset_channel_cursor(session, 10_000) is False


async def test_resetting_the_cursor_makes_the_next_poll_start_over(
    session, session_factory
):
    """Сброс отметки стирает номер последнего разобранного сообщения."""
    channel = channel_row(username="pyjobs", last_processed_msg_id=500)
    await put(session_factory, channel)

    assert await reset_channel_cursor(session, channel.id) is True

    assert (await session.get(TelegramChannel, channel.id)).last_processed_msg_id is None
