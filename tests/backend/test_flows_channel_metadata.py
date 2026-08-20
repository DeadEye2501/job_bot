"""Следствия обновления названий и картинок каналов.

Сводка идёт до тяжёлого разбора сообщений: одно обращение на канал, и окно
получает свежие названия за десятки секунд вместо десятков минут. Идёт она
последовательно нарочно — соединение Pyrogram одно, и параллельные обращения
упираются в предел частоты.

Название переписывается при каждом изменении, картинка — только если своей у
канала ещё нет: пользователь мог поставить её руками. Канал, до которого не
достучались, пропускается: из-за одного недоступного остальные обновиться
должны.
"""

import logging

from backend.flows import channels
from backend.models import TelegramChannel
from tests.dbio import all_rows, only_row, put
from tests.factories import channel_row
from tests.fakes.telegram import FakeTelegramClient, chat, photo


async def _channels(session_factory, *rows):
    """Заводит каналы и отдаёт их сохранённые строки."""
    await put(session_factory, *rows)
    return await all_rows(session_factory, TelegramChannel)


async def test_a_changed_title_is_written_down(make_pipeline, session_factory):
    """Изменившееся название канала переписывается."""
    saved = await _channels(session_factory, channel_row(username="jobs", title="Было"))
    client = FakeTelegramClient(chats={"jobs": chat(title="Стало")})
    pipeline = await make_pipeline(client)

    await channels.refresh_channel_metadata(pipeline, saved)

    assert (await only_row(session_factory, TelegramChannel)).title == "Стало"


async def test_an_unchanged_title_is_left_alone(make_pipeline, session_factory):
    """Совпавшее название не переписывается: менять нечего."""
    saved = await _channels(session_factory, channel_row(username="jobs", title="Работа"))
    client = FakeTelegramClient(chats={"jobs": chat(title="Работа")})
    pipeline = await make_pipeline(client)
    heard: list[int] = []
    pipeline.on_channels_changed = lambda: heard.append(1)

    await channels.refresh_channel_metadata(pipeline, saved)

    assert heard == []


async def test_a_channel_without_a_picture_gets_one(make_pipeline, session_factory):
    """Каналу без картинки подтягивается его аватар."""
    saved = await _channels(
        session_factory, channel_row(username="jobs", title="Работа", avatar=None)
    )
    client = FakeTelegramClient(
        chats={"jobs": chat(title="Работа", photo=photo(big_file_id="кар"))},
        avatar=b"\x89PNG",
    )
    pipeline = await make_pipeline(client)

    await channels.refresh_channel_metadata(pipeline, saved)

    assert (await only_row(session_factory, TelegramChannel)).avatar == b"\x89PNG"


async def test_a_channel_that_has_a_picture_keeps_it(make_pipeline, session_factory):
    """Канал со своей картинкой чужую не берёт.

    Пользователь мог поставить её руками; перетирать её на каждом обходе
    значило бы отменять его выбор раз в полчаса.
    """
    saved = await _channels(
        session_factory, channel_row(username="jobs", title="Работа", avatar=b"\x89OWN")
    )
    client = FakeTelegramClient(
        chats={"jobs": chat(title="Работа", photo=photo(big_file_id="кар"))},
        avatar=b"\x89PNG",
    )
    pipeline = await make_pipeline(client)

    await channels.refresh_channel_metadata(pipeline, saved)

    assert (await only_row(session_factory, TelegramChannel)).avatar == b"\x89OWN"
    assert client.download_calls == []


async def test_a_channel_telegram_does_not_know_does_not_stop_the_sweep(
    make_pipeline, session_factory
):
    """Неизвестный Telegram канал сводку не обрывает: соседние обновляются.

    Каналы закрываются, переименовываются и пропадают; из-за одного
    такого не обновить остальные было бы дорого.
    """
    saved = await _channels(
        session_factory,
        channel_row(username="broken", title="Было"),
        channel_row(username="jobs", title="Было"),
    )
    client = FakeTelegramClient(chats={"jobs": chat(title="Стало")})
    pipeline = await make_pipeline(client)

    await channels.refresh_channel_metadata(pipeline, saved)

    titles = {c.username: c.title for c in await all_rows(session_factory, TelegramChannel)}
    assert titles == {"broken": "Было", "jobs": "Стало"}


async def test_a_failed_request_does_not_stop_the_sweep(
    make_pipeline, session_factory
):
    """Сорвавшееся обращение к Telegram сводку тоже не обрывает.

    Закрытый канал отвечает не отсутствием, а отказом; без перехвата он
    уронил бы обновление названий у всех, кто дальше по списку.
    """
    saved = await _channels(
        session_factory,
        channel_row(username="broken", title="Было"),
        channel_row(username="jobs", title="Было"),
    )
    client = FakeTelegramClient(
        chats={"jobs": chat(title="Стало")},
        fails={"get_chat": [OSError("канал закрыт"), None]},
    )
    pipeline = await make_pipeline(client)

    await channels.refresh_channel_metadata(pipeline, saved)

    titles = {c.username: c.title for c in await all_rows(session_factory, TelegramChannel)}
    assert titles == {"broken": "Было", "jobs": "Стало"}


