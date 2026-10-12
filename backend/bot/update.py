"""Скачивание обновления в месте прогона: пока оно идёт, прогон не начать.

Отличие от `backend/update_download`: тот качает и сверяет, а здесь — где эта
работа живёт и куда идёт её ход.
"""

import logging
from typing import Literal

from backend import update_download, updater
from backend.bot import slot
from backend.notify import fire

logger = logging.getLogger(__name__)

_LABEL = "Обновление"

DownloadOutcome = Literal[slot.CycleOutcome, update_download.UpdateOutcome, "handoff_failed"]
"""Чем кончилось скачивание: исходы места прогона, свои — нет новее, не сошлось, —
и «скачано, но копию-подменщик не запустить»."""


async def download_update(bot) -> DownloadOutcome:
    """Скачать свежий релиз рядом с exe, заняв место прогона, и отдать его
    копии-подменщику. «Стоп» гасит и скачивание."""

    def report(got: int, total: int) -> None:
        fire(bot.on_progress, "on_progress", "update", _LABEL, got, total)

    target = update_download.new_exe_path()
    # Первый шаг — сразу: пока GitHub отвечает и качается первый мегабайт, полоса
    # иначе стояла бы пустой и человек не видел бы, чем занят бот.
    outcome = await slot.answer_in_slot(
        bot,
        lambda: update_download.download_update(target, report),
        "update",
        ("update", _LABEL, 0, 0),
    )
    if outcome != "ok":
        return outcome
    try:
        updater.launch_updater(target)
    # Файл скачан и сверен, не вышел только запуск копии: это не «не скачалось»,
    # и человеку говорят то, что случилось, а приложение живёт дальше.
    except OSError:
        logger.exception("скачанное обновление не передано: копию-подменщик не запустить")
        return "handoff_failed"
    return outcome
