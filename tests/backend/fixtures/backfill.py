"""Обстановка для проверок догона переписки: собеседник и прогон догона."""

import pytest

from backend.flows.dm_backfill import backfill_hr_dm_history, catch_up_missed_dms
from backend.models import HR
from tests.dbio import only_row, put
from tests.factories import hr_row
from tests.fakes.telegram import incoming, outgoing


def theirs(msg_id, text):
    """Сообщение от собеседника."""
    return incoming(id=msg_id, text=text, outgoing=False)


def ours(msg_id, text, *, photo=None):
    """Своё сообщение, отправленное из другого клиента."""
    return outgoing(id=msg_id, text=text, photo=photo)


async def catch_up(client, hr, session_factory, **kwargs):
    """Догоняет переписку с одним HR."""
    await backfill_hr_dm_history(
        client,
        hr,
        None,
        "qwen",
        session_factory,
        backfill_limit=50,
        schedule_classification=lambda *args: None,
        **kwargs,
    )


async def catch_up_everyone(client, session_factory):
    """Догоняет переписку по всем известным собеседникам.

    Отличается от `catch_up` тем, что идёт настоящей дорогой обхода: отметку
    «что у нас было до прохода» снимает именно она, и сверка удалённого без
    неё работает вслепую.
    """
    await catch_up_missed_dms(
        client,
        None,
        "qwen",
        session_factory,
        50,
        schedule_classification=lambda *args: None,
    )


@pytest.fixture
async def known_hr(session_factory):
    """Сохранённый HR с номером собеседника."""
    await put(session_factory, hr_row(telegram_user_id=777))
    return await only_row(session_factory, HR)
