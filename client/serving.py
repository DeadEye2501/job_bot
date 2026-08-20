"""Файлы, которые страница окна читает по http.

**Раздаём по http, а не открываем файлы с диска.** Страница ввозит модули и
спрашивает свои же файлы запросами, а с `file://` браузер отказывает и тому и
другому по правилам происхождения — отказ при этом виден только в консоли
страницы, а на экране просто пусто. Тем же правилом живут и вложения: снимок
из переписки, вставленный в отданную по http страницу адресом `file://`,
Chromium не загружает вовсе.

Своё приложение, а не готовая раздача из библиотеки окна
(`webview.http.BottleServer` поверх `bottle.static_file`). Готовая умеет то же
и заслон на выход из корня держит сама; отличий три, и все нужны нам сегодня:
корень должен отдавать страницу, а не отказ на каталоге; каталога сборки до
слайса А4 нет вовсе, и раздача обязана это пережить; и главное — своё
проверяется сторожами без окна, а готовая поднимается только вместе с ним.
"""

from __future__ import annotations

import logging
import mimetypes
import posixpath
from pathlib import Path
from typing import Callable, Iterable


logger = logging.getLogger(__name__)

_NOT_FOUND = b"not found"

MEDIA_PREFIX = "/media/"
"""С чего начинается адрес вложения переписки.

Шов трёх мест: раздача узнаёт по нему свой каталог, мост строит по нему адрес
для разметки, а просьба открыть вложение разбирает по нему адрес, приехавший
от окна обратно. Написанный в каждом из трёх своей строкой, он разъезжался бы
молча: снимок перестал бы отрисовываться, а причина лежала бы в чужом файле.
"""


def served_files(front_root: Path, media_root: Path) -> Callable:
    """Приложение WSGI, отдающее собранный фронт и вложения переписки.

    Каталога два, потому что и лежат они порознь: сборку кладёт Vite рядом с
    кодом, а вложения бот скачивает в каталог данных человека. Разбирает их
    начало пути (`MEDIA_PREFIX`), а заслон на выход из каталога у обоих один.

    Каталога может не быть вовсе — ни сборки, ни вложений. Отсутствие ничем не
    отличается от пустого: на всё отвечаем «нет такого», и окно открывается
    пустым вместо того, чтобы не открыться.
    """
    front_root = front_root.resolve()
    media_root = media_root.resolve()

    def application(environ: dict, start_response: Callable) -> Iterable[bytes]:
        path = environ.get("PATH_INFO", "/")
        if path.startswith(MEDIA_PREFIX):
            target = inside(media_root, path[len(MEDIA_PREFIX):])
        else:
            target = inside(front_root, _or_index(path))
        body = _read(target)
        if body is None:
            start_response("404 Not Found", [("Content-Type", "text/plain")])
            return [_NOT_FOUND]
        start_response(
            "200 OK",
            [
                ("Content-Type", _content_type(target)),
                ("Content-Length", str(len(body))),
            ],
        )
        return [body]

    return application


def _read(target: Path | None) -> bytes | None:
    """Содержимое файла, а нечитаемое и ненайденное — пусто.

    Беду чтения отвечаем тем же «нет такого», что и отсутствие: раздача живёт
    внутри окна, и вылетевшая отсюда поломка ушла бы страницей отказа сервера
    вместо картинки. Пути к этому два и оба обычные: вложение читают, пока бот
    его дописывает, и читают уже после того, как снос данных удалил каталог.
    """
    if target is None or not target.is_file():
        return None
    try:
        return target.read_bytes()
    except OSError:
        logger.exception("не удалось прочитать для раздачи: %s", target)
        return None


def inside(root: Path, path: str) -> Path | None:
    """Путь запроса, приведённый к файлу внутри каталога, или пусто.

    Раздача слушает на localhost, и постучаться в неё может не только наше
    окно: адрес и порт видны любому процессу человека. Выпусти она путь с «..»,
    отдать можно было бы что угодно с диска — и файл базы, и ключи.

    Заслон стоит после приведения (`normpath`), а не до: `a/../../b` заслону по
    подстроке не поддаётся, а приведённому пути — поддаётся.

    Не только для раздачи: тем же заслоном мост проверяет адрес вложения,
    приехавший от окна обратно, — прежде чем отдать файл системе. Дело у обоих
    одно, и разъехаться этим двум проверкам нельзя.
    """
    relative = posixpath.normpath(path).lstrip("/")
    if not relative or relative == ".":
        return None
    target = (root / relative).resolve()
    if root not in target.parents:
        return None
    return target


def _or_index(path: str) -> str:
    """Путь страницы: корень — это она сама.

    Окно открывается по корню и ничего другого не просит. Отдай мы на нём
    отказ, человек увидел бы пустое окно вместо приложения.

    Путь тут не приводится: приведёт его `inside` следом, и делать это дважды
    незачем — «..» она разберёт и в пустом, и в непустом.
    """
    return path.lstrip("/") or "index.html"


_OWN_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
    ".woff2": "font/woff2",
    ".map": "application/json; charset=utf-8",
}
"""Типы того, из чего состоит сборка Vite, — своей таблицей, а не системной.

`mimetypes` на Windows читает реестр, а туда пишет всякий установщик: запись
`.js → text/plain` встречается и делает ровно то, от чего этот модуль и
написан. Chromium отказывается исполнять модуль, приехавший не тем типом, и
отказ виден только в консоли — на экране пусто, а причина в чужом реестре.
"""


def _content_type(target: Path) -> str:
    """Тип файла, по которому браузер решает, что с ним делать.

    Своё берётся первым, системное — только для того, чего в сборке обычно нет:
    картинок, положенных руками. Незнакомое отдаём двоичным: браузер тогда его
    сохранит, а не покажет как текст — показанный текстом шрифт выглядит
    поломкой страницы.
    """
    own = _OWN_TYPES.get(target.suffix.lower())
    if own is not None:
        return own
    guessed, _encoding = mimetypes.guess_type(target.name)
    if guessed is None:
        return "application/octet-stream"
    if guessed.startswith("text/"):
        return f"{guessed}; charset=utf-8"
    return guessed
