"""Скачивание обновления: файл остаётся на диске, только если сошёлся с релизом.

Отличие от `adapters/github_release`: тот только приносит байты, а здесь решают,
что с ними делать, — считать сумму, сверить, удалить при любой беде — и сколько
уже скачано.
"""

import hashlib
import logging
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Literal

from adapters import github_release
from adapters.github_release import Release
from backend.app_version import newer_version

logger = logging.getLogger(__name__)

UpdateOutcome = Literal["ok", "no_update", "broken"]
"""Чем кончилось скачивание: файл лёг, новее нет, скачанное не сошлось с релизом."""

_MB = 1024 * 1024


def new_exe_path() -> Path:
    """Куда ложится скачанное: рядом с exe, под его именем с `.new`. Рядом, а не
    во временной папке: подмена — переименование, а оно не ходит между дисками."""
    exe = Path(sys.executable)
    return exe.with_name(exe.name + ".new")


async def newer_release() -> Release | None:
    """Последний релиз, если он новее запущенного; иначе пусто. Одно решение на
    проверку и на скачивание: разойдись они, значок звал бы обновиться, а
    скачивание отвечало бы «новой версии нет»."""
    release = await github_release.latest_release()
    return release if release is not None and newer_version(release.tag) else None


async def download_update(target: Path, report: Callable[[int, int], None]) -> UpdateOutcome:
    """Скачать свежий релиз в `target` и сверить; ход — `report(скачано, всего)` в байтах.

    Релиз берётся здесь же, а не приходит доводом: между проверкой и нажатием
    могла выйти ещё одна версия. Файл, не дошедший до сверки или не сошедшийся,
    удаляется: недокачанный exe не должен лечь на место приложения. Сверяется
    сумма — совпавшая, она значит и тот же размер.
    """
    release = await newer_release()
    if release is None:
        return "no_update"
    kept = False
    try:
        sha256 = await _fetch(release, target, report)
        kept = sha256 == release.sha256
        if not kept:
            logger.warning("обновление %s не сошлось с релизом: сумма %s", release.tag, sha256)
    finally:
        if not kept:
            _remove(target)
    return "ok" if kept else "broken"


async def _fetch(release: Release, target: Path, report: Callable[[int, int], None]) -> str:
    """Записать файл релиза в `target`; ответ — его сумма.

    Ход — на каждом мегабайте и один раз в конце: чаще окну незачем, а кольцо
    вестей переполнилось бы.
    """
    digest = hashlib.sha256()
    got = reported = 0
    with target.open("wb") as file:

        def write(chunk: bytes) -> None:
            nonlocal got, reported
            file.write(chunk)
            digest.update(chunk)
            got += len(chunk)
            if got // _MB > reported // _MB:
                report(got, release.size)
                reported = got

        await github_release.download(release.url, write)
    if reported != got:
        report(got, release.size)
    return digest.hexdigest()


def _remove(target: Path) -> None:
    """Убрать недокачанное. Свежий файл бывает ненадолго занят антивирусом — тогда
    он остаётся до следующего запуска, который его уберёт, а исход скачивания
    своим и остаётся."""
    try:
        target.unlink(missing_ok=True)
    except OSError:
        logger.warning("не удалось убрать недокачанное обновление %s", target, exc_info=True)
