from dataclasses import dataclass
from typing import Literal

from backend.models import (
    HR,
    Company,
    TelegramChannel,
    Vacancy,
    VacancyEvent,
    VacancyStatus,
    VacancyStatusHistory,
)


FitVerdict = Literal["fit", "reject", "trash"]


@dataclass(frozen=True)
class Classification:
    status: VacancyStatus
    explanation: str | None


@dataclass(frozen=True)
class ParsedVacancy:
    title: str
    description: str | None
    company_name: str | None
    company_website: str | None
    hr_contact: str | None
    # Любой нон-Telegram способ откликнуться, который LLM нашёл в посте
    # (email, ссылка на форму отклика, careers-страница, ссылка на job-
    # площадку, явная инструкция «писать в комментариях»). Берётся
    # дословно из текста поста. Сохраняется в ``Vacancy.notes`` строкой
    # «Контакты: <other_contact>» — у юзера должен быть способ
    # откликнуться даже когда TG-контакта в посте нет. None если в
    # посте никакого контакта кроме (или включая) TG-аккаунта.
    other_contact: str | None
    # Stack split into "обязательные" (required) and "будет плюсом" (preferred)
    # at parse time by the LLM. Both lists are already canonicalized,
    # version-stripped, capitalized and unique across BOTH lists (the LLM is
    # explicitly instructed not to put the same skill into both groups). The
    # split is consumed by ``score_parsed`` for weighting and by
    # ``validate_vacancy_fit`` (sees both lists separately); everywhere else
    # (UI chips, DB ``Vacancy.stack`` column) reads ``stack`` — see the
    # property below — which simply joins both lists in declaration order.
    stack_required: list[str]
    stack_preferred: list[str]
    grade: str | None
    salary: str | None
    remote: str | None
    location: str | None

    @property
    def stack(self) -> list[str]:
        """Объединённый стек (required + preferred) — потребители этого
        view не нуждаются в делении: запись в БД-колонку ``Vacancy.stack``,
        ``is_empty_vacancy``-чек, отображение в UI. Возвращаем новый list,
        не view — чтобы случайная мутация у потребителя не утекла в
        required/preferred.
        """
        return list(self.stack_required) + list(self.stack_preferred)


@dataclass(frozen=True)
class FitValidation:
    verdict: FitVerdict
    reason: str | None


@dataclass(frozen=True)
class VacancyDetail:
    vacancy: Vacancy
    history: list[VacancyStatusHistory]
    events: list[VacancyEvent]


@dataclass(frozen=True)
class HrWithCount:
    hr: HR
    vacancy_count: int
    last_company_name: str | None
    unread_count: int = 0
    is_blacklisted: bool = False


@dataclass(frozen=True)
class HrDetail:
    """Full payload for the Contacts / HR detail pane (05).

    ``last_company_id`` complements ``last_company_name`` so the UI can
    deep-link into the Companies tab on click. ``unread_count`` powers the
    «N непрочитанных» chip in the head. ``blacklist_value`` is non-NULL
    when an active row exists in the blacklist table for this HR — UI
    paints a red chip + flips the menu item to «Убрать из blacklist».
    """
    hr: HR
    vacancy_count: int
    last_company_id: int | None
    last_company_name: str | None
    unread_count: int
    blacklist_value: str | None = None


@dataclass(frozen=True)
class CompanyDetail:
    """Full payload for the Contacts/Companies detail pane (06).

    ``hr_count`` = distinct HRs with at least one vacancy at this company,
    powering the «N HR» chip in the head. ``blacklist_value`` is non-NULL
    when an active row exists in the blacklist table for this company —
    UI paints the red chip + flips the menu item to «Убрать из blacklist».
    """
    company: Company
    vacancy_count: int
    hr_count: int
    blacklist_value: str | None = None


@dataclass(frozen=True)
class CompanyWithCount:
    company: Company
    vacancy_count: int
    is_blacklisted: bool = False


@dataclass(frozen=True)
class ChannelWithCount:
    channel: TelegramChannel
    vacancy_count: int
    is_blacklisted: bool = False


@dataclass(frozen=True)
class ChannelStats:
    """Computed stats for the Contacts/Channels detail pane.

    All counts are over the full lifetime of the channel; only
    ``vacancies_per_day`` is windowed (last 30 days) — это про «пропускная
    способность сейчас», а не средняя за всю историю канала.

    ``status_counts`` keys are ``VacancyStatus.value`` strings (e.g.
    ``"New"``, ``"Applied"``) so the frontend can drive the breakdown bar
    and legend without a server-side ordering choice.
    """
    status_counts: dict[str, int]
    total: int
    vacancies_per_day: float
    # KPI ratios as integer percent, 0-100. None when the denominator is 0
    # (UI shows «—» вместо «0%», иначе пустой канал выглядит как
    # провальная воронка).
    fit_percent: int | None
    apply_percent: int | None
    response_percent: int | None


@dataclass(frozen=True)
class ChannelDetail:
    channel: TelegramChannel
    stats: ChannelStats
    blacklist_value: str | None = None
