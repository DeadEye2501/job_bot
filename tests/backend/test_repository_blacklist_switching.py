"""Следствия гашения и включения строки чёрного списка.

Строку не удаляют, а гасят: решение остаётся в истории, но на поведение не
влияет. Обратный ход тоже возможен.
"""

from backend.models import Blacklist
from backend.repository import set_blacklist_active
from tests.dbio import put
from tests.factories import blacklist_row


async def test_switching_a_missing_row_reports_failure(session):
    """Погасить несуществующую строку нельзя, и вызов об этом сообщает."""
    assert await set_blacklist_active(session, 10_000, False) is False


async def test_a_row_switches_both_ways(session, session_factory):
    """Строка гасится и включается обратно."""
    row = blacklist_row("hr", "@maria", active=True)
    await put(session_factory, row)

    assert await set_blacklist_active(session, row.id, False) is True
    assert (await session.get(Blacklist, row.id)).active is False

    assert await set_blacklist_active(session, row.id, True) is True
    assert (await session.get(Blacklist, row.id)).active is True
