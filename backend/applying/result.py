"""Исходы исполнителя способа и то новое о мире, что он узнал по дороге."""

from dataclasses import dataclass
from typing import Literal


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


Outcome = Literal["applied"] | Missed
