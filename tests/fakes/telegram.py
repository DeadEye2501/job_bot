"""Подделка клиента Pyrogram и построители его объектов.

Реализованы только те методы, которые проект действительно зовёт. Неизвестный
метод даёт `AttributeError` сам собой — объекта-заглушки здесь нет намеренно:
заглушка превращает «код зовёт не то» в зелёный тест.

Расхождение подделки с настоящим клиентом опаснее её отсутствия: боевой код
почти везде обёрнут широким `except`, и неверная подпись метода приходит туда
же, куда пришла бы сетевая ошибка. Проверка «не качали» после этого зелена
при любом исходе. Поэтому подписи здесь повторяют настоящие, а не удобные.
"""

import asyncio
import io
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

# Метка времени у исходящего — своя, не «сейчас»: тест сверяет её с тем, что
# легло в базу, а «сейчас» на такое сравнение не годится.
SENT_AT = datetime(2026, 1, 1, 12, 0)


def message(*, text=None, caption=None, **extra) -> SimpleNamespace:
    """Сообщение. `text` и `caption` задаются всегда: код читает их напрямую."""
    return SimpleNamespace(text=text, caption=caption, **extra)


def incoming(*, user_id=777, username=None, text="здравствуйте", **extra):
    """Входящее личное сообщение от собеседника.

    Поля, которые боевой код читает напрямую, заданы всегда: отсутствие
    любого из них он встречает `AttributeError`, а не веткой.

    С чатом иначе: его отсутствие — настоящий случай, и код на него
    ветвится (в оповещении об удалении Pyrogram кладёт `None`). Задан он
    здесь потому, что в личной переписке чат и есть собеседник, и собран
    из того же отправителя: иначе подменённый отправитель разъезжался бы
    с чатом по номеру. Проверки про «чата нет» сообщение собирают сами.
    """
    fields = {
        "id": 10,
        "text": text,
        "date": SENT_AT,
        "photo": None,
        "document": None,
        "reply_to_message_id": None,
    }
    fields.update(extra)
    sender = fields.pop("from_user", None)
    if sender is None:
        sender = user(id=user_id, username=username)
    fields.setdefault("chat", chat(id=sender.id, username=sender.username))
    return message(from_user=sender, **fields)


# Отличает «текста не задали» от «текста нет»: второе — настоящий случай,
# объявление из одной картинки, и `None` должен доходить до кода как есть.
_UNSET = object()


def post(msg_id: int, *, text=_UNSET, **extra):
    """Объявление из канала. Текст по умолчанию несёт свой номер.

    Номер в тексте нужен проверкам порядка: по нему видно, какое именно
    объявление разобрано, когда их несколько.
    """
    fields = {"service": None, "poll": None}
    fields.update(extra)
    return message(
        id=msg_id,
        text=f"объявление {msg_id}" if text is _UNSET else text,
        date=SENT_AT,
        **fields,
    )


def photo(*, small_file_id=None, big_file_id=None) -> SimpleNamespace:
    """Фотография профиля с идентификаторами файлов."""
    return SimpleNamespace(small_file_id=small_file_id, big_file_id=big_file_id)


def document(name: str | None) -> SimpleNamespace:
    """Вложенный документ. Имя бывает и пустым, и отсутствующим."""
    return SimpleNamespace(file_name=name)


def chat(*, title=None, photo=None, **extra) -> SimpleNamespace:
    """Канал или чат в том виде, в каком его отдаёт `get_chat`."""
    return SimpleNamespace(title=title, photo=photo, **extra)


def user(*, username=None, photo=None, **extra) -> SimpleNamespace:
    """Собеседник Telegram.

    Имя, фамилия, ник и признак бота заданы всегда, пусть и пустые: у
    настоящего собеседника эти поля есть, и боевой код читает их напрямую.
    Без них подделка роняет `AttributeError` там, где код работает.
    """
    fields = {
        "is_bot": False,
        "is_deleted": False,
        "first_name": None,
        "last_name": None,
    }
    fields.update(extra)
    return SimpleNamespace(username=username, photo=photo, **fields)


