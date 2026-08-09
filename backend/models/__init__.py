"""Объявления таблиц базы, собранные из всех предметов.

Ввоз здесь — не удобство, а требование SQLAlchemy: ``Base.metadata`` полна
только тогда, когда объявлены все таблицы. Пакет без этих строк отдал бы
alembic autogenerate неполный набор, и тот выписал бы удаление недостающих.
"""

from backend.models.base import Base
from backend.models.contacts import HR, Company, TelegramChannel
from backend.models.enums import (
    BotMode,
    Currency,
    LlmConfigKind,
    StatusHistorySource,
    VacancyStatus,
)
from backend.models.message import Message
from backend.models.profile import (
    Profile,
    ProfileExperience,
    ProfileLanguage,
    ProfileSkill,
    profile_experience_skills,
)
from backend.models.settings import (
    BLACKLIST_KINDS,
    AppSetting,
    Blacklist,
    BotState,
    LlmConfig,
    TgAccount,
)
from backend.models.vacancy import (
    TrashEvent,
    Vacancy,
    VacancyEvent,
    VacancyStatusHistory,
)

__all__ = [
    "HR",
    "AppSetting",
    "Base",
    "BLACKLIST_KINDS",
    "Blacklist",
    "BotMode",
    "BotState",
    "Company",
    "Currency",
    "LlmConfig",
    "LlmConfigKind",
    "Message",
    "Profile",
    "ProfileExperience",
    "ProfileLanguage",
    "ProfileSkill",
    "StatusHistorySource",
    "TelegramChannel",
    "TgAccount",
    "TrashEvent",
    "Vacancy",
    "VacancyEvent",
    "VacancyStatus",
    "VacancyStatusHistory",
    "profile_experience_skills",
]
