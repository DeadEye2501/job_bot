"""Набор, с которым работает сессия агента."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import date
from typing import TypeVar

from sqlalchemy.ext.asyncio import AsyncSession

from adapters.browser import BrowserHost
from adapters.claude_code_agent import AgentEnd
from backend.agent.human_gate import HumanGate
from backend.flows.pipeline import IngestionPipeline


@dataclass(frozen=True)
class SessionPlan:
    """Одна сессия агента: наставление, задание, инструменты с подписями, поиск в сети."""

    system_prompt: str
    task: str
    tools: list[Callable]
    web_search: bool


RunSession = Callable[[SessionPlan], Awaitable[AgentEnd]]

T = TypeVar("T")


@dataclass
class AgentKit:
    """Всё, что нужно инструментам и обходу. Сессию обход получает функцией,
    а не водителем: так он не знает, кто ведёт агента."""

    pipeline: IngestionPipeline
    browser: BrowserHost
    gate: HumanGate
    run_session: RunSession
    today: date

    async def written(self, write: Callable[[AsyncSession], Awaitable[T]]) -> T:
        """Записать одной транзакцией и отдать ответ записи.

        Инструменты пишут по одному делу за вызов — отметку входа, отклик,
        скрининг, контакты, — и каждое либо ложится целиком, либо не ложится.
        """
        async with self.pipeline.session_factory() as session:
            async with session.begin():
                return await write(session)
