"""Следствия сверки строки сессии при запуске.

Telegram переселяет учётную запись между узлами и меняет ключи; строка сессии
после этого другая, и разошедшаяся копия в настройках означает повторный вход
с кодом из смс на следующем запуске.

Записывается только изменившаяся: запись стоит расшифровки, шифрования и
обращения к базе на каждом запуске, а менять чаще всего нечего. И ни сбой
выгрузки, ни сбой записи запуск не роняют — клиент к этому мигу уже подключён
и работает.
"""

from backend.bot import loop
from tests.fakes.telegram import FakeTelegramClient


async def test_a_changed_session_string_is_saved(make_bot):
    """Изменившаяся строка сессии сохраняется."""
    client = FakeTelegramClient()
    client.session_string = "новая сессия"
    bot = await make_bot(client)

    await loop._persist_session_if_changed(bot)

    assert bot._rs.tg.session_string == "новая сессия"


async def test_an_unchanged_session_string_is_left_alone(make_bot):
    """Совпавшая строка сессии не переписывается.

    Запись стоит расшифровки, шифрования и обращения к базе на каждом
    запуске — а менять нечего.
    """
    client = FakeTelegramClient()
    client.session_string = "прежняя"
    bot = await make_bot(client)
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

    await loop._persist_session_if_changed(bot)

    assert written == []


async def test_a_failed_export_saves_nothing(make_bot):
    """Сорвавшаяся выгрузка строки сессии ничего не записывает.

    Записать вместо неё пустоту значило бы стереть рабочий вход.
    """
    bot = await make_bot(
        FakeTelegramClient(fails={"export_session_string": OSError("сеть")})
    )
    before = bot._rs.tg.session_string

    await loop._persist_session_if_changed(bot)

    assert bot._rs.tg.session_string == before


async def test_a_failed_save_does_not_stop_the_start(make_bot):
    """Сорвавшаяся запись строки сессии запуск не роняет.

    Клиент уже подключён и работает; упасть из-за неудачной записи
    значило бы обменять рабочий запуск на удобство следующего.
    """
    client = FakeTelegramClient()
    client.session_string = "новая сессия"
    bot = await make_bot(client)

    async def broken(**kwargs):
        raise OSError("база")

    bot._rs.set_tg = broken
    before = bot._rs.tg.session_string

    await loop._persist_session_if_changed(bot)

    assert bot._rs.tg.session_string == before
