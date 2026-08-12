"""Следствия сборки клиента Telegram и отправки личного сообщения.

Клиент собирается двумя способами. Со строкой сессии он живёт в памяти —
это предпочтительный путь: строка лежит в настройках в зашифрованном виде и
переживает переезд папки с данными. Без строки, то есть до первого входа,
сессия ведётся файлом, и его надо где-то держать.

Отправка прикрывается признаком, который в боевом коде по умолчанию снят, а
на стенде взведён. Пока он взведён, письмо не уходит, а причина остаётся в
журнале — это единственная защита от рассылки живым HR во время разработки.
Снимают его тут только те проверки, которым нужна ушедшая отправка, и только
на подставном клиенте.

Номер ушедшего сообщения возвращается наружу: по нему потом опознаётся отметка
о прочтении, и без него у исходящей строки нечему совпасть.
"""

from pathlib import Path

import pytest

import adapters.telegram
from adapters.telegram import make_client, send_dm
from backend.runtime_settings import TgAccountConfig
from tests.fakes.telegram import FakeTelegramClient
from config import get_data_dir


def _account(**overrides):
    """Учётные данные Telegram в том виде, в каком их читают из настроек."""
    fields = {
        "api_id": 26276902,
        "api_hash": "шифр",
        "phone": "+70000000000",
        "password": "",
        "session_string": None,
    }
    fields.update(overrides)
    return TgAccountConfig(**fields)


def test_a_saved_session_keeps_the_client_in_memory():
    """Со строкой сессии клиент живёт в памяти, без файла на диске.

    Строка лежит в настройках зашифрованной и переживает переезд папки с
    данными; файл сессии — нет.
    """
    client = make_client(_account(session_string="сессия"))

    assert client.in_memory is True


def test_a_first_login_keeps_the_session_in_a_file():
    """До первого входа сессия ведётся файлом в папке данных.

    Строки ещё нет — её выдаёт сам Telegram по итогам входа, и до тех пор
    держать состояние негде.
    """
    client = make_client(_account())

    assert not client.in_memory
    # Сверяется сам путь файла, а не имя из настроек: имя — довод, который мы
    # же и передали, а следствие у него одно — куда ляжет сессия. Путь назван
    # строкой нарочно: смени его в коде, и Pyrogram заведёт новый файл, а
    # старый осиротеет — то есть человека попросят войти заново.
    assert Path(client.storage.database) == (
        get_data_dir() / "sessions" / "job_bot.session"
    )
    assert Path(client.workdir).is_dir()


def test_the_login_carries_the_phone_and_the_password():
    """Вход несёт телефон и пароль второго шага."""
    client = make_client(_account(password="пароль"))

    assert client.phone_number == "+70000000000"
    assert client.password == "пароль"


def test_an_account_without_a_second_step_carries_no_password():
    """У учётной записи без второго шага пароль не передаётся.

    Пустая строка Pyrogram'ом читается как «пароль есть», и он спросил бы
    его у пользователя на ровном месте.
    """
    client = make_client(_account(password=""))

    assert client.password is None


@pytest.mark.parametrize(
    "account",
    [
        pytest.param(_account(session_string="сессия"), id="в памяти"),
        pytest.param(_account(), id="файлом"),
    ],
)
def test_the_client_waits_out_short_rate_limits_itself(account):
    """Клиент сам пережидает короткие запреты частоты.

    Умолчание в десять секунд не покрывает пики во время догона
    переписок пачками, и каждый такой пик выходил бы наружу ошибкой.
    """
    assert make_client(account).sleep_threshold == 60


async def test_a_message_goes_out_and_its_number_comes_back(sending_unlocked):
    """Сообщение уходит, и его номер возвращается наружу.

    По номеру потом опознаётся отметка о прочтении: без него у исходящей
    строки нечему совпасть.
    """
    client = FakeTelegramClient()

    assert await send_dm(client, "maria", "письмо") == client.last_message_id
    assert client.outgoing == [("send_message", "maria", "письмо", None)]


async def test_an_attachment_turns_the_message_into_a_document(sending_unlocked):
    """С вложением сообщение уходит документом, а текст становится подписью.

    Отдельным сообщением текст пришёл бы раньше или позже файла, и HR
    получил бы письмо, оторванное от резюме.
    """
    client = FakeTelegramClient()

    await send_dm(client, "maria", "письмо", Path("Резюме.pdf"))

    assert client.outgoing == [
        ("send_document", "maria", "Резюме.pdf", "письмо"),
    ]


async def test_the_guard_stops_the_message_and_reports_nothing_sent(monkeypatch):
    """Взведённый признак письмо останавливает и номера не выдаёт.

    Это единственная защита от рассылки живым HR во время разработки, и
    отсутствие номера говорит вызывающему, что письма не было.
    """
    monkeypatch.setattr(adapters.telegram, "SEND_LOCKED", True)
    client = FakeTelegramClient()

    assert await send_dm(client, "maria", "письмо") is None
    assert client.outgoing == []


async def test_the_guard_stops_an_attachment_too(monkeypatch):
    """Взведённый признак останавливает и отправку с вложением."""
    monkeypatch.setattr(adapters.telegram, "SEND_LOCKED", True)
    client = FakeTelegramClient()

    assert await send_dm(client, "maria", "письмо", Path("Резюме.pdf")) is None
    assert client.outgoing == []
