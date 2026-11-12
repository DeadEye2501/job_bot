"""Объявления таблиц базы, собранные из всех предметов.

Ввоз здесь — не удобство, а требование SQLAlchemy: ``Base.metadata`` полна
только тогда, когда объявлены все таблицы. Пакет без этих строк отдал бы
alembic autogenerate неполный набор, и тот выписал бы удаление недостающих.
"""

from backend.models.application import Application, Screening
from backend.models.base import Base
from backend.models.contacts import HR, Aggregator, AggregatorResume, Company, TelegramChannel
from backend.models.enums import (
    ApplicationVia,
    BotMode,
    ContactAddedBy,
    Gender,
    LlmConfigKind,
    PreferenceKind,
    SalaryPeriod,
    StatusHistorySource,
    VacancyStatus,
    status_code,
)
from backend.models.message import Message
from backend.models.profile import (
    STACK_LINKS,
    CoverLetter,
    Profile,
    ProfileExperience,
    ProfileLanguage,
    ProfilePreference,
    ProfileProject,
    ProfileSkill,
    profile_experience_skills,
    profile_project_skills,
)
from backend.models.rates import CurrencyRate
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
from backend.models.workspace import (
    Workspace,
    WorkspaceAggregator,
    WorkspaceBlacklist,
    WorkspaceChannel,
)

__all__ = [
    "CurrencyRate",
    "HR",
    "Aggregator",
    "AggregatorResume",
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
    "CoverLetter",
    "Gender",
    "LlmConfig",
    "LlmConfigKind",
    "MailAccount",
    "Message",
    "PreferenceKind",
    "Profile",
    "ProfileExperience",
    "ProfileLanguage",
    "ProfilePreference",
    "ProfileProject",
    "ProfileSkill",
    "STACK_LINKS",
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
    "Workspace",
    "WorkspaceAggregator",
    "WorkspaceBlacklist",
    "WorkspaceChannel",
    "profile_experience_skills",
    "profile_project_skills",
]
