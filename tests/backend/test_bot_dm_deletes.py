"""Следствия удаления сообщения на стороне Telegram.

Строка не выбрасывается, а метится удалённой: переписка с HR — свидетельство,
и стереть его вслед за собеседником значило бы потерять то, ради чего она
велась. Непрочитанное входящее при этом ещё и гасится, иначе счётчик навсегда
завис бы на надгробии, которое некому открыть.

Telegram присылает такие оповещения скупо: переписка в них часто не названа
вовсе, гарантирован только номер сообщения. Номера у пользовательской учётной
записи общие на все личные переписки, так что попадание по одному номеру
точное в обе стороны — безымянная уборка хоронит и наши письма тоже.
"""

from datetime import datetime, timezone

import pytest
from pyrogram.enums import ChatType

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
    bot.ingestion = FakeIngestion()
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
    bot.ingestion = FakeIngestion()
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
    bot.ingestion = FakeIngestion()
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
    bot.ingestion = FakeIngestion()
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
    bot.ingestion = FakeIngestion()
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
    bot.ingestion = FakeIngestion()
    await put(
        session_factory,
        message_row(hr_id=hr.id, is_incoming=True, tg_message_id=10),
    )

    await bot._on_dm_delete(client, [_tombstone(10, chat_id=999)])

    assert (await only_row(session_factory, Message)).is_deleted is False


async def test_a_switched_off_bot_ignores_deletions(chatting, session_factory):
    """Выключенный бот удаления не разбирает."""
    bot, client, hr = await chatting(mode=BotMode.OFF, telegram_user_id=777)
    bot.ingestion = FakeIngestion()
    await put(
        session_factory,
        message_row(hr_id=hr.id, is_incoming=True, tg_message_id=10),
    )

    await bot._on_dm_delete(client, [_tombstone(10)])

    assert (await only_row(session_factory, Message)).is_deleted is False


async def test_an_empty_batch_changes_nothing(chatting, session_factory):
    """Пустая пачка удалений ничего не меняет и не падает."""
    bot, client, hr = await chatting(telegram_user_id=777)
    bot.ingestion = FakeIngestion()
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
    bot.ingestion = FakeIngestion()
    await put(
        session_factory,
        message_row(hr_id=hr.id, is_incoming=True, tg_message_id=10),
    )

    await bot._on_dm_delete(client, [_tombstone(10, chat_id=None)])

    assert (await only_row(session_factory, Message)).is_deleted is True


async def test_a_chatless_deletion_reaches_outgoing_messages_too(
    chatting, session_factory
):
    """Безымянное удаление хоронит и наше письмо, и окно о нём слышит.

    Жди исходящее догона переписки — до следующей загрузки оно висело бы
    живым, а глубже его предела не похоронилось бы никогда. Окно спрашивается
    тем же отбором, и сузься он обратно у одного из двух запросов, надгробие
    встало бы, а переписка на экране осталась бы прежней.
    """
    bot, client, hr = await chatting(telegram_user_id=777)
    bot.ingestion = FakeIngestion()
    await put(
        session_factory,
        message_row(hr_id=hr.id, is_incoming=False, tg_message_id=10),
    )
    heard: list[int] = []
    bot.on_new_message = heard.append

    await bot._on_dm_delete(client, [_tombstone(10, chat_id=None)])

    assert (await only_row(session_factory, Message)).is_deleted is True
    assert heard == [hr.id]


async def test_a_deleted_message_leaves_the_pending_buffer(chatting, session_factory):
    """Удалённое сообщение выбывает из текста, ждущего разбора.

    Учитывать в решении то, что собеседник забрал назад, — прямой путь к
    неверному статусу вакансии.
    """
    bot, client, hr = await chatting(telegram_user_id=777)
    ingestion = FakeIngestion()
    bot.ingestion = ingestion
    await put(
        session_factory,
        message_row(hr_id=hr.id, is_incoming=True, tg_message_id=10),
    )

    await bot._on_dm_delete(client, [_tombstone(10)])

    assert ingestion.buffer_removals == [(hr.id, 10)]


async def test_a_chatless_deletion_leaves_the_pending_buffer_too(
    chatting, session_factory
):
    """Безымянное удаление тоже выбрасывает письмо из копилки разбора.

    Боевое удаление личного письма приходит без переписки почти всегда, и
    без этой уборки отозванный отказ доживал бы до разбора и двигал статус
    вакансии по тому, чего собеседник уже не говорил.
    """
    bot, client, hr = await chatting(telegram_user_id=777)
    ingestion = FakeIngestion()
    bot.ingestion = ingestion
    await put(
        session_factory,
        message_row(hr_id=hr.id, is_incoming=True, tg_message_id=10),
    )

    await bot._on_dm_delete(client, [_tombstone(10, chat_id=None)])

    assert ingestion.buffer_removals == [(hr.id, 10)]


