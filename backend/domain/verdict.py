"""Приговор разобранному объявлению до того, как оно войдёт в граф статусов."""

from backend.models import VacancyStatus
from backend.payloads import ParsedVacancy

EMPTY_SKIP_REASON = "empty: no meaningful fields"


def is_empty_vacancy(parsed: ParsedVacancy | None) -> bool:
    """True если вакансия — очевидная пустышка/мусор и должна уходить в trash
    без обращения к LLM-валидатору.

    Критерии:
    - parsed is None — LLM не извлёк даже title.
    - title есть, но из 5 ключевых полей (description, stack, hr_contact,
      company_name, salary) заполнено МЕНЬШЕ ДВУХ. Раньше требовалось
      чтобы ВСЕ четыре отсутствовали (description+stack+hr_contact+
      company_name) — это съедало валидные короткие посты типа
      «Junior дизайнер | удалёнка | контакт @anna_hr» (есть title +
      hr_contact, остальное пусто → trash). Теперь нужны хотя бы ДВА
      сигнала из пяти.
    """
    if parsed is None:
        return True
    signals = (
        bool(parsed.description),
        bool(parsed.stack),
        bool(parsed.hr_contact),
        bool(parsed.company_name),
        bool(parsed.salary),
    )
    return sum(signals) < 2


def decide_vacancy_status(
    parsed: ParsedVacancy | None,
    score: int,
    blacklist_match: str | None,
    *,
    threshold: int,
) -> tuple[VacancyStatus, str | None]:
    if parsed is None:
        return VacancyStatus.NOT_FIT, "unparseable"
    if blacklist_match:
        return VacancyStatus.NOT_FIT, f"blacklist: {blacklist_match}"
    if score < threshold:
        return VacancyStatus.NOT_FIT, f"score {score} < {threshold}"
    return VacancyStatus.NEW, None