class FakeTelegramClient:
    """Отдаёт заранее положенное и записывает, о чём его спрашивали."""

    def __init__(
        self, *, users=None, avatar=None, chats=None, media=b"file", fails=None
    ) -> None:
        """`fails` — что бросить вместо ответа, по имени метода.

        Значением там может стоять список: тогда обращения обслуживаются по
        очереди, и `None` в списке означает «на этот раз без ошибки». Так
        проверяется повтор после отказа.
        """
        self._users = users or {}
        self._avatar = avatar
        self._chats = chats or {}
        self._media = media
        self._fails = fails or {}
        self.get_users_calls: list[str] = []
        self.get_chat_calls: list[str] = []
        self.history_calls: list[tuple] = []
        self.download_calls: list = []
        self.download_paths: list[str] = []
        self.read_calls: list = []
        self.outgoing: list[tuple] = []
        self.handlers: list = []
        self.lifecycle: list[str] = []
        self.last_message_id = 500
        self.session_string = "шифр"
        # Переписка, которую отдаёт `get_chat_history`. Ставится после
        # сборки: пятый именованный довод конструктора упирается в предел.
        self.history: list = []
        self.logged_out = False
        # Вход по коду: чем отвечает Telegram и о чём его спрашивали.
        self.phone_code_hash = "отпечаток"
        self.me = user(id=1, username="я")
        self.code_requests: list[str] = []
        self.sign_in_calls: list[tuple] = []
        self.passwords: list[str] = []
        # Вклиниться в середину вызова: так проверяется гонка со встречным
        # обработчиком, который успевает записать строку, пока идёт обращение.
        self.on_send = None
        self.on_download = None

    @property
    def loop(self):
        """Цикл событий. Есть и у настоящего клиента: в паре с `executor`
        через него Pyrogram уводит несопрограммные отборы в отдельный поток."""
        return asyncio.get_running_loop()

    # Отдельного пула нет нарочно: `None` означает «пул по умолчанию», и
    # отбор всё равно исполнится — а свой пришлось бы закрывать руками.
    executor = None

    def add_handler(self, handler) -> None:
        self.handlers.append(handler)

    def _fail_if_asked(self, method: str) -> None:
        error = self._fails.get(method)
        if isinstance(error, list):
            error = error.pop(0) if error else None
        if error is not None:
            raise error

    async def get_chat(self, chat_id):
        self.get_chat_calls.append(chat_id)
        self._fail_if_asked("get_chat")
        return self._chats.get(chat_id)

    async def get_chat_history(self, target, limit=100):
        self.history_calls.append((target, limit))
        self._fail_if_asked("get_chat_history")
        for msg in self.history[:limit]:
            yield msg

    async def get_users(self, username):
        self.get_users_calls.append(username)
        self._fail_if_asked("get_users")
        return self._users.get(username)

    async def download_media(self, target, file_name=None, in_memory=False):
        """Скачивание в память по идентификатору файла или на диск по сообщению.

        У Pyrogram это один метод: первым доводом он берёт и идентификатор
        файла, и само сообщение, а куда положить — решают `in_memory` и
        `file_name`. Двумя подделками эти формы разводить нельзя. Боевой
        `download_media` зовёт вторую, и подделка, знающая только первую,
        отвечает `TypeError`; его глотает `except Exception` вокруг вызова,
        и проверка «не качали» зеленеет независимо от того, качали или нет.
        """
        self.download_calls.append(target)
        if self.on_download is not None:
            await self.on_download(file_name)
        self._fail_if_asked("download_media")
        if in_memory:
            return io.BytesIO(self._avatar) if self._avatar is not None else None
        self.download_paths.append(file_name)
        if self._media is None:
            return None
        Path(file_name).write_bytes(self._media)
        return file_name

    async def _accept(self, kind: str, target, payload):
        """Принимает исходящее и отдаёт то, что вернул бы Telegram."""
        self.outgoing.append((kind, target, payload))
        self._fail_if_asked(kind)
        self.last_message_id += 1
        answer = SimpleNamespace(id=self.last_message_id, date=SENT_AT)
        if self.on_send is not None:
            await self.on_send(answer)
        return answer

    async def send_message(self, target, text):
        return await self._accept("send_message", target, text)

    async def send_photo(self, target, path):
        return await self._accept("send_photo", target, path)

    async def send_document(self, target, path):
        return await self._accept("send_document", target, path)

    async def read_chat_history(self, target):
        self.read_calls.append(target)
        self._fail_if_asked("read_chat_history")

    async def connect(self):
        self.lifecycle.append("подключение")
        self._fail_if_asked("connect")

    async def disconnect(self):
        self.lifecycle.append("отключение")
        self._fail_if_asked("disconnect")

    async def send_code(self, phone):
        self.code_requests.append(phone)
        self._fail_if_asked("send_code")
        return SimpleNamespace(phone_code_hash=self.phone_code_hash)

    async def sign_in(self, phone_number=None, phone_code_hash=None, phone_code=None):
        self.sign_in_calls.append((phone_number, phone_code_hash, phone_code))
        self._fail_if_asked("sign_in")

    async def check_password(self, password):
        self.passwords.append(password)
        self._fail_if_asked("check_password")

    async def get_me(self):
        # В журнал жизни, а не в свой список: у вопроса о себе важно не
        # только то, задали ли его, но и то, что задали до отключения.
        self.lifecycle.append("кто я")
        self._fail_if_asked("get_me")
        return self.me

    async def start(self):
        self.lifecycle.append("запуск")
        self._fail_if_asked("start")

    async def stop(self):
        self.lifecycle.append("остановка")
        self._fail_if_asked("stop")

    async def log_out(self):
        self.logged_out = True
        self._fail_if_asked("log_out")

    async def export_session_string(self):
        self._fail_if_asked("export_session_string")
        return self.session_string
