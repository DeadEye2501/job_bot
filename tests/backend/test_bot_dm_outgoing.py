"""Следствия сообщения, отправленного HR с телефона или другого клиента.

Такое сообщение приходит обратно эхом, и его подхватывают, чтобы переписка в
окне совпадала с тем, что видит собеседник. Написанное отсюда возвращается
тем же эхом — но строка о нём уже есть, и второй раз её не пишут: два
одинаковых пузыря пользователь заметит сразу.

Проверка «уже есть» стоит до скачивания вложения нарочно. Без неё загрузка
эха гналась бы за копией, сделанной при отправке, к одному и тому же файлу —
и оставляла бы в папке рваный.
"""

import logging

from backend.models import BotMode, Message
from tests.dbio import all_rows, only_row, put
from tests.factories import EPOCH, message_row
from tests.fakes.telegram import FakeTelegramClient
from tests.fakes.telegram_objects import message, my_dm


async def test_a_message_typed_elsewhere_shows_up_in_the_chat(
    chatting_on_fakes, session_factory
):
    """Написанное с телефона появляется в переписке окна.

    Иначе половина разговора видна только на телефоне, и пользователь
    отвечает второй раз на то, что уже ответил.
    """
    bot, client, hr = await chatting_on_fakes(telegram_user_id=777)

    await bot._on_dm_outgoing(client, my_dm())

    saved = await only_row(session_factory, Message)
    assert saved.is_incoming is False
    assert saved.hr_id == hr.id
    assert saved.text == "ответ с телефона"
    assert saved.tg_message_id == 10
    assert saved.sent_at == EPOCH


async def test_an_echo_of_our_own_send_is_not_written_twice(
    chatting_on_fakes, session_factory
):
    """Эхо отправленного отсюда второй строкой не пишется.

    Строку завела сама отправка; вторая дала бы в переписке два
    одинаковых пузыря.
    """
    bot, client, hr = await chatting_on_fakes(telegram_user_id=777)
    await put(
        session_factory,
        message_row(
            hr_id=hr.id, is_incoming=False, tg_message_id=10, text="отправлено отсюда"
        ),
    )

    await bot._on_dm_outgoing(client, my_dm())

    saved = await only_row(session_factory, Message)
    assert saved.text == "отправлено отсюда"


async def test_an_echo_of_our_own_send_downloads_nothing(chatting_on_fakes, session_factory):
    """Эхо своего вложения заново не качается.

    Копия уже лежит в папке, сделанная при отправке; загрузка гналась бы
    с ней за один и тот же файл и оставила бы рваный.
    """
    client = FakeTelegramClient()
    bot, _, hr = await chatting_on_fakes(client=client, telegram_user_id=777)
    await put(
        session_factory,
        message_row(hr_id=hr.id, is_incoming=False, tg_message_id=10),
    )

    await bot._on_dm_outgoing(client, my_dm(photo=object()))

    assert client.download_calls == []


async def test_the_window_hears_about_an_echo_of_our_own_send(
    chatting_on_fakes, session_factory
):
    """Об эхе своей отправки окно всё равно узнаёт.

    Строка уже была, но до эха она значилась только у нас; момент, когда
    сообщение действительно ушло, — это и есть эхо.
    """
    bot, client, hr = await chatting_on_fakes(telegram_user_id=777)
    await put(
        session_factory,
        message_row(hr_id=hr.id, is_incoming=False, tg_message_id=10),
    )
    heard: list[int] = []
    bot.on_new_message = heard.append

    await bot._on_dm_outgoing(client, my_dm())

    assert heard == [hr.id]


async def test_a_message_to_a_stranger_is_not_saved(chatting_on_fakes, session_factory):
    """Написанное незнакомому собеседнику не сохраняется.

    Переписка ведётся с HR; складывать сюда разговор с кем угодно
    значило бы завалить вкладку посторонним.
    """
    bot, client, hr = await chatting_on_fakes(telegram_user_id=777)

    await bot._on_dm_outgoing(client, my_dm(chat_id=999))

    assert await all_rows(session_factory, Message) == []


async def test_a_message_without_a_chat_is_ignored(chatting_on_fakes, session_factory):
    """Сообщение без указания переписки пропускается: адресата не опознать."""
    bot, client, hr = await chatting_on_fakes(telegram_user_id=777)

    await bot._on_dm_outgoing(client, message(id=10, text="куда-то", chat=None))

    assert await all_rows(session_factory, Message) == []


async def test_a_switched_off_bot_ignores_what_was_typed_elsewhere(
    chatting_on_fakes, session_factory
):
    """Выключенный бот написанное с телефона не подхватывает."""
    bot, client, hr = await chatting_on_fakes(mode=BotMode.OFF, telegram_user_id=777)

    await bot._on_dm_outgoing(client, my_dm())

    assert await all_rows(session_factory, Message) == []


