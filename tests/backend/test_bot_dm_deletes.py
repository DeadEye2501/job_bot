"""Следствия удаления сообщения на стороне Telegram.

Строка не выбрасывается, а метится удалённой: переписка с HR — свидетельство,
и стереть его вслед за собеседником значило бы потерять то, ради чего она
велась. Непрочитанное входящее при этом ещё и гасится, иначе счётчик навсегда
завис бы на надгробии, которое некому открыть.

Telegram присылает такие оповещения скупо: переписка в них часто не названа
вовсе, гарантирован только номер сообщения. А номера свои у каждой переписки —
двойки и тройки есть у всех. Поэтому безымянная уборка сужена до входящих:
задеть чужую строку она всё ещё может, но окно для этого куда уже.
"""

from datetime import datetime, timezone

from backend.models import HR, BotMode, Message
from tests.dbio import all_rows, only_row, put
from tests.factories import hr_row, message_row
from tests.fakes.ingestion import FakeIngestion
from tests.fakes.telegram import chat, message


def _tombstone(msg_id: int, *, chat_id=777, username=None):
    """Надгробие сообщения: номер и, если повезло, переписка."""
    return message(
        id=msg_id,
        chat=None if chat_id is None else chat(id=chat_id, username=username),
    )


async def test_a_deleted_message_is_marked_not_dropped(chatting, session_factory):
    """Удалённое сообщение метится, а не выбрасывается.

    Переписка с HR — свидетельство; стирать её вслед за собеседником
    значило бы терять то, ради чего она велась.
    """
    bot, client, hr = await chatting(telegram_user_id=777)
    bot._ingestion = FakeIngestion()
    await put(
        session_factory,
        message_row(hr_id=hr.id, is_incoming=True, tg_message_id=10, text="было"),
    )

    await bot._on_dm_delete(client, [_tombstone(10)])

    saved = await only_row(session_factory, Message)
    assert saved.is_deleted is True
    assert saved.text == "было"


async def test_an_unread_tombstone_stops_counting(chatting, session_factory):
    """Непрочитанное удалённое перестаёт числиться непрочитанным.

    Открыть его уже нельзя, и счётчик завис бы на нём навсегда.
    """
    bot, client, hr = await chatting(telegram_user_id=777)
    bot._ingestion = FakeIngestion()
    await put(
        session_factory,
        message_row(hr_id=hr.id, is_incoming=True, tg_message_id=10, read_at=None),
    )

    await bot._on_dm_delete(client, [_tombstone(10)])

    assert (await only_row(session_factory, Message)).read_at is not None


async def test_an_already_read_tombstone_keeps_its_read_time(
    chatting, session_factory
):
    """У прочитанного удалённого время прочтения остаётся прежним."""
    first_read = datetime(2026, 1, 1, 9, 0, tzinfo=timezone.utc)
    bot, client, hr = await chatting(telegram_user_id=777)
    bot._ingestion = FakeIngestion()
    await put(
        session_factory,
        message_row(hr_id=hr.id, is_incoming=True, tg_message_id=10, read_at=first_read),
    )

    await bot._on_dm_delete(client, [_tombstone(10)])

    saved = await only_row(session_factory, Message)
    assert saved.read_at.replace(tzinfo=timezone.utc) == first_read


async def test_a_deleted_outgoing_message_is_not_marked_read(
    chatting, session_factory
):
    """Своё удалённое прочитанным не метится: его читает HR, а не мы."""
    bot, client, hr = await chatting(telegram_user_id=777)
    bot._ingestion = FakeIngestion()
    await put(
        session_factory,
        message_row(hr_id=hr.id, is_incoming=False, tg_message_id=10, read_at=None),
    )

    await bot._on_dm_delete(client, [_tombstone(10)])

    saved = await only_row(session_factory, Message)
    assert saved.is_deleted is True
    assert saved.read_at is None


async def test_several_deletions_in_one_chat_go_together(chatting, session_factory):
    """Несколько удалений в одной переписке разбираются разом."""
    bot, client, hr = await chatting(telegram_user_id=777)
    bot._ingestion = FakeIngestion()
    await put(
        session_factory,
        message_row(hr_id=hr.id, is_incoming=True, tg_message_id=10),
        message_row(hr_id=hr.id, is_incoming=True, tg_message_id=11),
        message_row(hr_id=hr.id, is_incoming=True, tg_message_id=12),
    )

    await bot._on_dm_delete(client, [_tombstone(10), _tombstone(12)])

    marked = {m.tg_message_id: m.is_deleted for m in await all_rows(session_factory, Message)}
    assert marked == {10: True, 11: False, 12: True}


async def test_a_deletion_from_a_stranger_marks_nothing(chatting, session_factory):
    """Удаление в переписке с незнакомым собеседником ничего не метит."""
    bot, client, hr = await chatting(telegram_user_id=777)
    bot._ingestion = FakeIngestion()
    await put(
        session_factory,
        message_row(hr_id=hr.id, is_incoming=True, tg_message_id=10),
    )

    await bot._on_dm_delete(client, [_tombstone(10, chat_id=999)])

    assert (await only_row(session_factory, Message)).is_deleted is False


