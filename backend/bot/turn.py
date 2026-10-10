"""Полный оборот автоматики: недоразобранное и каналы, затем обход агрегаторов.

Отличие от соседей: `bot/channels` правит каналы из окна, `bot/aggregators`
ведёт сам обход, а здесь — порядок, в котором оборот их зовёт. Зовут его цикл
и кнопка ▶, и порядок у обоих один.
"""

import logging

from backend.bot import aggregators, slot

logger = logging.getLogger(__name__)


async def ingest_round(bot) -> None:
    """Оборот приёма: сперва дочитать отложенное, потом идти за новым.

    Недоразобранная строка ждёт статьи, которой не хватило на приёме, и в
    окне её не видно вовсе — ни в списке, ни в отказах. Подбирались бы такие
    только при подъёме — объявление ждало бы до следующего запуска приложения,
    а работает оно сутками.

    Сорвавшийся подбор обход не отменяет: свежие объявления человек ждёт
    больше, чем дочитанные.
    """
    try:
        await bot.ingestion.recover_orphan_vacancies()
    except Exception:
        logger.exception("orphan recovery failed")
    await bot.ingestion.poll_active_channels()


async def run_turn(bot, label: str) -> slot.CycleOutcome:
    """Оборот целиком: приём в месте прогона, затем обход агрегаторов.

    «busy» — место прогона занято. Погашенный «Стопом» или сорвавшийся приём
    обход агрегаторов не пускает; смена режима посреди оборота его не
    отменяет — начатое дорабатывает.
    """
    outcome, _ = await slot.run_in_slot(bot, lambda: ingest_round(bot), label)
    if outcome != "ok" or bot.stop_event.is_set():
        return outcome
    await aggregators.launch_round(bot)
    return "ok"
