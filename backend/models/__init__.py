"""Объявления таблиц базы, собранные из всех предметов.

Ввоз здесь — не удобство, а требование SQLAlchemy: ``Base.metadata`` полна
только тогда, когда объявлены все таблицы. Пакет без этих строк отдал бы
alembic autogenerate неполный набор, и тот выписал бы удаление недостающих.
"""

from backend.models.application import Application, Screening
from backend.models.base import Base
from backend.models.contacts import HR, Aggregator, Company, TelegramChannel
from backend.models.enums import (
    ApplicationVia,
    BotMode,
    ContactAddedBy,
    Gender,
    LlmConfigKind,
    SalaryPeriod,
    StatusHistorySource,
    VacancyStatus,
    status_code,
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
    MailAccount,
    TgAccount,
)
from backend.models.vacancy import (
    TrashEvent,
    Vacancy,
    VacancyContact,
    VacancyEvent,
    VacancyStatusHistory,
)

__all__ = [
    "HR",
    "Aggregator",
    "AppSetting",
    "Application",
    "ApplicationVia",
    "Base",
    "BLACKLIST_KINDS",
    "Blacklist",
    "BotMode",
    "BotState",
    "Company",
    "ContactAddedBy",
    "Gender",
    "LlmConfig",
    "LlmConfigKind",
    "MailAccount",
    "Message",
    "Profile",
    "ProfileExperience",
    "ProfileLanguage",
    "ProfileSkill",
    "SalaryPeriod",
    "Screening",
    "StatusHistorySource",
    "status_code",
    "TelegramChannel",
    "TgAccount",
    "TrashEvent",
    "Vacancy",
    "VacancyContact",
    "VacancyEvent",
    "VacancyStatus",
    "VacancyStatusHistory",
    "profile_experience_skills",
]
