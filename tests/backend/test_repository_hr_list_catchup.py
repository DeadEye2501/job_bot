"""Следствия перечней, с которых бот догоняет пропущенное после простоя.

Перечень один и берёт всех, до кого вообще можно дотянуться в Telegram:
догон читает хвост переписки целиком, а повторы отбивает номером письма.
"""

from backend.repository.hr_list import list_hrs_for_backfill
from tests.dbio import put
from tests.factories import hr_row


async def test_backfill_covers_everyone_reachable_in_telegram(
    session, session_factory
):
    """В догоняющий разбор идут все, у кого есть хоть какой-то признак в Telegram."""
    await put(
        session_factory,
        hr_row(name="по идентификатору", telegram_user_id=111, telegram_username=None),
        hr_row(name="по нику", telegram_user_id=None, telegram_username="maria"),
        hr_row(name="без признаков", telegram_user_id=None, telegram_username=None),
    )

    got = await list_hrs_for_backfill(session)

    assert sorted(hr.name for hr in got) == sorted(["по идентификатору", "по нику"])
