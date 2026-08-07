"""Построение объектов, которые тесты подают на вход коду.

Здесь и полезные нагрузки, и строки моделей — но только то, что живёт в
памяти, без сессии. Настоящая запись в базу остаётся делом самих тестов —
фабрика не знает ни про сессию, ни про схему.
"""

from backend.models import (
    AppSetting,
    BotMode,
    BotState,
    LlmConfig,
    LlmConfigKind,
    ProfileSkill,
    TgAccount,
)
from backend.payloads import ParsedVacancy

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
    идентификатор задан и переопределению не подлежит.
    """
    fields = {
        "api_id": 26276902,
        "api_hash_encrypted": None,
        "phone": "+70000000000",
        "password_encrypted": None,
        "session_blob_encrypted": None,
    }
    fields.update(overrides)
    return TgAccount(id=1, **fields)


def llm_config_row(kind: LlmConfigKind, **overrides) -> LlmConfig:
    """Строка настройки провайдера LLM. Род задаётся явно: он уникален."""
    fields = {
        "base_url": "http://provider.test",
        "api_key_encrypted": None,
        "model": "qwen",
    }
    fields.update(overrides)
    return LlmConfig(kind=kind, **fields)


def app_setting_row(key: str, value: str | None) -> AppSetting:
    """Строка настройки в общем словаре ключ-значение."""
    return AppSetting(key=key, value=value)


def bot_state_row(mode: BotMode) -> BotState:
    """Строка состояния бота. Тоже односрочная с проверкой `id = 1`."""
    return BotState(id=1, mode=mode)
