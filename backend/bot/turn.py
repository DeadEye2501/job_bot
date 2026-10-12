"""Полный оборот автоматики одной задачей: недоразобранное, каналы, агрегаторы.

Отличие от соседей: `bot/channels` правит каналы из окна, `bot/aggregators`
ведёт сам обход, а здесь — порядок, в котором оборот их зовёт. Зовут его цикл
и кнопка ▶, и порядок у обоих один.
"""

import asyncio
import logging
from backend.agent.kit import AgentKit
from backend.agent.stops import RUN_STOPPERS
from backend.bot import aggregators, slot, work

logger = logging.getLogger(__name__)


def launch_turn(bot, label: str) -> asyncio.Task | None:
    """Оборот одной задачей в месте прогона; пусто — место занято.

    Одна задача — один «Стоп»: погашенный на каналах оборот агрегаторы уже не
    пускает. Набор агента живёт весь оборот: отобранное каналами откликается
    тем же набором, что и найденное агрегаторами.
    """

    async def turn(kit: AgentKit) -> str:
        await _recover(bot)
        await bot.ingestion.poll_active_channels()
        await aggregators.seek_all(bot, kit)
        return "ok"

    if not slot.launch_in_slot(bot, lambda: work.agent_work(bot, turn), label):
        return None
    return bot.launched_task


async def _recover(bot) -> None:
    """Сперва дочитать отложенное, потом идти за новым.

    Недоразобранная строка ждёт статьи, которой не хватило на приёме, и в
    окне её не видно вовсе — ни в списке, ни в отказах. Подбирались бы такие
    только при подъёме — объявление ждало бы до следующего запуска приложения,
    а работает оно сутками.

    Сорвавшийся подбор обход не отменяет: свежие объявления человек ждёт
    больше, чем дочитанные.
    """
    try:
        await bot.ingestion.recover_orphan_vacancies()
    except RUN_STOPPERS:
        raise
    except Exception:
        logger.exception("orphan recovery failed")
