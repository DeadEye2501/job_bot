"""Фото человека, которое окно показывает в анкете: выбрать, обрезать, убрать."""

from __future__ import annotations

import base64
import binascii
from pathlib import Path

from backend.bot.media import (
    PHOTO_EXTS,
    PHOTO_SIZE_LIMIT,
    PHOTO_SUFFIXES,
    drop_stored_media,
    store_profile_photo,
)
from backend.domain.image_types import image_type
from backend.repository.app_settings import PHOTO_PATH_KEY

from client.bridge.answer import denied, reply
from client.bridge.desktop import chosen_path, closed_dialog, file_filter
from client.bridge.media import image_data_url

_PHOTO_FILTER = file_filter("Фото", sorted(PHOTO_EXTS))


class Photo:
    """Фото как копия в каталоге медиа, а не ссылка на исходный файл.

    Примесь к `Profile`; собирающий обязан держать `_hub`. Выбранный файл
    уходит окну картинкой: рамку обрезки рисует окно, и назад приходит уже
    вырезанное — тоже картинкой, а не путём. Путь к файлу на диске странице
    не назвать: его даёт только диалог самого окна.
    """

    def pick_photo(self) -> dict:
        """Спросить у человека фото диалогом окна и отдать его окну для обрезки."""
        path = chosen_path(self._hub.window, _PHOTO_FILTER)
        if path is None:
            return closed_dialog()
        source = Path(path)
        if source.stat().st_size > PHOTO_SIZE_LIMIT:
            return denied(f"Фото больше {PHOTO_SIZE_LIMIT // (1024 * 1024)} МБ.")
        return {"ok": {"image": image_data_url(source.read_bytes())}}

    def store_photo(self, image: str) -> dict:
        """Запомнить вырезанное окном фото копией в каталоге медиа.

        Узнаётся картинка по своим байтам, а не по подписи в начале строки:
        подпись пишет страница. Копия с другим расширением удаляется последней:
        не записалось новое — старое фото осталось.
        """
        blob = _image_bytes(image)
        suffix = PHOTO_SUFFIXES.get(image_type(blob[:12]) if blob else None)
        if suffix is None:
            return denied("Это не фото.")

        async def run() -> dict:
            previous = self._hub.rs.photo_path
            relative = store_profile_photo(blob, suffix)
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


def _image_bytes(image) -> bytes | None:
    """Байты картинки, вшитой в строку `data:…;base64,…`; другое — пусто."""
    if not isinstance(image, str) or not image.startswith("data:") or "," not in image:
        return None
    try:
        return base64.b64decode(image.split(",", 1)[1], validate=True)
    except binascii.Error:
        return None
