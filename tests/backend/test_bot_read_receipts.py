"""Следствия отметок о прочтении — своих и чужих.

Своя ставится, когда пользователь открыл переписку в окне: она гасит счётчик
непрочитанного и уходит в Telegram, чтобы телефон и настольный клиент тоже
перестали её подсвечивать.

Чужая приходит сервером, когда HR прочитал наши письма, и переводит галочку
в двойную. Такие оповещения сыплются на каждое событие сервера, поэтому
чужие отсеиваются первой же строкой — до всякого обращения к базе.

Выключенный бот не делает ни того ни другого: «выключен» означает, что он не
трогает ни базу, ни Telegram.
"""

from datetime import datetime, timezone

from pyrogram.raw.types import (
    PeerChat,
    PeerUser,
    UpdateReadHistoryInbox,
    UpdateReadHistoryOutbox,
)

from backend.models import BotMode, Message
from tests.dbio import all_rows, only_row, put
from tests.factories import message_row
from tests.fakes.telegram import FakeTelegramClient


def _outbox_read(user_id: int, max_id: int):
    """Оповещение «собеседник прочитал наши сообщения до такого-то»."""
    return UpdateReadHistoryOutbox(
        peer=PeerUser(user_id=user_id), max_id=max_id, pts=1, pts_count=1
    )


async def test_opening_a_chat_marks_its_incoming_messages_read(
    chatting, session_factory
):
    """Открытая переписка гасит непрочитанное у входящих."""
    bot, client, hr = await chatting()
    await put(
        session_factory,
        message_row(hr_id=hr.id, is_incoming=True, read_at=None),
        message_row(hr_id=hr.id, is_incoming=True, read_at=None, tg_message_id=2),
    )

    assert await bot.mark_hr_chat_read(hr.id) == 2

    assert all(m.read_at is not None for m in await all_rows(session_factory, Message))


async def test_our_own_messages_are_not_marked_read(chatting, session_factory):
    """Свои же письма прочитанными не помечаются.

    Отметка означает «мы прочли присланное»; на исходящих её ставит HR, и
    подделать её значило бы показать двойную галочку без основания.
    """
    bot, client, hr = await chatting()
    await put(
        session_factory,
        message_row(hr_id=hr.id, is_incoming=False, read_at=None),
    )

    assert await bot.mark_hr_chat_read(hr.id) == 0

    assert (await only_row(session_factory, Message)).read_at is None


async def test_an_already_read_message_is_not_touched_again(
    chatting, session_factory
):
    """Уже прочитанное второй раз не помечается.

    Иначе метка времени ползла бы вперёд при каждом открытии переписки, и
    «когда прочитали» перестало бы что-либо значить.
    """
    first_read = datetime(2026, 1, 1, 9, 0, tzinfo=timezone.utc)
    bot, client, hr = await chatting()
    await put(
        session_factory,
        message_row(hr_id=hr.id, is_incoming=True, read_at=first_read),
    )

    assert await bot.mark_hr_chat_read(hr.id) == 0

    saved = await only_row(session_factory, Message)
    assert saved.read_at.replace(tzinfo=timezone.utc) == first_read


async def test_the_read_mark_goes_to_telegram_too(chatting, session_factory):
    """Отметка уходит и в Telegram: телефон тоже гасит подсветку."""
    bot, client, hr = await chatting(telegram_user_id=777)
    await put(session_factory, message_row(hr_id=hr.id, is_incoming=True, read_at=None))

    await bot.mark_hr_chat_read(hr.id)

    assert client.read_calls == [777]


async def test_nothing_new_means_nothing_sent_to_telegram(chatting, session_factory):
    """Когда гасить нечего, Telegram не беспокоят."""
    bot, client, hr = await chatting(telegram_user_id=777)

    assert await bot.mark_hr_chat_read(hr.id) == 0
    assert client.read_calls == []


async def test_a_failed_telegram_mark_keeps_the_local_one(chatting, session_factory):
    """Сбой отметки в Telegram местную не отменяет.

    Счётчик непрочитанного в окне важнее подсветки на телефоне, и
    откатывать первое из-за второго было бы обменом не в ту сторону.
    """
    bot, client, hr = await chatting(
        client=FakeTelegramClient(fails={"read_chat_history": OSError("сеть")}),
        telegram_user_id=777,
    )
    await put(session_factory, message_row(hr_id=hr.id, is_incoming=True, read_at=None))

    assert await bot.mark_hr_chat_read(hr.id) == 1
    assert (await only_row(session_factory, Message)).read_at is not None


async def test_a_switched_off_bot_marks_nothing_read(chatting, session_factory):
    """Выключенный бот не гасит непрочитанное и не пишет в Telegram."""
    bot, client, hr = await chatting(mode=BotMode.OFF, telegram_user_id=777)
    await put(session_factory, message_row(hr_id=hr.id, is_incoming=True, read_at=None))

    assert await bot.mark_hr_chat_read(hr.id) == 0

    assert (await only_row(session_factory, Message)).read_at is None
    assert client.read_calls == []


async def test_a_missing_hr_marks_nothing(chatting, session_factory):
    """Отметка по несуществующему HR ничего не делает и не падает."""
    bot, client, _ = await chatting()

    assert await bot.mark_hr_chat_read(404) == 0


async def test_an_hr_read_receipt_flips_our_messages_to_read(
    chatting, session_factory
):
    """Прочтение со стороны HR переводит наши письма в прочитанные."""
    bot, client, hr = await chatting(telegram_user_id=777)
    await put(
        session_factory,
        message_row(hr_id=hr.id, is_incoming=False, tg_message_id=10, read_at=None),
    )

    await bot._on_raw_update(client, _outbox_read(777, 10), {}, {})

    assert (await only_row(session_factory, Message)).read_at is not None


