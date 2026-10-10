"""Вложение письма, каким его видит окно: адрес разметки и файл за адресом."""

from __future__ import annotations

import base64
from pathlib import Path

from backend.bot.media import image_type
from client.serving import MEDIA_PREFIX, inside


def _media_url(stored_path: str | None) -> str | None:
    """Адрес, по которому окно получит вложение у своей же раздачи.

    В колонке лежит путь внутри каталога медиа (`"1/42.jpg"`) — про сам каталог
    окно не знает вовсе. Адрес нужен http'шный: страница отдана по http, и
    подресурс с `file://` Chromium не загружает по правилам происхождения —
    в ленте на месте снимка остаётся пустота, а отказ виден только в консоли.

    Путь, ведущий вне каталога медиа, адреса не получает: раздать такой нечем,
    заслон его не выпустит. Показать «нет адреса» окно уже умеет — так же, как
    нескачанное вложение. Класть туда такие пути перестали: сегодня в колонку
    идёт только путь внутри каталога.
    """
    if not stored_path:
        return None
    relative = _under_media(stored_path)
    if relative is None:
        return None
    return MEDIA_PREFIX + relative


def media_file(url: str) -> Path | None:
    """Файл на диске, стоящий за адресом вложения, или пусто.

    Обратная дорога того же адреса: окно возвращает его, прося открыть
    вложение системой, а системе нужен путь. Заслон здесь тот же, что у
    раздачи, и нужен по той же причине — адрес приезжает снаружи.
    """
    if not isinstance(url, str) or not url.startswith(MEDIA_PREFIX):
        return None
    from backend.bot.media import MEDIA_DIR
    return inside(MEDIA_DIR.resolve(), url[len(MEDIA_PREFIX):])


def _under_media(stored_path: str) -> str | None:
    """Путь из колонки, приведённый к пути внутри каталога медиа.

    Приводит обе записи разом: относительную, какую пишут сегодня, и
    оставшуюся от прежних заходов абсолютную.

    Сам заслон общий (`serving.inside`): дальше каталога он не пускает и
    отвечает на «..», сложись он в колонке как угодно. Здесь только приведение
    абсолютной записи к относительной — до заслона, потому что абсолютный путь
    заменяет собой корень, и заслону досталось бы уже не то, что проверяют.
    """
    from backend.bot.media import MEDIA_DIR
    root = MEDIA_DIR.resolve()
    path = Path(stored_path)
    if path.is_absolute():
        try:
            path = path.resolve().relative_to(root)
        except ValueError:
            return None
    target = inside(root, path.as_posix())
    return None if target is None else target.relative_to(root).as_posix()


def _image_type(blob: bytes) -> str:
    """Тип снимка по его первым байтам.

    Снимки Telegram приходят jpeg, а значки сайтов — png, ico, gif, webp, и
    заголовка с типом у колонки нет: правду говорят только сами байты. Не
    узнанное считается jpeg — так приходит всё, что дал Telegram.
    """
    return image_type(blob) or "image/jpeg"


def _avatar_data_url(blob: bytes | None) -> str | None:
    """Снимок учётной записи или значок сайта, вшитый в сам ответ.

    Аватарки Telegram весят по нескольку килобайт, и вшитые в список они
    обходятся дешевле, чем отдельный запрос на каждую строку.
    """
    if not blob:
        return None
    return f"data:{_image_type(blob)};base64," + base64.b64encode(blob).decode("ascii")
