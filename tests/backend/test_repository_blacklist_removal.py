"""Следствия удаления строки чёрного списка.

На эту таблицу никто не ссылается, поэтому удаление простое — но соседние
строки оно задевать не должно.
"""

from sqlalchemy import select

from backend.models import Blacklist
from backend.repository.blacklist import delete_blacklist
from tests.dbio import put
from tests.factories import blacklist_row


async def test_deleting_a_missing_row_reports_failure(session):
    """Удалить несуществующую строку нельзя, и вызов об этом сообщает."""
    assert await delete_blacklist(session, 10_000) is False


async def test_deleting_a_row_removes_only_that_one(session, session_factory):
    """Удаление уносит одну строку, не задевая соседних."""
    doomed = blacklist_row("hr", "@maria")
    spared = blacklist_row("hr", "@olga")
    await put(session_factory, doomed, spared)

    assert await delete_blacklist(session, doomed.id) is True

    assert [r.value for r in (await session.scalars(select(Blacklist))).all()] == [
        "@olga"
    ]
