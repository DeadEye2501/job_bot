"""Исходы исполнителя способа и то новое о мире, что он узнал по дороге."""

import logging
from collections.abc import Awaitable
from dataclasses import dataclass
from typing import Literal

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


@dataclass(frozen=True)
class Dropped:
    """Человек закончил работу по вакансии в окне подтверждения: ничего не ушло.

    Не промах способа: человек бросил вакансию, а не способ, и другой способ
    спросил бы его о том же. Статус вакансии не меняется — следующий прогон
    возьмёт её снова.
    """

    reason: str = "отказался человек"


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
