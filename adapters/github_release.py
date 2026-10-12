"""Последний релиз приложения на GitHub.

Отличие от `adapters/web_page`: тот только собирает клиент страниц, а здесь
знают форму ответа API релизов. Клиент берётся у него же.
"""

from dataclasses import dataclass

import httpx

from adapters.web_page import page_client

LATEST = "https://api.github.com/repos/DeadEye2501/job_bot/releases/latest"
ASSET = "JobBot.exe"
_TIMEOUT_SEC = 20.0
_USER_AGENT = "JobBot-updater"


@dataclass(frozen=True)
class Release:
    tag: str
    url: str
    size: int
    sha256: str


def make_client() -> httpx.AsyncClient:
    return page_client(_TIMEOUT_SEC, _USER_AGENT)


async def latest_release() -> Release | None:
    """Последний релиз с файлом приложения, который есть чем сверить; иначе пусто.

    Пусто и тогда, когда релизов нет вовсе: API отвечает на это 404, а человеку
    это значит «новой версии нет». Файл без контрольной суммы обновлением не
    считается: скачанное сверить было бы не с чем.

    Беда сети, отказ GitHub и ответ не той формы уходят наверх: что сказать о
    них человеку, решает зовущий.
    """
    async with make_client() as client:
        response = await client.get(LATEST)
    if response.status_code == httpx.codes.NOT_FOUND:
        return None
    response.raise_for_status()
    body = response.json()
    asset = next((a for a in body["assets"] if a["name"] == ASSET), None)
    if asset is None or not asset["digest"]:
        return None
    return Release(
        tag=body["tag_name"],
        url=asset["browser_download_url"],
        size=asset["size"],
        sha256=asset["digest"].removeprefix("sha256:"),
    )
