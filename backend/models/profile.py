"""Таблицы анкеты кандидата."""

from datetime import date

from sqlalchemy import (
    JSON,
    Column,
    ForeignKey,
    Table,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.models.base import Base, IdMixin, UpdatedAtMixin, enum_column
from backend.models.enums import Gender, SalaryPeriod

profile_experience_skills = Table(
    "profile_experience_skills",
    Base.metadata,
    Column("experience_id", ForeignKey("profile_experience.id"), primary_key=True),
    Column("skill_id", ForeignKey("profile_skills.id"), primary_key=True),
)


class Profile(IdMixin, UpdatedAtMixin, Base):
    __tablename__ = "profile"

    first_name: Mapped[str]
    last_name: Mapped[str]
    title: Mapped[str]
    email: Mapped[str]
    phone: Mapped[str | None]
    location: Mapped[str | None]
    telegram_username: Mapped[str | None]
    github_url: Mapped[str | None]
    education: Mapped[str | None]
    # Подмножества перечней из backend/domain/taxonomy.py. Колонка JSON, так
    # что база чужое значение не отсеет — это делает код на входе.
    work_format: Mapped[list[str]] = mapped_column(
        JSON, server_default=text("'[]'")
    )
    grades: Mapped[list[str]] = mapped_column(
        JSON, server_default=text("'[]'")
    )
    free_preferences: Mapped[str | None]
    expected_salary: Mapped[int | None]
    expected_salary_currency: Mapped[str | None]
    expected_salary_period: Mapped[SalaryPeriod | None] = mapped_column(
        enum_column(SalaryPeriod, "salary_period")
    )
    first_name_latin: Mapped[str | None]
    last_name_latin: Mapped[str | None]
    gender: Mapped[Gender | None] = mapped_column(enum_column(Gender, "gender"))


class ProfileLanguage(IdMixin, Base):
    """Языки кандидата с уровнем владения для LLM-валидации.

    Один профиль — несколько языков (Русский native, Английский B1, и т.д.).
    Уровень — стандартный CEFR + "native". В промпт подмешивается строкой
    "Русский — native, Английский — B1, Армянский — A2".

    Уникальность по (profile_id, language) — нельзя дважды добавить тот
    же язык; редактирование = upsert по этой паре.
    """

    __tablename__ = "profile_language"
    __table_args__ = (
        UniqueConstraint("profile_id", "language"),
    )

    profile_id: Mapped[int] = mapped_column(ForeignKey("profile.id"))
    language: Mapped[str]
    level: Mapped[str]  # "A1" | "A2" | "B1" | "B2" | "C1" | "C2" | "native"


class ProfileSkill(IdMixin, Base):
    __tablename__ = "profile_skills"

    profile_id: Mapped[int] = mapped_column(ForeignKey("profile.id"))
    category: Mapped[str]
    name: Mapped[str]
    level: Mapped[int]
    aliases: Mapped[list[str]] = mapped_column(
        JSON, server_default=text("'[]'")
    )


class ProfileExperience(IdMixin, Base):
    __tablename__ = "profile_experience"

    profile_id: Mapped[int] = mapped_column(ForeignKey("profile.id"))
    company: Mapped[str]
    company_url: Mapped[str | None]
    role: Mapped[str]
    start_date: Mapped[date]
    end_date: Mapped[date | None]
    achievements: Mapped[list[str]] = mapped_column(
        JSON, server_default=text("'[]'")
    )
    responsibilities: Mapped[list[str]] = mapped_column(
        JSON, server_default=text("'[]'")
    )
    skills: Mapped[list["ProfileSkill"]] = relationship(
        secondary=profile_experience_skills
    )
