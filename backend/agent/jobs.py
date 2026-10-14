"""Задачи сессий агента и их итоги."""

from dataclasses import dataclass, field
from datetime import datetime

from backend.domain.apply_order import Way
from backend.models import Aggregator
from backend.payloads import SeenResume


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
    """Агент сам завершил сессию: итогом из `RESULTS` своей задачи."""

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
class ScanJob:
    """Перечень резюме человека на сайте агрегатора. Способа отклика у неё нет:
    сайт — её источник, как у входа. `reported` — список дошёл до базы: `done`
    без него значит, что раздела резюме агент не нашёл."""

    source: Source
    reported: bool = False
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
    отправкой каждой страницы ждать подтверждения человека; `resume` —
    название и ссылка резюме, выбранного человеком на сайте агрегатора
    (у формы работодателя — пусто).

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
    resume: SeenResume | None = None
    confirming: bool = False
    letter_checks: int = 0
    outcome: Outcome | None = None
    confirmed: dict[tuple[str, str], dict] = field(default_factory=dict)
    unscreened: dict[tuple[str, str, str], dict] = field(default_factory=dict)


@dataclass
class FillJob:
    """Заполнение резюме на сайте агрегатора по профилю.

    `resume_url` — резюме, которое перезаписывается; пусто — заводится новое.
    `accepted` — принятые пункты раскладки по ключу «адрес страницы, селектор
    поля», той же формы, что `ApplyJob.confirmed`: вписать можно только их.
    `page_checks` — сколько раз проверяющий смотрел запасной путь на адресе.
    `general` — поля, названные общими (у пункта было обоснование запасного
    пути): вписать в них можно только проверенное. `skipped` — подписи
    необязательных полей, оставленных без пункта, по адресу последней
    раскладки — для сводки в журнал. Итог `required_missing`
    ставит только `report_required_missing`, с перечнем полей, — поэтому его
    нет в `RESULTS`.
    """

    source: Source
    resume_url: str | None = None
    outcome: Outcome | None = None
    accepted: dict[tuple[str, str], dict] = field(default_factory=dict)
    page_checks: dict[str, int] = field(default_factory=dict)
    general: set[tuple[str, str]] = field(default_factory=set)
    skipped: dict[str, list[str]] = field(default_factory=dict)


RESULTS = {
    LoginJob: frozenset({"done"}),
    ScanJob: frozenset({"done"}),
    FillJob: frozenset({"done"}),
    SeekJob: frozenset({"done", "failed"}),
    ApplyJob: frozenset({"vacancy_closed", "platform_closed", "not_fit", "resume_missing"}),
}
"""Итоги, которыми агент завершает сессию каждой задачи."""

HUMAN_KINDS = ("captcha", "login")
"""Зачем агент зовёт человека."""
