"""Следствия наполнения строки списка каналов.

Счётчик вакансий и отметка чёрного списка собираются отдельными запросами и
раскладываются по строкам одним проходом — вместо запроса на каждый канал.
"""

from backend.repository.channels import list_telegram_channels
from tests.dbio import put
from tests.factories import blacklist_row, channel_row, vacancy_row


async def test_the_row_carries_its_count_and_blacklist_mark(
    session, session_factory
):
    """В строке списка едут счётчик вакансий и отметка чёрного списка."""
    listed = channel_row(username="listed", title="В списке")
    switched_off = channel_row(username="off", title="Отметка снята")
    other_kind = channel_row(username="hr_like", title="Чужой род")
    await put(session_factory, listed, switched_off, other_kind)
    await put(
        session_factory,
        vacancy_row(source_channel_id=listed.id),
        blacklist_row("channel", "@listed"),
        blacklist_row("channel", "@off", active=False),
        blacklist_row("hr", "@hr_like"),
    )

    rows = {r.channel.title: r for r in await list_telegram_channels(session)}

    assert rows["В списке"].vacancy_count == 1
    assert rows["В списке"].is_blacklisted is True
    assert rows["Отметка снята"].is_blacklisted is False
    assert rows["Чужой род"].is_blacklisted is False
