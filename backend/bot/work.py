"""Работа в месте прогона с набором агента: набор живёт, пока идёт работа.

Отличие от `bot/slot`: тот решает, где работа идёт и кто её гасит; здесь —
с чем она идёт. Набор один на работу: поиск и отклик делят один браузер, а два
окна на один профиль Chromium не откроет.
"""

import logging
from collections.abc import Awaitable, Callable
from datetime import date
from typing import Literal

from adapters.browser import BrowserHost, find_browser
from backend.agent.kit import AgentKit
from backend.agent.sessions import live_session
from backend.agent.stops import HumanTimeout, LimitExhausted
from backend.bot import slot
from backend.notify import fire

logger = logging.getLogger(__name__)

# Одна фраза на все ожидания человека — капчу, вход и подтверждение отправки:
# что именно не дождалось ответа, человек видит сам по плашке, которая была.
HUMAN_TIMEOUT_NOTE = "Время ожидания истекло."
LIMIT_NOTE = "Исчерпан лимит подписки Claude Code — работа остановлена."

AgentStop = Literal["human_timeout", "limit"]
"""Чем работа с набором агента обрывается сама: человек не пришёл, лимит кончился."""

WorkOutcome = Literal[slot.CycleOutcome, AgentStop]
"""Чем кончилась работа с набором агента в месте прогона, если своих исходов у
неё нет. Исходы действий богаче собираются из этого, а не выписываются заново."""


async def agent_work(bot, work: Callable[[AgentKit], Awaitable[str]]) -> str:
    """Работа с набором агента: чистая пауза на человека в начале, отпущенный
    ждущий вызов и закрытый браузер в конце, чем бы ни кончилось. Набор на это
    время — `bot.kit`: им откликается конвейер."""
    kit = _kit(bot)
    bot.kit = kit
    kit.gate.reset()
    try:
        return await work(kit)
    except HumanTimeout:
        logger.warning(HUMAN_TIMEOUT_NOTE)
        fire(bot.on_round_note, "on_round_note", HUMAN_TIMEOUT_NOTE)
        return "human_timeout"
    except LimitExhausted:
        logger.warning(LIMIT_NOTE)
        fire(bot.on_round_note, "on_round_note", LIMIT_NOTE)
        return "limit"
    finally:
        bot.kit = None
        kit.gate.abort()
        await kit.browser.close()


async def in_slot(bot, job: Callable[[AgentKit], Awaitable[str]], label: str,
                  progress: tuple[str, str, int, int] | None = None) -> str:
    """Работа с набором агента в месте прогона: ответ работы или отказ места."""
    return await slot.answer_in_slot(bot, lambda: agent_work(bot, job), label, progress)


def _kit(bot) -> AgentKit:
    return AgentKit(
        pipeline=bot.ingestion,
        browser=BrowserHost(find_browser(), bot.rs.show_browser),
        gate=bot.human_gate,
        run_session=live_session(bot.rs.chat.model),
        today=date.today(),
    )
