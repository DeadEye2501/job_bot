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


def user(*, is_bot=False, is_deleted=False, photo=None, **extra) -> SimpleNamespace:
    """Собеседник Telegram."""
    return SimpleNamespace(is_bot=is_bot, is_deleted=is_deleted, photo=photo, **extra)


class FakeTelegramClient:
    """Отдаёт заранее положенное и записывает, о чём его спрашивали."""

    def __init__(
        self,
        *,
        users=None,
        avatar=None,
        get_users_error=None,
        download_error=None,
    ) -> None:
        self._users = users or {}
        self._avatar = avatar
        self._get_users_error = get_users_error
        self._download_error = download_error
        self.get_users_calls: list[str] = []
        self.download_calls: list[str] = []

    async def get_users(self, username):
        self.get_users_calls.append(username)
        if self._get_users_error is not None:
            raise self._get_users_error
        return self._users.get(username)

    async def download_media(self, file_id, in_memory=False):
        self.download_calls.append(file_id)
        if self._download_error is not None:
            raise self._download_error
        if self._avatar is None:
            return None
        return io.BytesIO(self._avatar)
