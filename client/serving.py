"""Собранный фронт, отданный окну по http."""

from __future__ import annotations

import mimetypes
import posixpath
from pathlib import Path
from typing import Callable, Iterable


_NOT_FOUND = b"not found"


def built_front(root: Path) -> Callable:
    """Приложение WSGI, раздающее собранный фронт из названного каталога.

    **Раздаём по http, а не открываем файлы с диска.** Страница ввозит модули и
    спрашивает свои же файлы запросами, а с `file://` браузер отказывает и тому
    и другому по правилам происхождения — отказ при этом виден только в консоли
    страницы, а на экране просто пусто.

    Своё приложение, а не готовая раздача из библиотеки окна
    (`webview.http.BottleServer` поверх `bottle.static_file`). Готовая умеет то
    же и заслон на выход из корня держит сама; отличий три, и все нужны нам
    сегодня: корень должен отдавать страницу, а не отказ на каталоге; каталога
    сборки до слайса А4 нет вовсе, и раздача обязана это пережить; и главное —
    своё проверяется сторожами без окна, а готовая поднимается только вместе с
    ним.

    Каталога может не быть вовсе: собирает его Vite слайсом А4, а окно
    заводится этим. Отсутствие ничем не отличается от пустого — на всё отвечаем
    «нет такого», и окно открывается пустым вместо того, чтобы не открыться.
    """
    root = root.resolve()

    def application(environ: dict, start_response: Callable) -> Iterable[bytes]:
        target = _inside(root, environ.get("PATH_INFO", "/"))
        if target is None or not target.is_file():
            start_response("404 Not Found", [("Content-Type", "text/plain")])
            return [_NOT_FOUND]
        body = target.read_bytes()
        start_response(
            "200 OK",
            [
                ("Content-Type", _content_type(target)),
                ("Content-Length", str(len(body))),
            ],
        )
        return [body]

    return application


def _inside(root: Path, path: str) -> Path | None:
    """Путь запроса, приведённый к файлу внутри каталога, или пусто.

    Раздача слушает на localhost, и постучаться в неё может не только наше
    окно: адрес и порт видны любому процессу человека. Выпусти она путь с «..»,
    отдать можно было бы что угодно с диска — и файл базы, и ключи.

    Заслон стоит после приведения (`normpath`), а не до: `a/../../b` заслону по
    подстроке не поддаётся, а приведённому пути — поддаётся.
    """
    relative = posixpath.normpath(path).lstrip("/")
    if not relative or relative == ".":
        relative = "index.html"
    target = (root / relative).resolve()
    if target != root and root not in target.parents:
        return None
    return target


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
