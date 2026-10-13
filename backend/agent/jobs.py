"""Задачи сессий агента и их итоги."""

from dataclasses import dataclass, field
from datetime import datetime

from backend.domain.apply_order import Way
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
    """Агент сам завершил сессию: `done`, `failed`, `vacancy_closed`, `platform_closed` или `not_fit`."""

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


@dataclass(frozen=True)
class Dropped:
    """Человек закончил работу по вакансии в окне подтверждения: ничего не ушло.

    Не промах способа: человек бросил вакансию, а не способ, и другой способ
    спросил бы его о том же. Статус вакансии не меняется — следующий прогон
    возьмёт её снова.
    """

    reason: str = "отказался человек"


Outcome = Finished | Failed | Applied | Dropped

FINAL = (Applied, Dropped)
"""Исходы, после которых сессия итог не меняет: отклик уже ушёл, или человек
закончил работу по вакансии. Переписанные, они дали бы второй отклик тому же
работодателю или отправку, от которой человек отказался."""

FINAL_ANSWER = (
    "Итог окончательный и не меняется: отклик уже записан или человек закончил "
    "работу по вакансии. Заверши работу."
)


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

    `profile_id` — профиль браузера: агрегатора или «Поиска по сети»;
    `letter_writer` — значение из `LETTER_WRITERS`; `confirming` — перед
    отправкой каждой страницы ждать подтверждения человека.

    `confirmed` — подтверждённые человеком пункты по ключу «адрес страницы,
    селектор поля»: всё, что можно вписать. `unscreened` — подтверждённые и ещё
    не легшие в запись скрининга; к ключу добавлена подпись: подтверждённое
    снова после ошибки сайта заменяет прежнее, а следующий шаг формы на том же
    адресе и под тем же селектором ложится своим вопросом.
    """

    vacancy_id: int
    way: Way
    profile_id: int
    simulated: bool
    letter_writer: str
    confirming: bool = False
    letter_checks: int = 0
    outcome: Outcome | None = None
    confirmed: dict[tuple[str, str], dict] = field(default_factory=dict)
    unscreened: dict[tuple[str, str, str], dict] = field(default_factory=dict)


RESULTS = {
    LoginJob: frozenset({"done"}),
    SeekJob: frozenset({"done", "failed"}),
    ApplyJob: frozenset({"vacancy_closed", "platform_closed", "not_fit"}),
}
"""Итоги, которыми агент завершает сессию каждой задачи."""

HUMAN_KINDS = ("captcha", "login")
"""Зачем агент зовёт человека."""
