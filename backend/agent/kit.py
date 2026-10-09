"""Набор, с которым работает сессия агента."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import date

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


@dataclass
class AgentKit:
    """Всё, что нужно инструментам и обходу. Сессию обход получает функцией,
    а не водителем: так он не знает, кто ведёт агента."""

    pipeline: IngestionPipeline
    browser: BrowserHost
    gate: HumanGate
    run_session: RunSession
    today: date
