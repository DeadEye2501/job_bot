"""Обновление приложения из релизов GitHub: какая версия запущена и есть ли новее.

Примесь к `System`: страница видит один предмет, `api.system`, а обновление —
своя работа, которой в файле домена было бы тесно.
"""

from __future__ import annotations

import logging
import sys

import httpx

from adapters import github_release
from backend.app_version import VERSION, newer_version
from client.bridge.answer import reply

logger = logging.getLogger(__name__)

GITHUB_SILENT = "GitHub не ответил — проверьте связь."


class AppUpdate:
    """Версия и проверка обновления. Нужен `_hub` — мотор, на котором идёт проверка."""

    def version(self) -> dict:
        """Запущенная версия и может ли эта копия обновиться.

        Может только собранный exe: из исходников подменять нечего, и решается
        это здесь, один раз, — окно получает уже решённое.
        """
        return {"ok": {"version": VERSION, "updatable": bool(getattr(sys, "frozen", False))}}

    def check_update(self) -> dict:
        """Есть ли на GitHub версия новее запущенной.

        Беда сети — ответ с `trouble`, а не отказ: отказ окно рисует плашкой
        ошибки, а это не поломка приложения. Молчать ли о ней, решает окно: при
        запуске молчит, по нажатию говорит.
        """

        async def run() -> dict:
            try:
                release = await github_release.latest_release()
            # Ответ не той формы — чаще всего страница портала сети Wi-Fi с кодом
            # 200 — для человека та же беда связи, что и обрыв.
            except (httpx.HTTPError, ValueError, KeyError, TypeError):
                logger.warning("проверка обновления: GitHub не ответил", exc_info=True)
                return {"newer": None, "trouble": GITHUB_SILENT}
            return {"newer": release and newer_version(release.tag), "trouble": None}

        return reply(self._hub.runner, run())
