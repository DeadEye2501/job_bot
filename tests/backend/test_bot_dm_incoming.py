"""Следствия входящего сообщения от HR и сохранения строки сессии.

Разбор входящего целиком лежит в конвейере; боту здесь принадлежат две вещи:
не пускать разбор при выключенном боте и сказать окну, чью переписку
перерисовать. Второе делается уже после разбора — до него HR может быть ещё
не заведён, и говорить было бы не о ком.

Строка сессии сохраняется при запуске, если изменилась: Telegram переселяет
учётную запись между узлами и меняет ключи, а разошедшаяся копия означает
повторный вход с кодом из смс на следующем запуске.
"""

import pytest

from backend.models import BotMode
from tests.fakes.telegram import chat, message, user


@pytest.fixture
def dm_pipeline(monkeypatch):
    """Подменяет разбор входящего: он живёт в конвейере, а не в боте."""
    seen: list = []

    async def process_dm(msg, *args, **kwargs):
        seen.append(msg)

    monkeypatch.setattr("backend.bot.process_dm", process_dm)
    return seen


def _incoming(*, user_id=777, username=None, msg_id=10):
    """Входящее сообщение от собеседника."""
    return message(
        id=msg_id,
        text="здравствуйте",
        chat=chat(id=user_id, username=username),
        from_user=user(id=user_id, username=username),
    )


async def test_an_incoming_message_goes_to_the_pipeline(chatting, dm_pipeline):
    """Входящее уходит в конвейер на разбор."""
    bot, client, hr = await chatting(telegram_user_id=777)
    msg = _incoming()

    await bot._on_dm(client, msg)

    assert dm_pipeline == [msg]


async def test_a_switched_off_bot_does_not_read_incoming_messages(
    chatting, dm_pipeline
):
    """Выключенный бот входящие не разбирает.

    «Выключен» означает и это тоже: не читать ответы HR и не менять по
    ним статусы вакансий.
    """
    bot, client, hr = await chatting(mode=BotMode.OFF, telegram_user_id=777)

    await bot._on_dm(client, _incoming())

    assert dm_pipeline == []


async def test_the_window_hears_about_an_incoming_message(chatting, dm_pipeline):
    """Окно узнаёт о входящем: открытая переписка обновится сразу."""
    bot, client, hr = await chatting(telegram_user_id=777)
    heard: list[int] = []
    bot.on_new_message = heard.append

    await bot._on_dm(client, _incoming())

    assert heard == [hr.id]


async def test_a_message_from_a_stranger_does_not_reach_the_window(
    chatting, dm_pipeline
):
    """О письме незнакомого собеседника окну не сообщают.

    Перерисовывать нечего: переписки с ним во вкладке «Контакты» нет.
    """
    bot, client, hr = await chatting(telegram_user_id=777)
    heard: list[int] = []
    bot.on_new_message = heard.append

    await bot._on_dm(client, _incoming(user_id=999))

    assert heard == []


async def test_a_message_without_a_sender_does_not_reach_the_window(
    chatting, dm_pipeline
):
    """Сообщение без отправителя окну не показывают: чью переписку чинить."""
    bot, client, hr = await chatting(telegram_user_id=777)
    heard: list[int] = []
    bot.on_new_message = heard.append
    msg = message(id=10, text="ниоткуда", chat=chat(id=777), from_user=None)

    await bot._on_dm(client, msg)

    assert dm_pipeline == [msg]
    assert heard == []


async def test_an_hr_known_only_by_name_is_found_too(chatting, dm_pipeline):
    """HR, известный только по имени, тоже опознаётся.

    Номер собеседника заводится позже — при первом разборе; до того у
    строки есть одно только имя.
    """
    bot, client, hr = await chatting(telegram_username="maria", telegram_user_id=None)
    heard: list[int] = []
    bot.on_new_message = heard.append

    await bot._on_dm(client, _incoming(user_id=999, username="maria"))

    assert heard == [hr.id]


async def test_a_broken_window_hook_does_not_break_the_handler(
    chatting, dm_pipeline
):
    """Сломанное оповещение окна разбор входящего не отменяет."""
    bot, client, hr = await chatting(telegram_user_id=777)

    def broken(hr_id):
        raise RuntimeError("окно")

    bot.on_new_message = broken
    msg = _incoming()

    await bot._on_dm(client, msg)

    assert dm_pipeline == [msg]


async def test_a_changed_session_string_is_saved(chatting):
    """Изменившаяся строка сессии сохраняется.

    Telegram переселяет учётную запись между узлами и меняет ключи;
    разошедшаяся копия означает повторный вход с кодом из смс.
    """
    bot, client, hr = await chatting()

    async def export_session_string():
        return "новая сессия"

    client.export_session_string = export_session_string

    await bot._persist_session_if_changed()

    assert bot._rs.tg.session_string == "новая сессия"


async def test_an_unchanged_session_string_is_left_alone(chatting):
    """Совпавшая строка сессии не переписывается.

    Запись стоит расшифровки, шифрования и обращения к базе на каждом
    запуске — а менять нечего.
    """
    bot, client, hr = await chatting()
    await bot._rs.set_tg(
        api_id=1,
        api_hash="ш",
        phone="+70000000000",
        password="",
        session_string="прежняя",
    )
    written: list[str] = []

    async def remember(**kwargs):
        written.append(kwargs["session_string"])

    bot._rs.set_tg = remember

    async def export_session_string():
        return "прежняя"

    client.export_session_string = export_session_string

    await bot._persist_session_if_changed()

    assert written == []


async def test_a_failed_export_saves_nothing(chatting):
    """Сорвавшаяся выгрузка строки сессии ничего не записывает.

    Записать вместо неё пустоту значило бы стереть рабочий вход.
    """
    bot, client, hr = await chatting()
    before = bot._rs.tg.session_string

    async def export_session_string():
        raise OSError("сеть")

    client.export_session_string = export_session_string

    await bot._persist_session_if_changed()

    assert bot._rs.tg.session_string == before


async def test_a_failed_save_does_not_stop_the_start(chatting):
    """Сорвавшаяся запись строки сессии запуск не роняет.

    Клиент уже подключён и работает; упасть из-за неудачной записи
    значило бы обменять рабочий запуск на удобство следующего.
    """
    bot, client, hr = await chatting()

    async def export_session_string():
        return "новая сессия"

    async def broken(**kwargs):
        raise OSError("база")

    client.export_session_string = export_session_string
    bot._rs.set_tg = broken
    before = bot._rs.tg.session_string

    await bot._persist_session_if_changed()

    assert bot._rs.tg.session_string == before