async def test_a_receipt_does_not_reach_past_the_message_it_names(
    chatting, session_factory
):
    """Отметка не заходит дальше названного сообщения.

    HR прочитал переписку до какого-то места; пометить прочитанным то,
    что пришло после, значило бы показать двойную галочку зря.
    """
    bot, client, hr = await chatting(telegram_user_id=777)
    await put(
        session_factory,
        message_row(hr_id=hr.id, is_incoming=False, tg_message_id=20, read_at=None),
        message_row(hr_id=hr.id, is_incoming=False, tg_message_id=10, read_at=None),
    )

    await bot._on_raw_update(client, _outbox_read(777, 10), {}, {})

    by_id = {m.tg_message_id: m for m in await all_rows(session_factory, Message)}
    assert by_id[10].read_at is not None
    assert by_id[20].read_at is None


async def test_a_receipt_leaves_incoming_messages_alone(chatting, session_factory):
    """Отметка HR входящих не трогает: их читаем мы, а не он."""
    bot, client, hr = await chatting(telegram_user_id=777)
    await put(
        session_factory,
        message_row(hr_id=hr.id, is_incoming=True, tg_message_id=10, read_at=None),
    )

    await bot._on_raw_update(client, _outbox_read(777, 10), {}, {})

    assert (await only_row(session_factory, Message)).read_at is None


async def test_a_receipt_from_a_stranger_changes_nothing(chatting, session_factory):
    """Отметка от незнакомого собеседника ничего не меняет."""
    bot, client, hr = await chatting(telegram_user_id=777)
    await put(
        session_factory,
        message_row(hr_id=hr.id, is_incoming=False, tg_message_id=10, read_at=None),
    )

    await bot._on_raw_update(client, _outbox_read(999, 10), {}, {})

    assert (await only_row(session_factory, Message)).read_at is None


async def test_a_group_receipt_is_ignored(chatting, session_factory):
    """Отметка из группового чата пропускается: HR-переписка личная."""
    bot, client, hr = await chatting(telegram_user_id=777)
    await put(
        session_factory,
        message_row(hr_id=hr.id, is_incoming=False, tg_message_id=10, read_at=None),
    )
    update = UpdateReadHistoryOutbox(
        peer=PeerChat(chat_id=777), max_id=10, pts=1, pts_count=1
    )

    await bot._on_raw_update(client, update, {}, {})

    assert (await only_row(session_factory, Message)).read_at is None


async def test_a_switched_off_bot_ignores_receipts_too(chatting, session_factory):
    """Выключенный бот отметки от HR тоже не разбирает."""
    bot, client, hr = await chatting(mode=BotMode.OFF, telegram_user_id=777)
    await put(
        session_factory,
        message_row(hr_id=hr.id, is_incoming=False, tg_message_id=10, read_at=None),
    )

    await bot._on_raw_update(client, _outbox_read(777, 10), {}, {})

    assert (await only_row(session_factory, Message)).read_at is None


async def test_the_window_hears_about_a_receipt(chatting, session_factory):
    """Окно узнаёт о прочтении: галочка в открытой переписке меняется сразу.

    Оповещение несёт номер HR и границу прочитанного — этого хватает,
    чтобы перекрасить уже показанные строки, не перечитывая переписку.
    """
    bot, client, hr = await chatting(telegram_user_id=777)
    await put(
        session_factory,
        message_row(hr_id=hr.id, is_incoming=False, tg_message_id=10, read_at=None),
    )
    heard: list[tuple] = []
    bot.on_hr_read = lambda hr_id, max_id: heard.append((hr_id, max_id))

    await bot._on_raw_update(client, _outbox_read(777, 10), {}, {})

    assert heard == [(hr.id, 10)]


async def test_the_window_is_not_told_when_nothing_changed(chatting, session_factory):
    """Когда менять нечего, окно не дёргают.

    Повторные отметки от Telegram приходят часто; каждая из них
    перерисовывала бы переписку впустую.
    """
    bot, client, hr = await chatting(telegram_user_id=777)
    heard: list[tuple] = []
    bot.on_hr_read = lambda hr_id, max_id: heard.append((hr_id, max_id))

    await bot._on_raw_update(client, _outbox_read(777, 10), {}, {})

    assert heard == []


async def test_another_kind_of_update_is_ignored(chatting, session_factory):
    """Оповещение другого рода пропускается, а не разбирается зря.

    Сырые оповещения приходят на каждое событие сервера: разбор каждого
    стоил бы обращения к базе на пустом месте.
    """
    bot, client, hr = await chatting(telegram_user_id=777)
    await put(
        session_factory,
        message_row(hr_id=hr.id, is_incoming=False, tg_message_id=10, read_at=None),
    )

    await bot._on_raw_update(client, object(), {}, {})

    assert (await only_row(session_factory, Message)).read_at is None


async def test_our_own_reading_is_not_mistaken_for_the_hrs(chatting, session_factory):
    """Прочтение с нашей стороны за прочтение HR не принимается.

    Оповещение о том, что переписку открыли мы, устроено точно так же —
    тот же собеседник, та же граница, — и различает их только род. Приняв
    его за чужое, бот поставил бы двойную галочку на письма, которых HR
    не открывал.
    """
    bot, client, hr = await chatting(telegram_user_id=777)
    await put(
        session_factory,
        message_row(hr_id=hr.id, is_incoming=False, tg_message_id=10, read_at=None),
    )
    ours = UpdateReadHistoryInbox(
        peer=PeerUser(user_id=777),
        max_id=10,
        still_unread_count=0,
        pts=1,
        pts_count=1,
    )

    await bot._on_raw_update(client, ours, {}, {})

    assert (await only_row(session_factory, Message)).read_at is None
