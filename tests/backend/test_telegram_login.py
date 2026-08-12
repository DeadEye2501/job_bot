"""Следствия входа в Telegram по коду.

Вход — четыре шага с состоянием между ними: запрос кода, подтверждение кода,
при нужде облачный пароль, сохранение сессии. Живой вход требует настоящих
учётных данных и кода из Telegram, поэтому клиент здесь подделан, а
проверяется то, что вокруг него: что ушло в Telegram, что легло в настройки и
что осталось в держателе после каждого исхода.
"""

from types import SimpleNamespace

import pytest
from pyrogram.errors import (
    BadRequest,
    FloodWait,
    PhoneCodeExpired,
    PhoneCodeInvalid,
    PhoneNumberInvalid,
    SessionPasswordNeeded,
)

from backend.runtime_settings import RuntimeSettings
from backend.telegram_login import TelegramLogin
from tests.fakes.telegram import FakeTelegramClient


@pytest.fixture
def clients(monkeypatch):
    """Подделки вместо настоящих клиентов Pyrogram, по одной на попытку входа.

    `fails` — общий на все подделки перечень «чем ответить вместо ответа»:
    его кладут и до шага, и между шагами, когда клиент уже собран.
    """
    telegram = SimpleNamespace(made=[], fails={})

    def build(**kwargs):
        client = FakeTelegramClient(fails=telegram.fails)
        client.built_with = kwargs
        telegram.made.append(client)
        return client

    monkeypatch.setattr("backend.telegram_login.PyrogramClient", build)
    return telegram


@pytest.fixture
async def login(session_factory, clients):
    """Держатель входа поверх настоящих настроек и поддельного клиента."""
    settings = await RuntimeSettings.load(session_factory)
    return TelegramLogin("проверка", settings)


async def sent(login, *, phone="+79991234567"):
    """Пройти первый шаг: код запрошен, держатель ждёт ответа."""
    return await login.send_code(1, "ключ", phone)


async def test_the_code_is_asked_for_the_phone_that_was_typed(login, clients):
    """Код запрашивается у Telegram на набранный номер, и это видно в ответе."""
    step = await sent(login)

    assert clients.made[0].code_requests == ["+79991234567"]
    assert step.error is None
    assert "***4567" in step.payload["message"]


async def test_the_client_is_built_with_the_name_the_holder_was_given(login, clients):
    """Клиент собирается под именем сессии, с которым заведён держатель.

    Имя разводит два входа — из мастера и из настроек: под одним именем они
    делили бы файл сессии.
    """
    await sent(login)

    assert clients.made[0].built_with["name"] == "проверка"
    assert clients.made[0].built_with["api_id"] == 1
    # Сессия входа живёт в памяти: файл на диске пережил бы попытку и
    # достался бы следующей вместе с чужим ключом.
    assert clients.made[0].built_with["in_memory"] is True
    assert "подключение" in clients.made[0].lifecycle


async def test_a_phone_number_telegram_refused_leaves_no_client_open(login, clients):
    """Отвергнутый номер отвечает отказом и не оставляет открытого сокета."""
    clients.fails["send_code"] = PhoneNumberInvalid()

    step = await sent(login)

    assert step.error == "Неверный номер телефона."
    assert "отключение" in clients.made[0].lifecycle
    assert login.awaiting_code is False


async def test_a_rate_limit_without_a_number_is_named_in_words(login, clients):
    """Запрет без названного срока называется словами, а не «0 сек».

    Telegram не всегда говорит, сколько ждать; «подождите 0 сек» на экране —
    это приглашение попробовать снова прямо сейчас и получить тот же запрет.
    """
    clients.fails["send_code"] = FloodWait(value=0)

    step = await sent(login)

    assert "некоторое время" in step.error


async def test_a_rate_limit_with_a_number_says_how_long(login, clients):
    """Названный Telegram срок доезжает до окна человеческими единицами."""
    clients.fails["send_code"] = FloodWait(value=12418)

    step = await sent(login)

    assert "3 ч 26 мин" in step.error


async def test_a_second_request_closes_the_client_of_the_first(login, clients):
    """Повторный запрос кода закрывает клиента прежней попытки.

    Иначе «назад, другой номер» оставляет висеть сокет на каждый заход.
    """
    await sent(login)
    await sent(login, phone="+79990000000")

    assert "отключение" in clients.made[0].lifecycle
    assert len(clients.made) == 2


async def test_the_code_is_confirmed_against_the_request_it_answers(login, clients):
    """Код подтверждается с отпечатком той отправки, на которую отвечает.

    Отпечаток связывает код с запросом: без него Telegram не знает, какую
    именно отправку подтверждают, и живой вход не проходит вовсе — а по
    подделке этого не видно, она принимает что угодно.
    """
    await sent(login)

    await login.confirm_code("11111")

    assert clients.made[0].sign_in_calls == [
        ("+79991234567", "отпечаток", "11111")
    ]


