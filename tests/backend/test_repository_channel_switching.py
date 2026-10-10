"""Следствия управления включённостью канала.

Чёрный список сильнее пользователя: канал, попавший в него, включить нельзя.
Выключить можно кого угодно — запрет односторонний.
"""

from backend.models import TelegramChannel
from backend.repository.channels import deactivate_blacklisted_channels, is_channel_blacklisted, set_channel_active
from tests.dbio import put
from tests.factories import (
    blacklist_row,
    channel_marks,
    channel_row,
    marked_channels,
)


async def _listed_and_clean(session_factory, *, is_active: bool):
    """Два канала одной включённости: один внесён в чёрный список, второй нет.

    Чистый канал стоит парой нарочно: видно, что проход разбирает каналы по
    отметке, а не по счёту, — без пары он зеленел бы и на «трогаем всех подряд».
    """
    listed = channel_row(username="listed", is_active=is_active)
    clean = channel_row(username="clean", is_active=is_active)
    await put(session_factory, listed, clean)
    await put(session_factory, blacklist_row("channel", "@listed"))
    return listed, clean


async def test_switching_a_missing_channel_reports_failure(session):
    """Переключить несуществующий канал нельзя, и вызов об этом сообщает."""
    assert await set_channel_active(session, 10_000, True) == "missing"


async def test_a_channel_switches_both_ways(session, session_factory):
    """Канал включается и выключается по одному."""
    channel = channel_row(username="pyjobs", is_active=True)
    await put(session_factory, channel)

    assert await set_channel_active(session, channel.id, False) == "ok"
    assert (await session.get(TelegramChannel, channel.id)).is_active is False

    assert await set_channel_active(session, channel.id, True) == "ok"
    assert (await session.get(TelegramChannel, channel.id)).is_active is True


async def test_a_blacklisted_channel_is_not_switched_on_but_is_switched_off(
    session, session_factory
):
    """Запрет стоит в самой записи, как у агрегатора: включение, которое про
    отметку ничего не знает, её не отменит."""
    listed, _ = await _listed_and_clean(session_factory, is_active=True)

    assert await set_channel_active(session, listed.id, False) == "ok"
    assert await set_channel_active(session, listed.id, True) == "blacklisted"
    assert (await session.get(TelegramChannel, listed.id)).is_active is False


async def test_a_blacklisted_channel_is_recognised_as_such(session, session_factory):
    """Канал опознаётся как внесённый в список только по включённой отметке своего рода."""
    listed, switched_off, other_kind = marked_channels()
    nameless = channel_row(username=None)
    await put(session_factory, listed, switched_off, other_kind, nameless)
    await put(session_factory, *channel_marks())

    assert await is_channel_blacklisted(session, listed.id) is True
    assert await is_channel_blacklisted(session, switched_off.id) is False
    assert await is_channel_blacklisted(session, other_kind.id) is False
    assert await is_channel_blacklisted(session, nameless.id) is False
    assert await is_channel_blacklisted(session, 10_000) is False


async def test_blacklisted_channels_are_switched_off_in_bulk(
    session, session_factory
):
    """Разовый проход гасит все каналы из чёрного списка и только их."""
    listed, clean = await _listed_and_clean(session_factory, is_active=True)

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
