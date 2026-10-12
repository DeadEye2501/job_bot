"""Скачивание обновления в месте прогона: пока оно идёт, прогон не начать.

Отличие от `backend/update_download`: тот качает и сверяет, а здесь — где эта
работа живёт и куда идёт её ход.
"""

from typing import Literal

from backend import update_download, updater
from backend.bot import slot
from backend.notify import fire

_LABEL = "Обновление"

DownloadOutcome = Literal[slot.CycleOutcome, update_download.UpdateOutcome]
"""Чем кончилось скачивание: исходы места прогона и свои — нет новее, не сошлось."""


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
    if outcome == "ok":
        updater.launch_updater(target)
    return outcome
