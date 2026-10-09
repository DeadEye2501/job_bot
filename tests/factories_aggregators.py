"""Строки агрегаторов, контактов вакансии и откликов вне Telegram."""

from backend.models import (
    Aggregator,
    Application,
    ApplicationVia,
    ContactAddedBy,
    Screening,
    VacancyContact,
)
from tests.factories import EPOCH


def aggregator_row(**overrides) -> Aggregator:
    """Строка агрегатора. Хост уникален — задаётся явно, где строк больше одной."""
    fields = {"name": "HeadHunter", "host": "hh.ru"}
    fields.update(overrides)
    return Aggregator(**fields)


def vacancy_contact_row(vacancy_id: int, value: str, **overrides) -> VacancyContact:
    """Контакт вакансии. Ключ по умолчанию — само значение: тест, которому нужна
    нормальная форма, пишет его явно."""
    fields = {"match_key": value, "added_by": ContactAddedBy.USER}
    fields.update(overrides)
    return VacancyContact(vacancy_id=vacancy_id, value=value, **fields)


def application_row(vacancy_id: int, **overrides) -> Application:
    """Отклик вне Telegram, ушедший на сайте агрегатора."""
    fields = {
        "via": ApplicationVia.AGGREGATOR,
        "target": "https://hh.ru/vacancy/1",
        "sent_at": EPOCH,
    }
    fields.update(overrides)
    return Application(vacancy_id=vacancy_id, **fields)


def screening_row(application_id: int, position: int, **overrides) -> Screening:
    """Реплика скрининга: по умолчанию вопрос работодателя."""
    fields = {"from_us": False, "text": "Сколько лет опыта?"}
    fields.update(overrides)
    return Screening(application_id=application_id, position=position, **fields)
