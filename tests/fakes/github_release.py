"""Подделка API релизов GitHub: настоящий клиент поверх подставного транспорта.

Подменяется сборка клиента (`adapters.github_release.make_client`), разбор ответа
остаётся боевым. Сеть тестов не заперта, и без подмены проверка ушла бы на живой
GitHub.
"""

from urllib.parse import urlsplit

import httpx

from adapters.github_release import ASSET, LATEST
from tests.fakes.llm import serve

_DIGEST = "sha256:" + "ab" * 32


def serve_latest(monkeypatch, prepared: httpx.Response | BaseException) -> None:
    """Последний релиз отвечает заготовленным; исключение — сеть не дотянулась."""
    serve(monkeypatch, "adapters.github_release.make_client",
          {("GET", urlsplit(LATEST).path): prepared})


def release_answer(tag: str, *, asset: str = ASSET, digest: str | None = _DIGEST) -> httpx.Response:
    """Ответ API о релизе с одним файлом."""
    return httpx.Response(200, json={
        "tag_name": tag,
        "assets": [{
            "name": asset,
            "browser_download_url": f"https://github.com/DeadEye2501/job_bot/releases/download/{tag}/{asset}",
            "size": 1024,
            "digest": digest,
        }],
    })
