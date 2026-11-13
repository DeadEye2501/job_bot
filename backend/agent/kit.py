"""Набор, с которым работает сессия агента."""

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import date
from typing import TypeVar

from sqlalchemy.ext.asyncio import AsyncSession

from adapters.browser import BrowserHost
from adapters.claude_code_agent import AgentEnd
from backend.agent.human_gate import HumanGate
from backend.domain.resume_choice import ResumeSlot
from backend.flows.pipeline import IngestionPipeline
from backend.repository.agent_profile import build_agent_profile
from backend.repository.profile_languages import read_reply_language
from backend.repository.reply_resume import ReplyResume, reply_resume
from backend.repository.vacancy_pay import vacancy_salary_lines


def _never() -> bool:
    return False


@dataclass(frozen=True)
class SessionPlan:
    """Одна сессия агента: наставление, задание, инструменты с подписями, поиск в сети.

    `paused()` — стоит ли сейчас работа самой сессии: тогда её срок не течёт.
    `tool_timeout_ms` — срок одного вызова инструмента; пусто — общий срок
    процесса агента (`claude_code_agent`). `cut` — событие, которое гасит
    сессию снаружи: у отклика в браузере — окно, закрытое человеком; пусто —
    гасить снаружи нечему.
    """

    system_prompt: str
    task: str
    tools: list[Callable]
    web_search: bool
    paused: Callable[[], bool] = _never
    tool_timeout_ms: int | None = None
    cut: asyncio.Event | None = None


RunSession = Callable[[SessionPlan], Awaitable[AgentEnd]]

T = TypeVar("T")


@dataclass
class AgentKit:
    """Всё, что нужно инструментам и обходу. Сессию обход получает функцией,
    а не водителем: так он не знает, кто ведёт агента.

    `window_closed` — событие идущего отклика в браузере: закрытое человеком
    окно гасит этот отклик, а не всю работу (`bot/work.window_closed`); пусто —
    отклика в браузере нет. `shut_hosts` — сайты, чьё окно человек закрыл
    посреди отклика: до конца работы с набором способом не предлагаются.
    """

    pipeline: IngestionPipeline
    browser: BrowserHost
    gate: HumanGate
    run_session: RunSession
    today: date
    window_closed: asyncio.Event | None = None
    shut_hosts: set[str] = field(default_factory=set)

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

    async def profile_text(self, session: AsyncSession, salary: list[str], slot: ResumeSlot = "main") -> str:
        """Анкета для агента на сегодня; есть ли фото — по тому же `photo_file`,
        что даёт файл инструменту прикладывания. `salary` — строки зарплаты этой
        задачи (`agent/salary_view`); `slot` — чья ссылка на резюме в анкете
        (`build_agent_profile`)."""
        photo = self.pipeline.photo_file() is not None
        return await build_agent_profile(session, self.today, photo, salary, slot)

    async def reply_resume(self, session: AsyncSession, language: str) -> ReplyResume | None:
        """Резюме к отклику на `language` по файлам, лежащим сейчас на диске."""
        return await reply_resume(session, self.pipeline.cv_file(), self.pipeline.cv_en_file(), language)

    async def vacancy_profile_text(self, session: AsyncSession, vacancy_id: int) -> str:
        """Анкета для отклика и писем к вакансии: зарплата в ней — названная сумма,
        ссылка на резюме — того резюме, что идёт к отклику (`reply_resume`)."""
        resume = await self.reply_resume(session, await read_reply_language(session, vacancy_id))
        return await self.profile_text(session, await vacancy_salary_lines(session, vacancy_id),
                                       resume.slot if resume else "main")