async def test_a_wrong_code_is_answered_with_a_refusal(login, clients):
    """Неверный код отвечает отказом, а вход остаётся на том же шаге."""
    clients.fails["sign_in"] = PhoneCodeInvalid()
    await sent(login)

    step = await login.confirm_code("11111")

    assert step.error == "Неверный код."
    assert login.awaiting_code is True


async def test_a_stale_code_is_answered_with_a_refusal(login, clients):
    """Устаревший код отвечает отказом, называющим, что делать дальше."""
    clients.fails["sign_in"] = PhoneCodeExpired()
    await sent(login)

    step = await login.confirm_code("11111")

    assert "запросите новый" in step.error


async def test_a_second_factor_is_asked_for_when_telegram_wants_it(login, clients):
    """Telegram, требующий облачный пароль, переводит вход на его шаг."""
    clients.fails["sign_in"] = SessionPasswordNeeded()
    await sent(login)

    step = await login.confirm_code("11111")

    assert step.payload == {"need_password": True}
    assert login.awaiting_password is True


async def test_a_cloud_password_that_did_not_fit_is_answered_with_a_refusal(
    login, clients
):
    """Неверный облачный пароль отвечает отказом."""
    clients.fails["check_password"] = BadRequest()
    await sent(login)

    step = await login.confirm_password("не тот")

    assert step.error == "Неверный облачный пароль."


async def test_a_confirmed_code_saves_the_session_and_closes_the_client(
    login, clients, session_factory
):
    """Подтверждённый код сохраняет сессию в настройках и закрывает клиента.

    Сессия — то единственное, ради чего вход и затевался: с ней бот встаёт
    без второго обращения к Telegram.
    """
    await sent(login)

    step = await login.confirm_code("11111")

    settings = await RuntimeSettings.load(session_factory)
    assert settings.tg.session_string == "шифр"
    assert settings.tg.api_id == 1
    assert settings.tg.api_hash == "ключ"
    assert settings.tg.phone == "+79991234567"
    assert step.payload == {"done": True}
    assert "отключение" in clients.made[0].lifecycle


async def test_a_confirmed_password_saves_the_session_too(
    login, clients, session_factory
):
    """Пройденный облачный пароль сохраняется вместе с сессией."""
    clients.fails["sign_in"] = SessionPasswordNeeded()
    await sent(login)
    await login.confirm_code("11111")

    step = await login.confirm_password("облачный")

    assert step.payload == {"done": True}
    assert clients.made[0].passwords == ["облачный"]
    settings = await RuntimeSettings.load(session_factory)
    assert settings.tg.password == "облачный"


async def test_a_saved_login_forgets_everything_it_kept(login, clients):
    """После сохранения держатель ничего от попытки не хранит."""
    await sent(login)

    await login.confirm_code("11111")

    assert login.awaiting_code is False
    assert login.awaiting_password is False


async def test_a_session_that_did_not_export_is_answered_with_the_failure(
    login, clients, session_factory
):
    """Сорвавшийся вывоз сессии отвечает отказом и ничего не сохраняет."""
    clients.fails["export_session_string"] = RuntimeError("сеть")
    await sent(login)

    step = await login.confirm_code("11111")

    assert "сеть" in step.error
    settings = await RuntimeSettings.load(session_factory)
    assert settings.tg is None
    assert login.awaiting_code is False


async def test_the_saved_login_hands_the_username_to_the_one_who_waits(
    session_factory, clients
):
    """Ник вошедшего достаётся тому, кто его ждёт.

    Спрашивают его, пока клиент входа ещё подключён: бот встанет позже, и его
    собственное соединение будет готово не сразу.
    """
    heard: list[str] = []
    settings = await RuntimeSettings.load(session_factory)
    login = TelegramLogin("проверка", settings, on_saved=heard.append)
    await login.send_code(1, "ключ", "+79991234567")

    await login.confirm_code("11111")

    assert heard == ["я"]
    lifecycle = clients.made[0].lifecycle
    assert lifecycle.index("кто я") < lifecycle.index("отключение")


async def test_the_username_is_not_asked_for_when_nobody_waits_for_it(login, clients):
    """Без ожидающего ник у Telegram не спрашивают вовсе."""
    await sent(login)

    await login.confirm_code("11111")

    assert "кто я" not in clients.made[0].lifecycle


async def test_a_forgotten_login_closes_the_client(login, clients):
    """Закрытая на середине модалка закрывает клиента и обнуляет шаг."""
    await sent(login)

    await login.forget()

    assert "отключение" in clients.made[0].lifecycle
    assert login.awaiting_code is False
