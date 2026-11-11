"""Ревизия v1.4 на живой базе, поднятой прежней версией.

База доводится до ревизии профилей и засевается, а v1.4 идёт отдельным
прогоном — как у человека, обновившего приложение. Одним прогоном от init
пересборка `profile` прошла бы и без своего гашения ключей: его оставляет
ревизия профилей до конца прогона.
"""

from alembic import command

from backend.bootstrap import alembic_config
from tests.dbio import sqlite_rows, sqlite_write

_PROFILES_REVISION = "5d2e7a9c4b13"


def test_the_profile_rebuild_keeps_the_rows_pointing_at_it(migrations_target):
    command.upgrade(alembic_config(), _PROFILES_REVISION)
    sqlite_write(
        migrations_target,
        "INSERT INTO profile (id, workspace_id, first_name, last_name, title, email, free_preferences) "
        "VALUES (1, 1, 'Анна', 'Иванова', 'Python', 'a@x.ru', 'без гемблинга')",
        "INSERT INTO profile_language (id, profile_id, language, level) VALUES (1, 1, 'Русский', 'native')",
    )

    command.upgrade(alembic_config(), "head")

    assert sqlite_rows(migrations_target, "SELECT id, first_name FROM profile") == [(1, "Анна")]
    assert sqlite_rows(migrations_target, "SELECT profile_id, language FROM profile_language") == [
        (1, "Русский")
    ]
    columns = [row[1] for row in sqlite_rows(migrations_target, "PRAGMA table_info(profile)")]
    assert "free_preferences" not in columns
    assert sqlite_rows(migrations_target, "SELECT * FROM profile_preference") == []