async def test_a_deletion_that_matched_nothing_leaves_the_buffer_alone(
    chatting, session_factory
):
    """Удаление, не нашедшее строки, накопитель не трогает."""
    bot, client, hr = await chatting(telegram_user_id=777)
    ingestion = FakeIngestion()
    bot.ingestion = ingestion

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
    bot.ingestion = FakeIngestion()
    await put(
        session_factory,
        message_row(hr_id=hr.id, is_incoming=True, tg_message_id=10),
        message_row(hr_id=hr.id, is_incoming=True, tg_message_id=11),
    )
    heard: list[int] = []
    bot.on_new_message = heard.append

    await bot._on_dm_delete(client, [_tombstone(10), _tombstone(11)])

    assert heard == [hr.id]


async def test_a_repeated_deletion_does_not_wake_the_window_again(
    chatting, session_factory
):
    """Повторное оповещение об уже удалённом окно не будит.

    Одну и ту же строку накрывают оба пути: оповещение об удалении и догон
    переписки, который вычисляет удалённое сам. Строка уже надгробие, менять
    в ней нечего — а окно перерисовывало бы переписку заново.
    """
    bot, client, hr = await chatting(telegram_user_id=777)
    bot.ingestion = FakeIngestion()
    await put(
        session_factory,
        message_row(hr_id=hr.id, is_incoming=True, tg_message_id=10),
    )
    await bot._on_dm_delete(client, [_tombstone(10)])

    heard: list[int] = []
    bot.on_new_message = heard.append
    await bot._on_dm_delete(client, [_tombstone(10)])

    assert heard == []


async def test_the_window_hears_about_a_chatless_deletion_too(
    chatting, session_factory
):
    """О безымянном удалении окно тоже узнаёт — и знает, чью переписку чинить."""
    bot, client, hr = await chatting(telegram_user_id=777)
    bot.ingestion = FakeIngestion()
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
    bot.ingestion = FakeIngestion()
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


async def test_a_deletion_finds_an_hr_known_only_by_name(chatting, session_factory):
    """Удаление находит HR, известного только по имени.

    Номер собеседника заводится позже; до того опознать переписку можно
    лишь по имени, которое Pyrogram кладёт в тот же объект чата.
    """
    bot, client, hr = await chatting(telegram_username="maria", telegram_user_id=None)
    bot.ingestion = FakeIngestion()
    await put(
        session_factory,
        message_row(hr_id=hr.id, is_incoming=True, tg_message_id=10),
    )

    await bot._on_dm_delete(client, [_tombstone(10, chat_id=999, username="maria")])

    assert (await only_row(session_factory, Message)).is_deleted is True


def _deletion_filter(client):
    """Отбор, с которым обработчик удалений подписан на Pyrogram."""
    from pyrogram.handlers import DeletedMessagesHandler

    handlers = [h for h in client.handlers if isinstance(h, DeletedMessagesHandler)]
    assert len(handlers) == 1, "обработчик удалений должен быть ровно один"
    return handlers[0].filters


@pytest.mark.parametrize(
    ("kind", "expected"),
    [
        pytest.param(ChatType.PRIVATE, True, id="личная переписка"),
        pytest.param(ChatType.BOT, True, id="переписка с ботом"),
        pytest.param(ChatType.CHANNEL, False, id="канал"),
        pytest.param(ChatType.SUPERGROUP, False, id="группа"),
    ],
)
async def test_only_private_deletions_reach_the_handler(chatting, kind, expected):
    """До обработчика доходят удаления только из личных переписок.

    Удаления в каналах приходят тем же путём и пачками по сотне: разбирать
    их значило бы на каждую чистку канала обходить всю таблицу сообщений.
    """
    bot, client, hr = await chatting()

    reached = await _deletion_filter(client)(
        client, message(id=10, chat=chat(id=777, type=kind))
    )

    assert bool(reached) is expected


async def test_a_chatless_deletion_reaches_the_handler(chatting):
    """Удаление без переписки до обработчика доходит.

    Pyrogram для личных удалений ставит переписку в отсутствие — сведений
    о собеседнике в таком оповещении просто нет. Обычный отбор «личная
    переписка» на этом даёт отказ, и без отдельной ветки обработчик не
    срабатывал бы на них вовсе.
    """
    bot, client, hr = await chatting()

    reached = await _deletion_filter(client)(client, message(id=10, chat=None))

    assert bool(reached) is True
