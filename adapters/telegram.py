"""Сборка клиента Telegram и отправка письма его руками.

Единственным домом знания о Pyrogram модуль не является, и делать вид не
стоит: клиента ввозят ещё семеро — бот, обработчики, вход по коду, чтение
метаданных, догон переписки. Здесь собрано то, что зовут все: как клиент
собирается и как через него уходит письмо.

`SEND_LOCKED` живёт тут же, потому что читает его отсюда общий заслон
(`bot/can_send`) — а заслон спрашивают все дороги отправки, включая переписку
из окна, которая письмо шлёт своим зовом мимо `send_dm`. Проверка в самом
`send_dm` — второй рубеж, на случай дороги, заслон не спросившей.
"""

import logging
from pathlib import Path

from pyrogram import Client, raw, utils

from backend.domain.telegram_identity import DialogPeer
from backend.tg_credentials import TgAccountConfig
from config import get_data_dir

_log = logging.getLogger(__name__)


SESSIONS_DIR = get_data_dir() / "sessions"
"""Папка, в которой Pyrogram держит файл сеанса.

Объявлена здесь, а не у зовущего: имя знает и снос данных, и оболочка, что
ищет осиротевшие файлы сеанса.
"""

SESSION_NAME = "job_bot"


def make_client(tg: TgAccountConfig) -> Client:
    """Build a pyrogram client from a runtime TG config.

    If ``session_string`` is set, runs in-memory (preferred — survives moving
    the app data dir). Otherwise falls back to a file-based session in the
    per-user data dir, expected to be populated on first interactive login.
    """
    # ``sleep_threshold=60``: Pyrogram сам ждёт и ретраит FloodWait короче
    # 60с (default 10с) — закрывает пиковые TG-rate-limit'ы во время
    # batch-параллельного добора пропущенных сообщений без промахов.
    if tg.session_string:
        return Client(
            name=SESSION_NAME,
            session_string=tg.session_string,
            api_id=tg.api_id,
            api_hash=tg.api_hash,
            in_memory=True,
            sleep_threshold=60,
        )
    sessions_dir = SESSIONS_DIR
    sessions_dir.mkdir(exist_ok=True)
    return Client(
        name=SESSION_NAME,
        api_id=tg.api_id,
        api_hash=tg.api_hash,
        phone_number=tg.phone,
        password=tg.password or None,
        workdir=str(sessions_dir),
        sleep_threshold=60,
    )


# Запор боевой отправки: `True` — письмо не уходит. Хозяин запора не здесь, а в
# настройке `send_locked` — галке «Симуляция отправки», по умолчанию снятой;
# сюда значение переписывают на старте бота и при правке настроек, чтобы горячий
# путь отправки не ходил за ним в базу. Поэтому `False` в объявлении значит «до
# первой синхронизации», а не «отправка разрешена».
# Спрашивают его двое и делают разное: общий заслон (`bot/can_send`) отвечает
# окну отказом, а `send_dm` под запором пишет в журнал вместо отправки.
# Откликатель читает саму настройку (`rs.send_locked`) — ему нужен признак
# симуляции и для записи отклика.
SEND_LOCKED = False


async def send_dm(
    client: Client,
    user: str | int,
    text: str,
    attachment: str | Path | None = None,
) -> int | None:
    """Отправляет DM. Возвращает Telegram message_id ответа Pyrogram'а,
    либо None если отправка заглушена SEND_LOCKED — caller использует id
    для записи в Message.tg_message_id (закрывает UNIQUE-дыру с NULL'ами
    для outgoing-row'ов)."""
    if SEND_LOCKED:
        _log.warning(
            "send_dm: SEND_LOCKED=True — would have sent to %r"
            "%s (%d chars), suppressed",
            user,
            f" with attachment {attachment}" if attachment else "",
            len(text),
        )
        return None
    if attachment is not None:
        msg = await client.send_document(user, str(attachment), caption=text)
    else:
        msg = await client.send_message(user, text)
    return getattr(msg, "id", None)


_DIALOG_PAGE = 100
"""Сколько переписок просить за раз. Предел Telegram для этого обращения."""


