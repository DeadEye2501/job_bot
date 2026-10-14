"""Фото человека, которое окно показывает в анкете: выбрать копией и убрать."""

from __future__ import annotations

from pathlib import Path

from backend.bot.media import PHOTO_EXTS, copy_profile_photo, drop_stored_media
from backend.repository.app_settings import PHOTO_PATH_KEY

from client.bridge.answer import reply
from client.bridge.desktop import chosen_path, closed_dialog, file_filter

_PHOTO_FILTER = file_filter("Фото", sorted(PHOTO_EXTS))


class Photo:
    """Фото как копия в каталоге медиа, а не ссылка на исходный файл.

    Примесь к `Profile`; собирающий обязан держать `_hub`. Копия лежит рядом с
    вложениями переписки и отдаётся окну тем же адресом медиа.
    """

    def pick_photo(self) -> dict:
        """Спросить у человека фото диалогом самого окна и запомнить копию."""
        path = chosen_path(self._hub.window, _PHOTO_FILTER)
        if path is None:
            return closed_dialog()
        return self._store_photo(Path(path))

    def _store_photo(self, source: Path) -> dict:
        """Заменить копию фото выбранным файлом и записать путь к ней.

        Закрыт от страницы, как `_replace` у резюме: путь сюда приходит из
        диалога самого окна, то есть от человека. Прежняя копия удаляется
        последней: не скопировалось новое — старое фото осталось на месте.
        """

        async def run() -> dict:
            previous = self._hub.rs.photo_path
            relative = copy_profile_photo(source)
            await self._hub.rs.set_app(PHOTO_PATH_KEY, relative)
            if previous != relative:
                drop_stored_media(previous)
            return {"photo_path": relative}

        return reply(self._hub.runner, run())

    def clear_photo(self) -> dict:
        """Убрать фото: и путь, и копию."""

        async def run() -> dict:
            drop_stored_media(self._hub.rs.photo_path)
            await self._hub.rs.set_app(PHOTO_PATH_KEY, "")
            return {}

        return reply(self._hub.runner, run())