async def test_an_attachment_typed_elsewhere_is_downloaded(
    chatting_on_fakes, session_factory
):
    """Вложение, отправленное с телефона, скачивается в свою папку.

    Копии у нас нет — файл выбирали не здесь, и без загрузки переписка
    показала бы пузырь без содержимого.
    """
    client = FakeTelegramClient()
    bot, _, hr = await chatting_on_fakes(client=client, telegram_user_id=777)

    await bot._on_dm_outgoing(client, my_dm(photo=object()))

    saved = await only_row(session_factory, Message)
    assert saved.media_kind == "photo"
    assert saved.media_path == f"{hr.id}/10.jpg"
    assert len(client.download_paths) == 1


async def test_an_attachment_without_a_client_is_not_chased(
    chatting_on_fakes, session_factory, caplog
):
    """Без клиента Telegram вложение даже не пробуют скачать.

    Качать нечем, а попытка осела бы в журнале записью об ошибке — то есть
    счётчик ошибок в окне загорелся бы там, где всё идёт как задумано. Письмо
    при этом ложится: род вложения известен и без файла, и в переписке по нему
    виден пузырь.
    """
    bot, _, _ = await chatting_on_fakes(client=FakeTelegramClient(), telegram_user_id=777)
    bot.client = None

    with caplog.at_level(logging.ERROR):
        await bot._on_dm_outgoing(None, my_dm(photo=object()))

    saved = await only_row(session_factory, Message)
    assert saved.media_kind == "photo"
    assert saved.media_path is None
    assert [r for r in caplog.records if r.levelno >= logging.ERROR] == []


async def test_a_duplicate_that_slipped_in_meanwhile_is_passed_over(
    chatting_on_fakes, session_factory
):
    """Строка, вставленная за время скачивания, обработчик не роняет.

    Ветка «уже сохранено» задумана тихой: повтор ловится уникальностью и
    обработчик выходит, оставив в переписке ту строку, что успела лечь
    первой. Случай тот самый, ради которого ветка и написана: отправка из
    окна успевает записать своё, пока грузится вложение эха.
    """
    client = FakeTelegramClient()
    bot, _, hr = await chatting_on_fakes(client=client, telegram_user_id=777)

    async def send_slips_in(_file_name):
        await put(
            session_factory,
            message_row(
                hr_id=hr.id, is_incoming=False, tg_message_id=10, text="успела отправка"
            ),
        )

    client.on_download = send_slips_in
    heard: list[int] = []
    bot.on_new_message = heard.append

    await bot._on_dm_outgoing(client, my_dm(photo=object()))

    saved = await all_rows(session_factory, Message)
    assert [row.text for row in saved] == ["успела отправка"]
    # Тихо — это и про окно: строку оно уже получило от самой отправки,
    # и второе оповещение о том же сообщении перерисовало бы переписку
    # впустую.
    assert heard == []


async def test_a_write_that_fell_through_stays_quiet(
    chatting_on_fakes, session_factory, monkeypatch
):
    """Сорвавшаяся запись эха обработчик не роняет.

    Это колбэк насоса обновлений: улетевшее отсюда исключение поймать
    некому, и падает чтение обновлений целиком — из-за одной зеркальной
    строки, без которой переписка проживёт.

    Срыв устроен негодным значением поля, а не подменённым коммитом:
    только тогда сессия по-настоящему попадает в состояние «нужен откат»,
    в котором обращение к полю HR и поднимало исключение из записи в
    журнал. С подменённым коммитом ветка выглядела бы исправной, не будучи ею.

    Тишина здесь и про окно: строки не появилось, и звать переписку
    перерисовываться не за чем — она покажет ровно то же, что и была.
    """
    bot, client, hr = await chatting_on_fakes(telegram_user_id=777)
    monkeypatch.setattr("backend.flows.dm.extract_dm_text", lambda msg: object())
    heard: list[int] = []
    bot.on_new_message = heard.append

    await bot._on_dm_outgoing(client, my_dm())

    assert await all_rows(session_factory, Message) == []
    assert heard == []


async def test_the_window_hears_about_a_message_typed_elsewhere(
    chatting_on_fakes
):
    """Окно узнаёт о написанном с телефона: переписка обновится сразу."""
    bot, client, hr = await chatting_on_fakes(telegram_user_id=777)
    heard: list[int] = []
    bot.on_new_message = heard.append

    await bot._on_dm_outgoing(client, my_dm())

    assert heard == [hr.id]


async def test_a_broken_window_hook_does_not_lose_the_message(
    chatting_on_fakes, session_factory
):
    """Сломанное оповещение окна само сообщение не теряет."""
    bot, client, hr = await chatting_on_fakes(telegram_user_id=777)

    def broken(hr_id):
        raise RuntimeError("окно")

    bot.on_new_message = broken

    await bot._on_dm_outgoing(client, my_dm())

    assert (await only_row(session_factory, Message)).text == "ответ с телефона"


async def test_an_echo_finds_an_hr_known_only_by_name(chatting_on_fakes, session_factory):
    """Эхо находит HR, известного только по имени.

    Номер собеседника заводится позже; до того имя из объекта чата —
    единственное, чем строку можно опознать.
    """
    bot, client, hr = await chatting_on_fakes(telegram_username="maria", telegram_user_id=None)

    await bot._on_dm_outgoing(client, my_dm(chat_id=999, username="maria"))

    saved = await only_row(session_factory, Message)
    assert saved.hr_id == hr.id
    assert saved.text == "ответ с телефона"
