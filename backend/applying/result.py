"""Исходы исполнителя способа и то новое о мире, что он узнал по дороге."""

import logging
from collections.abc import Awaitable
from dataclasses import dataclass
from typing import Literal

# Исход сессии агента и исход способа сразу: «Закончить» нажимают и в окне
# Telegram и почты, и посреди сессии агента — объявлен он там, где его ставит сессия.
from backend.agent.jobs import Dropped

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TelegramClosed:
    """Telegram просил не писать; `until` — время UNIX, до которого."""

    until: float


@dataclass(frozen=True)
class SiteClosed:
    site_id: int


Lesson = TelegramClosed | SiteClosed


@dataclass(frozen=True)
class Missed:
    """Способ не сработал: причина для журнала и, если узнали, новое о мире."""

    reason: str
    lesson: Lesson | None = None


@dataclass(frozen=True)
class Unfit:
    """Вакансия человеку не подходит: форма поставила условие, которое анкета исключает.

    Не промах способа: другой способ упрётся в то же условие, и пробовать его незачем.
    """

    reason: str


Outcome = Literal["applied"] | Missed | Unfit | Dropped

GONE = Missed("вакансия удалена")
"""Вакансию удалили, пока до неё дошла очередь: способ пробовать не на чем."""


async def delivered(record: Awaitable, vacancy_id: int) -> Outcome:
    """Письмо уже у адресата — отклик состоялся, чем бы ни кончилась его запись.

    Промах здесь отдал бы вакансию следующему способу, и работодатель получил
    бы второй отклик; сорвавшаяся запись остаётся строкой в журнале.
    """
    try:
        await record
    except Exception:
        logger.exception("вакансия %d: письмо ушло, а отклик не записан", vacancy_id)
    return "applied"
