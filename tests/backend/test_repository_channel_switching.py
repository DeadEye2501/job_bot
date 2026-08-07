"""Следствия управления включённостью канала.

Чёрный список сильнее пользователя: канал, попавший в него, включить нельзя ни
по одному, ни оптом. Выключить можно кого угодно — запрет односторонний.
"""

from sqlalchemy import select

from backend.models import TelegramChannel
from backend.repository import (
    deactivate_blacklisted_channels,
    is_channel_blacklisted,
    set_all_channels_active,
    set_channel_active,
)
from tests.dbio import put
from tests.factories import blacklist_row, channel_row


async def test_switching_a_missing_channel_reports_failure(session):
    """Переключить несуществующий канал нельзя, и вызов об этом сообщает."""
    assert await set_channel_active(session, 10_000, True) is False


async def test_a_channel_switches_both_ways(session, session_factory):
    """Канал включается и выключается по одному."""
    channel = channel_row(username="pyjobs", is_active=True)
    await put(session_factory, channel)

    assert await set_channel_active(session, channel.id, False) is True
    assert (await session.get(TelegramChannel, channel.id)).is_active is False

    assert await set_channel_active(session, channel.id, True) is True
    assert (await session.get(TelegramChannel, channel.id)).is_active is True


async def test_a_blacklisted_channel_is_recognised_as_such(session, session_factory):
    """Канал опознаётся как внесённый в список только по включённой отметке своего рода."""
    listed = channel_row(username="listed")
    switched_off = channel_row(username="off")
    other_kind = channel_row(username="hr_like")
    nameless = channel_row(username=None)
    await put(session_factory, listed, switched_off, other_kind, nameless)
    await put(
        session_factory,
        blacklist_row("channel", "@listed"),
        blacklist_row("channel", "@off", active=False),
        blacklist_row("hr", "@hr_like"),
    )

    assert await is_channel_blacklisted(session, listed.id) is True
    assert await is_channel_blacklisted(session, switched_off.id) is False
    assert await is_channel_blacklisted(session, other_kind.id) is False
    assert await is_channel_blacklisted(session, nameless.id) is False
    assert await is_channel_blacklisted(session, 10_000) is False


async def test_blacklisted_channels_are_switched_off_in_bulk(
    session, session_factory
):
    """Разовый проход гасит все каналы из чёрного списка и только их."""
    listed = channel_row(username="listed", is_active=True)
    clean = channel_row(username="clean", is_active=True)
    await put(session_factory, listed, clean)
    await put(session_factory, blacklist_row("channel", "@listed"))

    assert await deactivate_blacklisted_channels(session) == 1

    assert (await session.get(TelegramChannel, listed.id)).is_active is False
    assert (await session.get(TelegramChannel, clean.id)).is_active is True


async def test_an_already_off_channel_is_not_counted_twice(session, session_factory):
    """Уже выключенный канал вторым проходом не считается.

    Проход зовут при каждом изменении списка, и счётчик идёт в уведомление:
    «выключен 1 канал» после второго нажатия было бы неправдой.
    """
    listed = channel_row(username="listed", is_active=False)
    await put(session_factory, listed)
    await put(session_factory, blacklist_row("channel", "@listed"))

    assert await deactivate_blacklisted_channels(session) == 0


async def test_an_empty_blacklist_switches_nothing_off(session, session_factory):
    """При пустом чёрном списке проход не трогает ничего."""
    channel = channel_row(username="clean", is_active=True)
    await put(session_factory, channel)

    assert await deactivate_blacklisted_channels(session) == 0
    assert (await session.get(TelegramChannel, channel.id)).is_active is True


async def test_switching_everything_off_spares_nobody(session, session_factory):
    """«Выключить все» гасит и те каналы, что в чёрном списке."""
    listed = channel_row(username="listed", is_active=True)
    clean = channel_row(username="clean", is_active=True)
    await put(session_factory, listed, clean)
    await put(session_factory, blacklist_row("channel", "@listed"))

    assert await set_all_channels_active(session, False) == 2

    rows = (await session.scalars(select(TelegramChannel))).all()
    assert [ch.is_active for ch in rows] == [False, False]


async def test_switching_everything_on_skips_the_blacklisted(
    session, session_factory
):
    """«Включить все» обходит каналы из чёрного списка.

    Их нельзя включить никаким способом: иначе кнопка «включить все» была бы
    обходным путём вокруг запрета.
    """
    listed = channel_row(username="listed", is_active=False)
    clean = channel_row(username="clean", is_active=False)
    await put(session_factory, listed, clean)
    await put(session_factory, blacklist_row("channel", "@listed"))

    assert await set_all_channels_active(session, True) == 1

    assert (await session.get(TelegramChannel, listed.id)).is_active is False
    assert (await session.get(TelegramChannel, clean.id)).is_active is True