async def test_a_failed_request_leaves_its_trace_in_the_log(
    make_pipeline, session_factory, caplog
):
    """Пропущенный канал оставляет в журнале трассировку отказа.

    Наружу пропуск не виден вовсе: название остаётся прежним, а сводка идёт
    дальше. Узнать, почему канал перестал обновляться, можно только отсюда.
    """
    saved = await _channels(session_factory, channel_row(username="broken"))
    pipeline = await make_pipeline(
        FakeTelegramClient(fails={"get_chat": OSError("канал закрыт")})
    )

    with caplog.at_level(logging.WARNING):
        await channels.refresh_channel_metadata(pipeline, saved)

    assert "Traceback (most recent call last)" in caplog.text
    assert "OSError: канал закрыт" in caplog.text


async def test_a_write_that_broke_does_not_break_the_sweep(
    make_pipeline, session_factory, monkeypatch, caplog
):
    """Сорвавшаяся запись сводки броском наружу не выходит.

    Сводка — дело второстепенное: названия и картинки. Уронив зовущего, она
    уносит с собой весь обход каналов, то есть все сегодняшние объявления, —
    а занятая база это обычное дело, соседняя сделка идёт своим чередом.
    """
    saved = await _channels(session_factory, channel_row(username="jobs", title="Было"))
    client = FakeTelegramClient(chats={"jobs": chat(title="Стало")})
    pipeline = await make_pipeline(client)
    heard: list[int] = []
    pipeline.on_channels_changed = lambda: heard.append(1)

    async def busy(pipeline, title_updates, avatar_updates):
        raise OSError("database is locked")

    monkeypatch.setattr(channels, "_store_metadata", busy)

    with caplog.at_level(logging.ERROR):
        await channels.refresh_channel_metadata(pipeline, saved)

    assert heard == []
    assert "OSError: database is locked" in caplog.text


async def test_a_channel_deleted_mid_sweep_is_skipped(
    make_pipeline, session_factory
):
    """Канал, удалённый посреди сводки, пропускается при записи.

    Сводка идёт минуты, и пользователь волен удалить канал прямо в это
    время; воскрешать его записью незачем.
    """
    saved = await _channels(session_factory, channel_row(username="jobs", title="Было"))
    client = FakeTelegramClient(chats={"jobs": chat(title="Стало")})
    pipeline = await make_pipeline(client)
    async with session_factory() as session:
        row = await session.get(TelegramChannel, saved[0].id)
        await session.delete(row)
        await session.commit()

    await channels.refresh_channel_metadata(pipeline, saved)

    assert await all_rows(session_factory, TelegramChannel) == []


async def test_the_window_hears_about_the_fresh_names(make_pipeline, session_factory):
    """Окно узнаёт о свежих названиях и перечитывает список каналов."""
    saved = await _channels(session_factory, channel_row(username="jobs", title="Было"))
    client = FakeTelegramClient(chats={"jobs": chat(title="Стало")})
    pipeline = await make_pipeline(client)
    heard: list[int] = []
    pipeline.on_channels_changed = lambda: heard.append(1)

    await channels.refresh_channel_metadata(pipeline, saved)

    assert heard == [1]


async def test_a_broken_window_hook_does_not_undo_the_names(
    make_pipeline, session_factory
):
    """Сломанное оповещение окна свежие названия не отменяет."""
    saved = await _channels(session_factory, channel_row(username="jobs", title="Было"))
    client = FakeTelegramClient(chats={"jobs": chat(title="Стало")})
    pipeline = await make_pipeline(client)

    def broken():
        raise RuntimeError("окно")

    pipeline.on_channels_changed = broken

    await channels.refresh_channel_metadata(pipeline, saved)

    assert (await only_row(session_factory, TelegramChannel)).title == "Стало"


async def test_refreshing_by_number_reaches_the_named_channels(
    make_pipeline, session_factory
):
    """Обновление по номерам достаёт названные каналы, а не все подряд.

    Так окно обновляет только что добавленный канал, не дожидаясь
    получасового обхода.
    """
    saved = await _channels(
        session_factory,
        channel_row(username="jobs", title="Было"),
        channel_row(username="other", title="Было"),
    )
    client = FakeTelegramClient(
        chats={"jobs": chat(title="Стало"), "other": chat(title="Тоже стало")}
    )
    pipeline = await make_pipeline(client)

    await pipeline.refresh_channel_metadata_for_ids([saved[0].id])

    titles = {c.username: c.title for c in await all_rows(session_factory, TelegramChannel)}
    assert titles == {"jobs": "Стало", "other": "Было"}


async def test_refreshing_by_number_skips_a_channel_without_a_name(
    make_pipeline, session_factory
):
    """Обновление по номерам о канале без имени Telegram не спрашивает.

    Спрашивать нечем: ник — единственный адрес. Беда была прикрыта
    случайно — обращение падало внутри широкого перехвата, и канал молча
    выпадал из сводки одной строкой в журнале.
    """
    saved = await _channels(
        session_factory,
        channel_row(username=None, title="Было"),
        channel_row(username="", title="Было"),
    )
    client = FakeTelegramClient()
    pipeline = await make_pipeline(client)

    await pipeline.refresh_channel_metadata_for_ids([row.id for row in saved])

    assert client.get_chat_calls == []


async def test_refreshing_nothing_asks_telegram_nothing(
    make_pipeline
):
    """Обновление пустого списка Telegram не беспокоит."""
    client = FakeTelegramClient()
    pipeline = await make_pipeline(client)

    await pipeline.refresh_channel_metadata_for_ids([])

    assert client.get_chat_calls == []
