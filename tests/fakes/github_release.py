"""Подделка GitHub: API релизов и скачивание файла поверх подставного транспорта.

Подменяется сборка клиента (`adapters.github_release.make_client`), разбор ответа
и запись файла остаются боевыми. Сеть тестов не заперта, и без подмены проверка
ушла бы на живой GitHub.
"""

import hashlib
from urllib.parse import urlsplit

import httpx

from adapters.github_release import ASSET, LATEST
from tests.fakes.llm import serve

APP = b"MZ" + b"\0" * 2046
"""Содержимое файла релиза по умолчанию — маленький, но непустой exe."""

NEWER = "v99.0.0"
"""Тег релиза заведомо новее запущенной версии."""

FROM_CONTENT = object()
"""Сумма файла в ответе API — от его содержимого, как её считает GitHub."""


def download_url(tag: str, asset: str = ASSET) -> str:
    return f"https://github.com/DeadEye2501/job_bot/releases/download/{tag}/{asset}"


def serve_latest(monkeypatch, prepared: httpx.Response | BaseException,
                 files: dict[str, httpx.Response | BaseException] | None = None) -> None:
    """Последний релиз отвечает заготовленным; исключение — сеть не дотянулась.

    `files` — адреса скачивания и их ответы.
    """
    routes = {("GET", urlsplit(LATEST).path): prepared}
    routes |= {("GET", urlsplit(url).path): answer for url, answer in (files or {}).items()}
    serve(monkeypatch, "adapters.github_release.make_client", routes)


def in_pieces(content: bytes, size: int = 64 * 1024) -> httpx.Response:
    """Файл, отдаваемый кусками, как его отдаёт живой поток."""

    async def pieces():
        for start in range(0, len(content), size):
            yield content[start:start + size]

    return httpx.Response(200, content=pieces())


def serve_newer(monkeypatch, served: httpx.Response | BaseException | None = None,
                content: bytes = APP, digest=FROM_CONTENT) -> None:
    """Релиз новее запущенного, и его файл; `served` — что отдаёт скачивание,
    по умолчанию само `content` кусками."""
    file = in_pieces(content) if served is None else served
    serve_latest(monkeypatch, release_answer(NEWER, content=content, digest=digest),
                 files={download_url(NEWER): file})


def release_answer(tag: str, *, asset: str = ASSET, content: bytes = APP,
                   digest=FROM_CONTENT) -> httpx.Response:
    """Ответ API о релизе с одним файлом; `digest=None` — у файла суммы нет."""
    if digest is FROM_CONTENT:
        digest = "sha256:" + hashlib.sha256(content).hexdigest()
    return httpx.Response(200, json={
        "tag_name": tag,
        "assets": [{
            "name": asset,
            "browser_download_url": download_url(tag, asset),
            "size": len(content),
            "digest": digest,
        }],
    })
