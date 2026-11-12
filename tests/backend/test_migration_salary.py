"""Ревизия зарплаты на живой базе, поднятой версией 1.4.

База доводится до v1.4 и засевается, а ревизия зарплаты идёт отдельным
прогоном — как у человека, обновившего приложение.
"""

from alembic import command

from backend.bootstrap import alembic_config
from tests.dbio import sqlite_rows, sqlite_write

_V1_4 = "f2e88ee2a3a6"


def _seeded_to_v1_4(target) -> None:
    command.upgrade(alembic_config(), _V1_4)
    sqlite_write(
        target,
        "INSERT INTO workspace (id, is_active) VALUES (2, 0)",
        "INSERT INTO profile (id, workspace_id, first_name, last_name, title, email,"
        " expected_salary, expected_salary_currency, expected_salary_period)"
        " VALUES (1, 1, 'Анна', 'Иванова', 'Python', 'a@x.ru', 3000, NULL, NULL)",
        "INSERT INTO profile (id, workspace_id, first_name, last_name, title, email,"
        " expected_salary, expected_salary_currency, expected_salary_period)"
        " VALUES (2, 2, 'Иван', 'Петров', 'Go', 'i@x.ru', 250000, '₽', 'year')",
        "INSERT INTO vacancy (id, workspace_id, salary, salary_min, salary_max)"
        " VALUES (1, 1, '$3000', 3000, 3000)",
        "INSERT INTO vacancy (id, workspace_id, salary) VALUES (2, 1, NULL)",
        "INSERT INTO profile_language (id, profile_id, language, level) VALUES (1, 1, 'Русский', 'native')",
    )


def test_old_vacancies_get_no_period(migrations_target):
    """Из «$30/hr» в базе лежит только 30: месяц назвал бы ставку месячной."""
    _seeded_to_v1_4(migrations_target)

    command.upgrade(alembic_config(), "head")

    assert sqlite_rows(migrations_target, "SELECT id, salary_period FROM vacancy ORDER BY id") == [
        (1, None), (2, None)
    ]


def test_the_expected_salary_stays_and_the_minimum_starts_empty(migrations_target):
    _seeded_to_v1_4(migrations_target)

    command.upgrade(alembic_config(), "head")

    assert sqlite_rows(
        migrations_target,
        "SELECT id, expected_salary, minimum_salary, expected_salary_currency,"
        " expected_salary_period FROM profile ORDER BY id",
    ) == [(1, 3000, None, "$", "month"), (2, 250000, None, "₽", "year")]


def test_rows_pointing_at_the_profile_survive_its_rebuild(migrations_target):
    """Ревизия пересобирает `profile`; языки, ссылающиеся на него, остаются."""
    _seeded_to_v1_4(migrations_target)

    command.upgrade(alembic_config(), "head")

    assert sqlite_rows(migrations_target, "SELECT profile_id, language FROM profile_language") == [(1, "Русский")]
    assert sqlite_rows(migrations_target, "PRAGMA foreign_key_check") == []


def test_the_rates_cache_starts_filled(migrations_target):
    _seeded_to_v1_4(migrations_target)

    command.upgrade(alembic_config(), "head")

    rates = dict(sqlite_rows(migrations_target, "SELECT code, per_usd FROM currency_rate"))
    assert rates == {
        "USD": 1.0, "RUB": 82.742974, "EUR": 0.899865,
        "AMD": 360.646084, "KZT": 446.086013, "GEL": 2.594131,
    }


def test_the_downgrade_brings_back_the_v1_4_schema(migrations_target):
    _seeded_to_v1_4(migrations_target)
    command.upgrade(alembic_config(), "head")

    command.downgrade(alembic_config(), _V1_4)

    assert sqlite_rows(
        migrations_target, "SELECT name FROM sqlite_master WHERE name = 'currency_rate'"
    ) == []
    assert "salary_period" not in _columns(migrations_target, "vacancy")
    assert "minimum_salary" not in _columns(migrations_target, "profile")
    assert sqlite_rows(
        migrations_target,
        "SELECT id, expected_salary, expected_salary_currency FROM profile ORDER BY id",
    ) == [(1, 3000, "$"), (2, 250000, "₽")]


def _columns(target, table: str) -> set[str]:
    return {name for _, name, *_ in sqlite_rows(target, f"PRAGMA table_info({table})")}
