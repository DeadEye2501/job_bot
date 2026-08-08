"""Подделка клиента Pyrogram и построители его объектов.

Реализованы только те методы, которые проект действительно зовёт. Неизвестный
метод даёт `AttributeError` сам собой — объекта-заглушки здесь нет намеренно:
заглушка превращает «код зовёт не то» в зелёный тест.
"""

import io
from types import SimpleNamespace


def message(*, text=None, caption=None, **extra) -> SimpleNamespace:
    """Сообщение. `text` и `caption` задаются всегда: код читает их напрямую."""
    return SimpleNamespace(text=text, caption=caption, **extra)


def photo(*, small_file_id=None, big_file_id=None) -> SimpleNamespace:
    """Фотография профиля с идентификаторами файлов."""
    return SimpleNamespace(small_file_id=small_file_id, big_file_id=big_file_id)


def chat(*, title=None, photo=None, **extra) -> SimpleNamespace:
    """Канал или чат в том виде, в каком его отдаёт `get_chat`."""
    return SimpleNamespace(title=title, photo=photo, **extra)


def user(*, is_bot=False, is_deleted=False, photo=None, **extra) -> SimpleNamespace:
    """Собеседник Telegram."""
    return SimpleNamespace(is_bot=is_bot, is_deleted=is_deleted, photo=photo, **extra)


class FakeTelegramClient:
    """Отдаёт заранее положенное и записывает, о чём его спрашивали."""

    def __init__(self, *, users=None, avatar=None, chats=None, fails=None) -> None:
        """`fails` — что бросить вместо ответа, по имени метода."""
        self._users = users or {}
        self._avatar = avatar
        self._chats = chats or {}
        self._fails = fails or {}
        self.get_users_calls: list[str] = []
        self.get_chat_calls: list[str] = []
        self.download_calls: list[str] = []
        self.handlers: list = []

    def add_handler(self, handler) -> None:
        self.handlers.append(handler)

    def _fail_if_asked(self, method: str) -> None:
        error = self._fails.get(method)
        if error is not None:
            raise error

    async def get_chat(self, chat_id):
        self.get_chat_calls.append(chat_id)
        self._fail_if_asked("get_chat")
        return self._chats.get(chat_id)

    async def get_users(self, username):
        self.get_users_calls.append(username)
        self._fail_if_asked("get_users")
        return self._users.get(username)

    async def download_media(self, file_id, in_memory=False):
        assert in_memory, "проект качает аватар только в память"
        self.download_calls.append(file_id)
        self._fail_if_asked("download_media")
        if self._avatar is None:
            return None
        return io.BytesIO(self._avatar)
