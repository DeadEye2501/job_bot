"""Построение объектов, которые тесты подают на вход коду.

Здесь и полезные нагрузки, и строки моделей — но только то, что живёт в
памяти, без сессии. Настоящая запись в базу остаётся делом самих тестов —
фабрика не знает ни про сессию, ни про схему.
"""

from datetime import datetime, timedelta

from backend.models import (
    AppSetting,
    BotMode,
    BotState,
    Company,
    HR,
    LlmConfig,
    LlmConfigKind,
    Message,
    ProfileSkill,
    StatusHistorySource,
    TelegramChannel,
    TgAccount,
    Vacancy,
    VacancyEvent,
    VacancyStatus,
    VacancyStatusHistory,
)
from backend.payloads import ParsedVacancy

EPOCH = datetime(2026, 1, 1, 12, 0)
"""Опорный момент для строк, у которых порядок по времени и есть предмет проверки.

Наивный: колонки объявлены `DateTime(timezone=True)`, но SQLite хранит их без
зоны и возвращает наивными — смешивать с осведомлёнными нельзя, сравнение
упадёт с `TypeError`.
"""


def at(minutes: int) -> datetime:
    """Момент на `minutes` минут позже опорного."""
    return EPOCH + timedelta(minutes=minutes)


def _empty_vacancy() -> dict:
    """Свежий словарь умолчаний на каждый вызов.

    `stack_required`/`stack_preferred` — списки, и общий на все вызовы
    словарь-константа отдавал бы один и тот же объект списка каждой
    построенной вакансии: мутация в одном тесте протекала бы в другой.
    Функция вместо константы гарантирует, что у двух вызовов подряд
    списки — разные объекты.
    """
    return {
        "title": "Python-разработчик",
        "description": None,
        "company_name": None,
        "company_website": None,
        "hr_contact": None,
        "other_contact": None,
        "stack_required": [],
        "stack_preferred": [],
        "grade": None,
        "salary": None,
        "remote": None,
        "location": None,
    }


def parsed_vacancy(**overrides) -> ParsedVacancy:
    """Разобранная вакансия: заголовок есть, остальное пусто.

    Умолчание выбрано так, чтобы тест называл ровно те поля, которые
    проверяет: всё незаданное заведомо не влияет на результат.
    """
    return ParsedVacancy(**{**_empty_vacancy(), **overrides})


def profile_skill(
    name: str, level: int, aliases: list | None = None
) -> ProfileSkill:
    """Навык профиля вне сессии — в базу не пишется, нужен как вход в подсчёт."""
    return ProfileSkill(
        name=name, level=level, aliases=aliases or [], category="backend"
    )


def tg_account_row(**overrides) -> TgAccount:
    """Строка учётной записи Telegram. Шифротексты кладёт вызывающий.

    Таблица односрочная с проверкой `id = 1` на уровне базы, поэтому
    умолчание для идентификатора — 1, но переопределение сливается до
    вызова конструктора: `id=` в overrides проходит, а не падает сырым
    `TypeError` о повторном ключевом аргументе.
    """
    fields = {
        "id": 1,
        "api_id": 26276902,
        "api_hash_encrypted": None,
        "phone": "+70000000000",
        "password_encrypted": None,
        "session_blob_encrypted": None,
    }
    fields.update(overrides)
    return TgAccount(**fields)


def llm_config_row(kind: LlmConfigKind, **overrides) -> LlmConfig:
    """Строка настройки провайдера LLM. Род задаётся явно: он уникален."""
    fields = {
        "base_url": "http://provider.test",
        "api_key_encrypted": None,
        "model": "qwen",
    }
    fields.update(overrides)
    return LlmConfig(kind=kind, **fields)


def app_setting_row(key: str, value: str | None, **overrides) -> AppSetting:
    """Строка настройки в общем словаре ключ-значение."""
    fields = {"key": key, "value": value}
    fields.update(overrides)
    return AppSetting(**fields)


def bot_state_row(mode: BotMode) -> BotState:
    """Строка состояния бота. Тоже односрочная с проверкой `id = 1`."""
    return BotState(id=1, mode=mode)


def vacancy_row(**overrides) -> Vacancy:
    """Строка вакансии, годная к выдаче в список.

    `is_parsed` — True: `list_vacancies` отбрасывает неразобранные, и
    умолчание False заставляло бы каждый тест списка называть поле, к
    которому он не имеет отношения. Тест про сам отбор задаёт его явно.

    `created_at` задан, а не оставлен базе: у колонки серверное умолчание
    `CURRENT_TIMESTAMP`, и две строки, вставленные в одну секунду, получили
    бы одинаковую метку — порядок по времени стал бы делом случая.
    """
    fields = {
        "title": "Python-разработчик",
        "status": VacancyStatus.NEW,
        "is_parsed": True,
        "created_at": EPOCH,
    }
    fields.update(overrides)
    return Vacancy(**fields)


def hr_row(**overrides) -> HR:
    """Строка HR."""
    fields = {"name": "Мария", "telegram_username": "maria"}
    fields.update(overrides)
    return HR(**fields)


def company_row(**overrides) -> Company:
    """Строка компании. Имя уникально на уровне базы — задаётся явно."""
    fields = {"name": "Контур", "aliases": []}
    fields.update(overrides)
    return Company(**fields)


def channel_row(**overrides) -> TelegramChannel:
    """Строка канала-источника."""
    fields = {"username": "pyjobs", "title": "Питон-вакансии"}
    fields.update(overrides)
    return TelegramChannel(**fields)


def message_row(**overrides) -> Message:
    """Строка переписки. Текст обязателен на уровне базы."""
    fields = {
        "text": "здравствуйте",
        "is_incoming": True,
        "hr_id": None,
        "vacancy_id": None,
        "sent_at": EPOCH,
    }
    fields.update(overrides)
    return Message(**fields)


def vacancy_event_row(vacancy_id: int, **overrides) -> VacancyEvent:
    """Событие обработки вакансии. Метка времени задаётся явно — по ней сортируют."""
    fields = {"kind": "parsed", "created_at": EPOCH}
    fields.update(overrides)
    return VacancyEvent(vacancy_id=vacancy_id, **fields)


def status_history_row(vacancy_id: int, **overrides) -> VacancyStatusHistory:
    """Запись о смене статуса. Метка времени задаётся явно — по ней сортируют."""
    fields = {
        "status": VacancyStatus.APPLIED,
        "previous_status": VacancyStatus.NEW,
        "source": StatusHistorySource.USER,
        "changed_at": EPOCH,
    }
    fields.update(overrides)
    return VacancyStatusHistory(vacancy_id=vacancy_id, **fields)
