"""Задачи сессий агента и их итоги."""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime

from backend.models import Aggregator


@dataclass(frozen=True)
class Source:
    """Строка агрегатора на время обхода. Пустой хост — «Поиск по сети»."""

    id: int
    name: str
    host: str | None
    last_run_at: datetime | None

    @classmethod
    def of(cls, row: Aggregator) -> "Source":
        """Снимок строки: обход живёт дольше сессии базы, а строка за её пределами не читается."""
        return cls(id=row.id, name=row.name, host=row.host, last_run_at=row.last_run_at)


@dataclass(frozen=True)
class Finished:
    """Агент сам завершил сессию: `done`, `failed`, `vacancy_closed` или `platform_closed`."""

    result: str
    reason: str


@dataclass(frozen=True)
class Failed:
    """Отклик выбранным способом не удался."""

    reason: str


@dataclass(frozen=True)
class Applied:
    """Отклик записан."""

    application_id: int


Outcome = Finished | Failed | Applied


@dataclass
class LoginJob:
    source: Source
    outcome: Outcome | None = None


@dataclass
class SeekJob:
    """Поиск на источнике. `refused` — модель эмбеддингов молчала: сессия — сбой,
    что бы ни сказал агент."""

    source: Source
    limit: int
    submitted: int = 0
    found: list[int] = field(default_factory=list)
    refused: bool = False
    outcome: Outcome | None = None


@dataclass
class ApplyJob:
    """Отклик одним способом.

    `method` — значение `ApplicationVia`; `profile_id` — профиль браузера:
    агрегатора или «Поиска по сети»; `forced` — ручной отклик, Applied и из
    Not Fit, Scam, Ghosting; `letter_writer` — значение из `LETTER_WRITERS`;
    `delivery` — отправка письма с записью отклика, которая переживает сессию.
    """

    vacancy_id: int
    method: str
    target: str
    aggregator_id: int | None
    profile_id: int
    forced: bool
    simulated: bool
    letter_writer: str
    letter_checks: int = 0
    outcome: Outcome | None = None
    delivery: asyncio.Task | None = None
