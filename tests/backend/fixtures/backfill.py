"""Обстановка для проверок догона переписки: собеседник и прогон догона."""

import pytest

from backend.flows.dm import DmHelpers
from backend.flows.dm_backfill import (
    DmHooks,
    backfill_hr_dm_history,
    catch_up_missed_dms,
)
from backend.models import HR
from tests.dbio import only_row, put
from tests.factories import hr_row
from tests.fakes.telegram_objects import incoming, my_dm


def theirs(msg_id, text):
    """Сообщение от собеседника."""
    return incoming(id=msg_id, text=text, outgoing=False)


def ours(msg_id, text, *, photo=None):
    """Своё сообщение, отправленное из другого клиента."""
    return my_dm(msg_id=msg_id, text=text, photo=photo)


def _helpers(client, session_factory, **extra) -> DmHelpers:
    """Сотрудники догона на стенде: модель молчит, разбор откладывается.

    Названное поимённо перебивает умолчание: проверке накопителя нужен свой
    планировщик, остальным — любой непустой, лишь бы разбор не пошёл в модель.
    """
    fields = {
        "session_factory": session_factory,
        "lm_chat_model": "qwen",
        "client": client,
        "schedule_classification": lambda *args: None,
    }
    fields.update(extra)
    return DmHelpers(**fields)


async def catch_up(client, hr, session_factory, *, hooks=None, **kwargs):
    """Догоняет переписку с одним HR."""
    await backfill_hr_dm_history(
        hr,
        _helpers(client, session_factory),
        hooks or DmHooks(),
        backfill_limit=50,
        **kwargs,
    )


async def catch_up_everyone(
    client, session_factory, *, hooks=None, dialogs=None, **kwargs
):
    """Догоняет переписку по списку переписок; неизвестный (`None`) — по всем.

    Отличается от `catch_up` тем, что идёт настоящей дорогой обхода: отметку
    «что у нас было до прохода» снимает именно она, и сверка удалённого без
    неё работает вслепую.
    """
    await catch_up_missed_dms(
        _helpers(client, session_factory, **kwargs),
        hooks or DmHooks(),
        backfill_limit=50,
        dialogs=dialogs,
    )


@pytest.fixture
async def known_hr(session_factory):
    """Сохранённый HR с номером собеседника."""
    await put(session_factory, hr_row(telegram_user_id=777))
    return await only_row(session_factory, HR)
