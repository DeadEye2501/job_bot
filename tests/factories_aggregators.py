"""Строки откликов вне Telegram: агрегаторы, контакты вакансии, отклики, почта."""

from backend.crypto import encrypt_str
from backend.models import (
    Aggregator,
    Application,
    ApplicationVia,
    ContactAddedBy,
    MailAccount,
    Screening,
    VacancyContact,
)
from backend.repository.aggregators import WEB_SEARCH_NAME
from tests.factories import EPOCH


def aggregator_row(**overrides) -> Aggregator:
    """Строка агрегатора. Хост уникален — задаётся явно, где строк больше одной."""
    fields = {"name": "HeadHunter", "host": "hh.ru"}
    fields.update(overrides)
    return Aggregator(**fields)


def web_search_row(**overrides) -> Aggregator:
    """Строка «Поиск по сети»: без хоста, под своим именем."""
    return aggregator_row(**{"name": WEB_SEARCH_NAME, "host": None, **overrides})


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


def mail_account_row() -> MailAccount:
    """Строка почты, готовой к отправке: адрес, пароль шифром и сервер."""
    return MailAccount(id=1, address="me@mail.test", password_encrypted=encrypt_str("secret"),
                       smtp_host="smtp.mail.test", smtp_port=465)