async def test_a_switched_off_bot_ignores_deletions(chatting, session_factory):
    """Выключенный бот удаления не разбирает."""
    bot, client, hr = await chatting(mode=BotMode.OFF, telegram_user_id=777)
    bot._ingestion = FakeIngestion()
    await put(
        session_factory,
        message_row(hr_id=hr.id, is_incoming=True, tg_message_id=10),
    )

    await bot._on_dm_delete(client, [_tombstone(10)])

    assert (await only_row(session_factory, Message)).is_deleted is False


async def test_an_empty_batch_changes_nothing(chatting, session_factory):
    """Пустая пачка удалений ничего не меняет и не падает."""
    bot, client, hr = await chatting(telegram_user_id=777)
    bot._ingestion = FakeIngestion()
    await put(
        session_factory,
        message_row(hr_id=hr.id, is_incoming=True, tg_message_id=10),
    )

    await bot._on_dm_delete(client, [])

    assert (await only_row(session_factory, Message)).is_deleted is False


async def test_a_chatless_deletion_reaches_incoming_messages(
    chatting, session_factory
):
    """Удаление без названной переписки достаёт входящее по одному номеру.

    Переписку Telegram в таких оповещениях не присылает вовсе; номер —
    единственное, за что можно зацепиться.
    """
    bot, client, hr = await chatting(telegram_user_id=777)
    bot._ingestion = FakeIngestion()
    await put(
        session_factory,
        message_row(hr_id=hr.id, is_incoming=True, tg_message_id=10),
    )

    await bot._on_dm_delete(client, [_tombstone(10, chat_id=None)])

    assert (await only_row(session_factory, Message)).is_deleted is True


async def test_a_chatless_deletion_spares_outgoing_messages(
    chatting, session_factory
):
    """Безымянное удаление своих сообщений не трогает.

    Номера в Telegram свои у каждой переписки, и без названной переписки
    отличить своё сообщение с тем же номером не по чему. Входящими
    сужение окна и держится.
    """
    bot, client, hr = await chatting(telegram_user_id=777)
    bot._ingestion = FakeIngestion()
    await put(
        session_factory,
        message_row(hr_id=hr.id, is_incoming=False, tg_message_id=10),
    )

    await bot._on_dm_delete(client, [_tombstone(10, chat_id=None)])

    assert (await only_row(session_factory, Message)).is_deleted is False


async def test_a_deleted_message_leaves_the_pending_buffer(chatting, session_factory):
    """Удалённое сообщение выбывает из текста, ждущего разбора.

    Учитывать в решении то, что собеседник забрал назад, — прямой путь к
    неверному статусу вакансии.
    """
    bot, client, hr = await chatting(telegram_user_id=777)
    ingestion = FakeIngestion()
    bot._ingestion = ingestion
    await put(
        session_factory,
        message_row(hr_id=hr.id, is_incoming=True, tg_message_id=10),
    )

    await bot._on_dm_delete(client, [_tombstone(10)])

    assert ingestion.buffer_removals == [(hr.id, 10)]


async def test_a_deletion_that_matched_nothing_leaves_the_buffer_alone(
    chatting, session_factory
):
    """Удаление, не нашедшее строки, накопитель не трогает."""
    bot, client, hr = await chatting(telegram_user_id=777)
    ingestion = FakeIngestion()
    bot._ingestion = ingestion

    await bot._on_dm_delete(client, [_tombstone(10)])

    assert ingestion.buffer_removals == []


async def test_the_window_hears_about_each_touched_chat_once(
    chatting, session_factory
):
    """Окно узнаёт о каждой задетой переписке по одному разу.

    Удаление приходит пачкой; оповещать на каждое сообщение значило бы
    перерисовывать переписку столько раз, сколько строк убрали.
    """
    bot, client, hr = await chatting(telegram_user_id=777)
    bot._ingestion = FakeIngestion()
    await put(
        session_factory,
        message_row(hr_id=hr.id, is_incoming=True, tg_message_id=10),
        message_row(hr_id=hr.id, is_incoming=True, tg_message_id=11),
    )
    heard: list[int] = []
    bot.on_new_message = heard.append

    await bot._on_dm_delete(client, [_tombstone(10), _tombstone(11)])

    assert heard == [hr.id]


async def test_the_window_hears_about_a_chatless_deletion_too(
    chatting, session_factory
):
    """О безымянном удалении окно тоже узнаёт — и знает, чью переписку чинить."""
    bot, client, hr = await chatting(telegram_user_id=777)
    bot._ingestion = FakeIngestion()
    await put(
        session_factory,
        message_row(hr_id=hr.id, is_incoming=True, tg_message_id=10),
    )
    heard: list[int] = []
    bot.on_new_message = heard.append

    await bot._on_dm_delete(client, [_tombstone(10, chat_id=None)])

    assert heard == [hr.id]


async def test_deletions_in_two_chats_are_both_handled(chatting, session_factory):
    """Удаления в двух переписках разбираются обе, а не первая попавшаяся."""
    bot, client, first = await chatting(telegram_user_id=777)
    bot._ingestion = FakeIngestion()
    await put(session_factory, hr_row(name="Пётр", telegram_user_id=888))
    second = [
        h for h in await all_rows(session_factory, HR) if h.id != first.id
    ][0]
    await put(
        session_factory,
        message_row(hr_id=first.id, is_incoming=True, tg_message_id=10),
        message_row(hr_id=second.id, is_incoming=True, tg_message_id=10),
    )

    await bot._on_dm_delete(
        client, [_tombstone(10), _tombstone(10, chat_id=888)]
    )

    assert all(m.is_deleted for m in await all_rows(session_factory, Message))
