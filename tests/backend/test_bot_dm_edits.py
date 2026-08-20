"""Следствия правки сообщения, пришедшей из Telegram.

Правка догоняет уже сохранённую строку: текст переписывается, и появляется
пометка «изменено» — без неё пользователь читал бы новую редакцию, думая, что
это исходная.

Сообщение, ещё ждущее разбора в накопителе, правится и там: разбор идёт через
минуту после последнего сообщения, и за эту минуту HR успевает дописать самое
важное. Разобрать старую редакцию значило бы решать по неполному тексту.
"""

from backend.models import BotMode, Message
from tests.dbio import all_rows, only_row, put
from tests.factories import message_row
from tests.fakes.telegram import chat, incoming, message, my_dm


def _edit(*, chat_id=777, username=None, msg_id=10, text="новая редакция", mine=False):
    """Правка сообщения в личной переписке; `mine` — своё оно или чужое.

    Своё и чужое собираются разными построителями, а не одним признаком у
    общего: у своего отправитель — мы, у чужого — собеседник. Отправитель
    проставлен в обе стороны, потому что Pyrogram заполняет его в обе, и
    подделка, гасящая его вместе с признаком «своё», закрыла бы оба условия
    разом — тогда ни одно из них по отдельности не было бы проверено.
    """
    if mine:
        return my_dm(msg_id=msg_id, chat_id=chat_id, username=username, text=text)
    return incoming(id=msg_id, user_id=chat_id, username=username, text=text)


async def test_an_edit_overwrites_the_saved_text(chatting_on_fakes, session_factory):
    """Правка переписывает сохранённый текст и метит строку как изменённую."""
    bot, client, hr = await chatting_on_fakes(telegram_user_id=777)
    await put(
        session_factory,
        message_row(hr_id=hr.id, is_incoming=True, tg_message_id=10, text="старая"),
    )

    await bot._on_dm_edit(client, _edit())

    saved = await only_row(session_factory, Message)
    assert saved.text == "новая редакция"
    assert saved.is_edited is True


async def test_an_edit_of_our_own_message_finds_the_outgoing_row(
    chatting_on_fakes, session_factory
):
    """Правка своего же сообщения находит исходящую строку, а не входящую.

    Номера сообщений в Telegram свои у каждой переписки, и во входящих
    вполне может лежать строка с тем же номером.
    """
    bot, client, hr = await chatting_on_fakes(telegram_user_id=777)
    await put(
        session_factory,
        message_row(hr_id=hr.id, is_incoming=True, tg_message_id=10, text="входящее"),
        message_row(hr_id=hr.id, is_incoming=False, tg_message_id=10, text="своё"),
    )

    await bot._on_dm_edit(client, _edit(mine=True))

    by_direction = {m.is_incoming: m for m in await all_rows(session_factory, Message)}
    assert by_direction[False].text == "новая редакция"
    assert by_direction[True].text == "входящее"


async def test_an_edit_from_a_stranger_changes_nothing(chatting_on_fakes, session_factory):
    """Правка из переписки с незнакомым собеседником ничего не меняет."""
    bot, client, hr = await chatting_on_fakes(telegram_user_id=777)
    await put(
        session_factory,
        message_row(hr_id=hr.id, is_incoming=True, tg_message_id=10, text="старая"),
    )

    await bot._on_dm_edit(client, _edit(chat_id=999))

    assert (await only_row(session_factory, Message)).text == "старая"


async def test_an_edit_without_a_chat_is_ignored(chatting_on_fakes, session_factory):
    """Правка без указания переписки пропускается: искать строку не по чему."""
    bot, client, hr = await chatting_on_fakes(telegram_user_id=777)
    await put(
        session_factory,
        message_row(hr_id=hr.id, is_incoming=True, tg_message_id=10, text="старая"),
    )

    await bot._on_dm_edit(client, message(id=10, text="новая", chat=None))

    assert (await only_row(session_factory, Message)).text == "старая"


async def test_a_switched_off_bot_ignores_edits(chatting_on_fakes, session_factory):
    """Выключенный бот правки не разбирает."""
    bot, client, hr = await chatting_on_fakes(mode=BotMode.OFF, telegram_user_id=777)
    await put(
        session_factory,
        message_row(hr_id=hr.id, is_incoming=True, tg_message_id=10, text="старая"),
    )

    await bot._on_dm_edit(client, _edit())

    assert (await only_row(session_factory, Message)).text == "старая"