def _message_date(messages, bookmark: tuple[int, int]) -> int:
    """Время верхнего письма переписки; ноль, если такого в ответе нет.

    Оно нужно закладке следующей страницы: Telegram отсчитывает её от пары
    «номер и время верхнего письма», и без времени вторая страница пришла бы
    той же первой.

    Ищется письмо по паре «переписка и номер», а не по одному номеру: в ответе
    лежат верхние письма всей сотни переписок, а счётчик номеров у каждой свой
    — по одному номеру находится первое попавшееся чужое письмо.
    """
    peer_id, message_id = bookmark
    for msg in messages:
        if getattr(msg, "id", None) != message_id:
            continue
        own = getattr(msg, "peer_id", None)
        if own is not None and utils.get_peer_id(own) == peer_id:
            return getattr(msg, "date", 0) or 0
    return 0


async def _dialog_page(client, offset_date: int, offset_id: int, offset_peer):
    """Страница списка переписок, взятая сырым обращением.

    `sleep_threshold` тот же, что у `get_dialogs`: короткое «слишком часто»
    Pyrogram пережидает сам, а до нас доходит только долгое.
    """
    return await client.invoke(
        raw.functions.messages.GetDialogs(
            offset_date=offset_date,
            offset_id=offset_id,
            offset_peer=offset_peer,
            limit=_DIALOG_PAGE,
            hash=0,
        ),
        sleep_threshold=60,
    )


def _next_bookmark(dialogs, messages) -> tuple[int, int, int] | None:
    """Закладка следующей страницы: переписка, номер верхнего письма и время.

    Берётся последняя переписка страницы, чьё верхнее письмо в ответе нашлось,
    а не последняя вообще: письма может не быть — у стёртого Telegram кладёт
    `messageEmpty`, у пустой переписки номер нулевой. Взяв закладку вслепую,
    проход попросил бы с нулевым временем, а это значит «с самого верха», и
    вся страница пришла бы заново.

    Пусто значит, что двигаться не по чему на всей странице.
    """
    for dialog in reversed(dialogs):
        peer_id = utils.get_peer_id(dialog.peer)
        date = _message_date(messages, (peer_id, dialog.top_message))
        if date:
            return peer_id, dialog.top_message, date
    return None


def _peers_of(dialogs, users) -> list:
    """Собеседники страницы: номер из переписки, ник — из участников ответа."""
    nicks = {u.id: getattr(u, "username", None) for u in users}
    peers = []
    for dialog in dialogs:
        peer_id = utils.get_peer_id(dialog.peer)
        peers.append(DialogPeer(peer_id, nicks.get(peer_id)))
    return peers


async def list_dialog_peers(client) -> list | None:
    """Собеседники, с которыми переписка есть, — свежими вперёд; `None` —
    список дочитать не вышло, и всех переписок он не называет.

    По ним догон отбирает, кого читать: читать переписку у того, с кем её нет,
    нечего, а стоит попытка дорого. Порядок берётся отсюда же — Telegram отдаёт
    список свежими вперёд, и человек, открывший приложение, ждёт именно свежее.

    Попутно проход кладёт участников в кэш пиров, и это не мелочь. Кэш живёт в
    памяти вместе со строкой сеанса и пуст при каждом запуске, а адресуем мы
    собеседника номером учётной записи: по пустому кэшу номер не разрешается, и
    Telegram отвечает `PeerIdInvalid` — чтению переписки, отправке письма и
    отметке о прочтении разом. Pyrogram кэширует участников ответа после
    каждого обращения.

    Обращение сырое, а не `get_dialogs`: тот на каждую переписку разбирает
    верхнее письмо, а если оно ответ — идёт в сеть за оригиналом. Нам нужны
    одни участники, и они лежат в ответе до всякого разбора.

    Проход кончается по закладке, на которой страница уже кончалась. Без этого
    сторожа он ходил бы по кругу — в подъёме, до объявления готовности, то
    есть окно ждало бы готового бота вечно.
    """
    offset_date, offset_id = 0, 0
    offset_peer = raw.types.InputPeerEmpty()
    seen: set[tuple[int, int]] = set()
    found: list = []
    while True:
        answer = await _dialog_page(client, offset_date, offset_id, offset_peer)
        dialogs = [d for d in answer.dialogs if isinstance(d, raw.types.Dialog)]
        if not dialogs:
            return found
        found.extend(_peers_of(dialogs, answer.users))
        step = _next_bookmark(dialogs, answer.messages)
        if step is None or step[:2] in seen:
            _log.warning(
                "список переписок кончился, не сдвинув закладку: прочитано %d, "
                "остальные не прогреты, догон пойдёт по всем",
                len(found),
            )
            return None
        seen.add(step[:2])
        peer_id, offset_id, offset_date = step
        offset_peer = await client.resolve_peer(peer_id)

