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

import logging
from pathlib import Path
from types import SimpleNamespace

import pytest
from pyrogram import raw

import adapters.telegram
from adapters.telegram import list_dialog_peers, make_client, send_dm
from tests.factories import tg_creds
from tests.fakes.telegram import FakeTelegramClient
from config import get_data_dir


def test_a_saved_session_keeps_the_client_in_memory():
    """Со строкой сессии клиент живёт в памяти, без файла на диске.

    Строка лежит в настройках зашифрованной и переживает переезд папки с
    данными; файл сессии — нет.
    """
    client = make_client(tg_creds(session_string="сессия"))

    assert client.in_memory is True


def test_a_first_login_keeps_the_session_in_a_file():
    """До первого входа сессия ведётся файлом в папке данных.

    Строки ещё нет — её выдаёт сам Telegram по итогам входа, и до тех пор
    держать состояние негде.
    """
    client = make_client(tg_creds())

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
    client = make_client(tg_creds(phone="+70000000000", password="пароль"))

    assert client.phone_number == "+70000000000"
    assert client.password == "пароль"


def test_an_account_without_a_second_step_carries_no_password():
    """У учётной записи без второго шага пароль не передаётся.

    Пустая строка Pyrogram'ом читается как «пароль есть», и он спросил бы
    его у пользователя на ровном месте.
    """
    client = make_client(tg_creds(password=""))

    assert client.password is None


@pytest.mark.parametrize(
    "account",
    [
        pytest.param(tg_creds(session_string="сессия"), id="в памяти"),
        pytest.param(tg_creds(), id="файлом"),
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


class DialogServer:
    """Telegram, отдающий список переписок постранично — как настоящий.

    Закладку следующей страницы он читает из `offset_date`, и нулевая для него
    значит «с самого верха». На этом и держится случай, ради которого у
    прогрева стоит сторож продвижения: не найди тот времени верхнего письма —
    попросил бы ту же первую страницу заново.

    `topless` — переписки, чьё верхнее письмо в ответ не кладётся. Так Telegram
    отвечает про стёртое письмо и про пустую переписку.
    """

    def __init__(self, peers, *, page=2, topless=()):
        self.peers = list(peers)
        self.page = page
        self.topless = set(topless)
        self.warmed: list[int] = []
        # Время у переписок убывает: свежие впереди, как их и отдаёт Telegram.
        self.dates = {peer: 1000 - at for at, peer in enumerate(self.peers)}

    async def invoke(self, query, **_options):
        start = 0
        if query.offset_date:
            after = [p for p, d in self.dates.items() if d == query.offset_date]
            start = self.peers.index(after[0]) + 1 if after else 0
        page = self.peers[start : start + self.page]
        self.warmed.extend(page)
        return SimpleNamespace(
            dialogs=[_raw_dialog(peer) for peer in page],
            messages=self._messages(page),
            users=[],
            chats=[],
        )

    def _messages(self, page):
        """Верхние письма страницы, а перед ними — чужое с тем же номером.

        Чужое стоит первым нарочно: номера у переписок не сквозные, и поиск
        письма по одному номеру нашёл бы именно его.
        """
        if not page:
            return []
        alien = _raw_message(_ALIEN_PEER, page[-1], date=1)
        own = [
            _raw_message(peer, peer, date=self.dates[peer])
            for peer in page
            if peer not in self.topless
        ]
        return [alien, *own]

    async def resolve_peer(self, peer_id):
        return raw.types.InputPeerUser(user_id=peer_id, access_hash=0)


_ALIEN_PEER = 9999


def _raw_dialog(peer_id: int):
    return raw.types.Dialog(
        peer=raw.types.PeerUser(user_id=peer_id),
        top_message=peer_id,
        read_inbox_max_id=0,
        read_outbox_max_id=0,
        unread_count=0,
        unread_mentions_count=0,
        unread_reactions_count=0,
        notify_settings=raw.types.PeerNotifySettings(),
    )


def _raw_message(peer_id: int, message_id: int, *, date: int):
    return SimpleNamespace(
        id=message_id, peer_id=raw.types.PeerUser(user_id=peer_id), date=date
    )


async def test_the_reading_walks_every_page_of_the_dialog_list():
    """Чтение доходит до последней переписки, а не до конца первой страницы.

    Закладку он ставит по верхнему письму последней переписки страницы, а
    искать то письмо надо парой «переписка и номер»: в ответе лежат верхние
    письма всей страницы, счётчик номеров у каждой переписки свой, и по
    одному номеру находится первое попавшееся чужое. С чужой закладкой вторая
    страница приходит не той.
    """
    server = DialogServer([11, 22, 33, 44, 55], page=2)

    found = await list_dialog_peers(server)

    assert [peer.peer_id for peer in found] == [11, 22, 33, 44, 55]


async def test_the_reading_ends_when_the_bookmark_cannot_move(caplog):
    """Чтение кончается, когда закладку поставить не по чему, и говорит об этом.

    Верхнего письма в ответе может не оказаться вовсе — у стёртого письма
    Telegram кладёт `messageEmpty`, у пустой переписки номер нулевой. Нулевая
    закладка значит «с самого верха», и без сторожа проход ходил бы по кругу
    в подъёме, до объявления готовности.

    Молчать при этом нельзя: прочитанной окажется одна страница из многих, и
    остальные переписки не будут ни прогреты, ни догнаны.
    """
    server = DialogServer([11, 22, 33, 44], page=2, topless={11, 22})

    with caplog.at_level(logging.WARNING):
        found = await list_dialog_peers(server)

    assert server.warmed == [11, 22]
    assert "список переписок кончился" in caplog.text
    # Недочитанный список — не список всех переписок: по нему догон отобрал бы
    # собеседников и молча потерял бы остальных.
    assert found is None

