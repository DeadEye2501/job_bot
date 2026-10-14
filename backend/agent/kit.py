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
from backend.repository.agent_profile import build_agent_profile


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

    async def read(self, query: Callable[[AsyncSession], Awaitable[T]]) -> T:
        """Прочитать в своей сессии и отдать ответ — пара `written` для чтения."""
        async with self.pipeline.session_factory() as session:
            return await query(session)

    async def profile_text(self, session: AsyncSession) -> str:
        """Анкета для агента на сегодня; есть ли фото — по тому же `photo_file`,
        что даёт файл инструменту прикладывания."""
        return await build_agent_profile(session, self.today, self.pipeline.photo_file() is not None)