async def test_an_edited_incoming_message_is_refreshed_in_the_buffer(
    chatting_on_fakes, session_factory
):
    """Правка входящего обновляет и текст, ждущий разбора.

    Разбор идёт через минуту после последнего сообщения; за эту минуту HR
    успевает дописать главное, и решать по старой редакции значило бы
    судить по неполному тексту.
    """
    bot, client, hr = await chatting_on_fakes(telegram_user_id=777)
    ingestion = bot.ingestion
    await put(
        session_factory,
        message_row(hr_id=hr.id, is_incoming=True, tg_message_id=10, text="старая"),
    )

    await bot._on_dm_edit(client, _edit())

    assert ingestion.buffer_edits == [(hr.id, 10, "новая редакция")]


async def test_an_edit_of_our_own_message_does_not_touch_the_buffer(
    chatting_on_fakes, session_factory
):
    """Правка своего сообщения накопитель не трогает: разбирают чужие."""
    bot, client, hr = await chatting_on_fakes(telegram_user_id=777)
    ingestion = bot.ingestion
    await put(
        session_factory,
        message_row(hr_id=hr.id, is_incoming=False, tg_message_id=10, text="своё"),
    )

    await bot._on_dm_edit(client, _edit(mine=True))

    assert ingestion.buffer_edits == []


async def test_an_edit_that_matched_nothing_leaves_the_buffer_alone(
    chatting_on_fakes
):
    """Правка, не нашедшая строки, накопитель тоже не трогает."""
    bot, client, hr = await chatting_on_fakes(telegram_user_id=777)
    ingestion = bot.ingestion

    await bot._on_dm_edit(client, _edit())

    assert ingestion.buffer_edits == []


async def test_the_window_hears_about_an_edit(chatting_on_fakes, session_factory):
    """Окно узнаёт о правке: открытая переписка перерисуется сразу."""
    bot, client, hr = await chatting_on_fakes(telegram_user_id=777)
    await put(
        session_factory,
        message_row(hr_id=hr.id, is_incoming=True, tg_message_id=10, text="старая"),
    )
    heard: list[int] = []
    bot.on_new_message = heard.append

    await bot._on_dm_edit(client, _edit())

    assert heard == [hr.id]


async def test_the_window_is_not_told_about_an_edit_that_matched_nothing(
    chatting_on_fakes
):
    """Правка, не нашедшая строки, окно не дёргает: перерисовывать нечего."""
    bot, client, hr = await chatting_on_fakes(telegram_user_id=777)
    heard: list[int] = []
    bot.on_new_message = heard.append

    await bot._on_dm_edit(client, _edit())

    assert heard == []


async def test_a_broken_window_hook_does_not_lose_the_edit(chatting_on_fakes, session_factory):
    """Сломанное оповещение окна саму правку не отменяет."""
    bot, client, hr = await chatting_on_fakes(telegram_user_id=777)
    await put(
        session_factory,
        message_row(hr_id=hr.id, is_incoming=True, tg_message_id=10, text="старая"),
    )

    def broken(hr_id):
        raise RuntimeError("окно")

    bot.on_new_message = broken

    await bot._on_dm_edit(client, _edit())

    assert (await only_row(session_factory, Message)).text == "новая редакция"


async def test_an_edit_of_a_message_without_a_sender_lands_on_the_outgoing_row(
    chatting_on_fakes, session_factory
):
    """Правка сообщения без отправителя правит исходящую строку.

    Отправителя не бывает у служебных записей и пересылок из каналов.
    Считать такую правку входящей значило бы искать строку не в той
    половине переписки.
    """
    bot, client, hr = await chatting_on_fakes(telegram_user_id=777)
    await put(
        session_factory,
        message_row(hr_id=hr.id, is_incoming=True, tg_message_id=10, text="входящее"),
        message_row(hr_id=hr.id, is_incoming=False, tg_message_id=10, text="своё"),
    )
    faceless = message(
        id=10,
        text="новая редакция",
        chat=chat(id=777, username=None),
        from_user=None,
        outgoing=False,
    )

    await bot._on_dm_edit(client, faceless)

    by_direction = {m.is_incoming: m for m in await all_rows(session_factory, Message)}
    assert by_direction[False].text == "новая редакция"
    assert by_direction[True].text == "входящее"


async def test_an_edit_finds_an_hr_known_only_by_name(chatting_on_fakes, session_factory):
    """Правка находит HR, известного только по имени.

    Номер собеседника у строки заводится позже, при первом разборе; до
    того опознать её можно лишь по имени из переписки.
    """
    bot, client, hr = await chatting_on_fakes(telegram_username="maria", telegram_user_id=None)
    await put(
        session_factory,
        message_row(hr_id=hr.id, is_incoming=True, tg_message_id=10, text="старая"),
    )

    await bot._on_dm_edit(client, _edit(chat_id=999, username="maria"))

    assert (await only_row(session_factory, Message)).text == "новая редакция"
