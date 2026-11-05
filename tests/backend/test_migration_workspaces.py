"""Ревизия профилей на живой базе: всё прежнее уходит в первый профиль, откат возвращает его.

База поднимается до ревизии init, засевается мимо ORM — модели описывают
`head`, — и доводится до `head`. Сверяется сырым SQL по тем же причинам.
"""

from alembic import command

from backend.bootstrap import alembic_config
from tests.conftest import INIT_REVISION
from tests.dbio import sqlite_rows, sqlite_write

_VACANCY = "INSERT INTO vacancy (id, title, status, is_parsed) VALUES ({id}, 'Python', 'New', 1)"


def _seeded(db_file, *statements: str) -> None:
    """Поднять базу до init, засеять и довести до `head`."""
    command.upgrade(alembic_config(), INIT_REVISION)
    sqlite_write(db_file, *statements)
    command.upgrade(alembic_config(), "head")


def _profile(id_: int) -> str:
    return (
        "INSERT INTO profile (id, first_name, last_name, title, email) "
        f"VALUES ({id_}, 'Анна', 'Иванова', 'Python', 'a@x.ru')"
    )


def test_existing_rows_join_the_first_workspace(migrations_target):
    _seeded(
        migrations_target,
        _VACANCY.format(id=1),
        "INSERT INTO trash_event (id, reason) VALUES (1, 'empty')",
        _profile(1),
    )

    for table in ("vacancy", "trash_event", "profile"):
        assert sqlite_rows(migrations_target, f"SELECT workspace_id FROM {table}") == [(1,)]
    assert sqlite_rows(migrations_target, "SELECT id, is_active FROM workspace") == [(1, 1)]


def test_switches_move_to_the_first_workspace(migrations_target):
    _seeded(
        migrations_target,
        "INSERT INTO telegram_channel (id, username, is_active, last_processed_msg_id) "
        "VALUES (5, 'jobs', 0, 77)",
        "INSERT INTO aggregator (id, name, host, is_active, last_run_at) "
        "VALUES (9, 'HeadHunter', 'hh.ru', 1, '2026-01-01 12:00:00')",
        "INSERT INTO aggregator_resume (id, aggregator_id, title, url, position, is_chosen) "
        "VALUES (3, 9, 'Разработчик', 'https://hh.ru/resume/1', 0, 1)",
        "INSERT INTO blacklist (id, kind, value, active) VALUES (4, 'company', 'Рога', 1)",
        "INSERT INTO blacklist (id, kind, value, active) VALUES (6, 'company', 'Копыта', 0)",
    )

    assert sqlite_rows(
        migrations_target,
        "SELECT workspace_id, channel_id, is_active, last_processed_msg_id FROM workspace_channel",
    ) == [(1, 5, 0, 77)]
    assert sqlite_rows(
        migrations_target,
        "SELECT workspace_id, is_active, last_run_at, chosen_resume_id "
        "FROM workspace_aggregator WHERE aggregator_id = 9",
    ) == [(1, 1, "2026-01-01 12:00:00", 3)]
    assert sqlite_rows(
        migrations_target, "SELECT workspace_id, blacklist_id, active FROM workspace_blacklist"
    ) == [(1, 4, 1)]


def test_an_unread_channel_that_is_on_moves_to_the_first_workspace(migrations_target):
    """Самый частый случай: канал включён, но ещё не читан."""
    _seeded(
        migrations_target,
        "INSERT INTO telegram_channel (id, username, is_active) VALUES (5, 'jobs', 1)",
    )

    assert sqlite_rows(
        migrations_target,
        "SELECT workspace_id, channel_id, is_active, last_processed_msg_id FROM workspace_channel",
    ) == [(1, 5, 1, None)]


def test_a_site_with_only_a_chosen_resume_moves_to_the_first_workspace(migrations_target):
    """Выключенный, не обходившийся сайт с выбранным резюме — не «строки нет»."""
    _seeded(
        migrations_target,
        "INSERT INTO aggregator (id, name, host, is_active) VALUES (9, 'HeadHunter', 'hh.ru', 0)",
        "INSERT INTO aggregator_resume (id, aggregator_id, title, url, position, is_chosen) "
        "VALUES (3, 9, 'Разработчик', 'https://hh.ru/resume/1', 0, 1)",
    )

    assert sqlite_rows(
        migrations_target,
        "SELECT workspace_id, is_active, last_run_at, chosen_resume_id "
        "FROM workspace_aggregator WHERE aggregator_id = 9",
    ) == [(1, 0, None, 3)]


def test_resume_and_photo_paths_move_to_the_first_workspace(migrations_target):
    _seeded(
        migrations_target,
        "INSERT INTO app_settings (key, value) VALUES ('cv_path', 'C:/cv.pdf')",
        "INSERT INTO app_settings (key, value) VALUES ('photo_path', 'profile/photo.png')",
    )

    assert sqlite_rows(migrations_target, "SELECT cv_path, photo_path FROM workspace") == [
        ("C:/cv.pdf", "profile/photo.png")
    ]
    assert sqlite_rows(
        migrations_target,
        "SELECT key FROM app_settings WHERE key IN ('cv_path', 'photo_path')",
    ) == []


def test_missing_paths_become_empty_in_the_first_workspace(migrations_target):
    _seeded(migrations_target)

    assert sqlite_rows(migrations_target, "SELECT cv_path, photo_path FROM workspace") == [("", "")]


def test_rows_pointing_at_vacancies_survive(migrations_target):
    _seeded(
        migrations_target,
        "INSERT INTO hr (id, name) VALUES (1, 'Мария')",
        _VACANCY.format(id=1),
        "INSERT INTO message (id, hr_id, vacancy_id, text) VALUES (1, 1, 1, 'Здравствуйте')",
        "INSERT INTO application (id, vacancy_id, via, target, sent_at) "
        "VALUES (1, 1, 'email', 'hr@x.ru', '2026-01-01 12:00:00')",
        "INSERT INTO screening (id, application_id, from_us, text, position) "
        "VALUES (1, 1, 0, 'Опыт?', 0)",
        "INSERT INTO vacancy_status_history (id, vacancy_id, message_id, status) "
        "VALUES (1, 1, 1, 'Applied')",
        "INSERT INTO vacancy_event (id, vacancy_id, kind) VALUES (1, 1, 'ingested')",
        "INSERT INTO vacancy_contact (id, vacancy_id, value, match_key, added_by) "
        "VALUES (1, 1, 'hr@x.ru', 'hr@x.ru', 'parse')",
    )

    for table in (
        "message", "application", "screening", "vacancy_status_history",
        "vacancy_event", "vacancy_contact",
    ):
        assert sqlite_rows(migrations_target, f"SELECT count(*) FROM {table}") == [(1,)], table
    assert sqlite_rows(migrations_target, "SELECT vacancy_id FROM message") == [(1,)]
    assert sqlite_rows(migrations_target, "PRAGMA foreign_key_check") == []


def test_downgrade_restores_the_first_workspace_values(migrations_target):
    _seeded(
        migrations_target,
        "INSERT INTO telegram_channel (id, username, is_active, last_processed_msg_id) "
        "VALUES (5, 'jobs', 0, 77)",
        "INSERT INTO aggregator (id, name, host, is_active, last_run_at) "
        "VALUES (9, 'HeadHunter', 'hh.ru', 1, '2026-01-01 12:00:00')",
        "INSERT INTO aggregator_resume (id, aggregator_id, title, url, position, is_chosen) "
        "VALUES (3, 9, 'Разработчик', 'https://hh.ru/resume/1', 0, 1)",
        "INSERT INTO blacklist (id, kind, value, active) VALUES (4, 'company', 'Рога', 0)",
        "INSERT INTO app_settings (key, value) VALUES ('cv_path', 'C:/cv.pdf')",
    )

    command.downgrade(alembic_config(), INIT_REVISION)

    assert sqlite_rows(
        migrations_target, "SELECT is_active, last_processed_msg_id FROM telegram_channel"
    ) == [(0, 77)]
    assert sqlite_rows(
        migrations_target, "SELECT is_active, last_run_at FROM aggregator WHERE id = 9"
    ) == [(1, "2026-01-01 12:00:00")]
    assert sqlite_rows(migrations_target, "SELECT is_chosen FROM aggregator_resume") == [(1,)]
    assert sqlite_rows(migrations_target, "SELECT active FROM blacklist") == [(0,)]
    assert sqlite_rows(
        migrations_target, "SELECT key, value FROM app_settings WHERE key IN ('cv_path', 'photo_path')"
    ) == [("cv_path", "C:/cv.pdf"), ("photo_path", "")]


def test_downgrade_drops_other_workspaces(migrations_target):
    _seeded(migrations_target, "INSERT INTO hr (id, name) VALUES (1, 'Мария')")
    sqlite_write(
        migrations_target,
        "INSERT INTO workspace (id, is_active) VALUES (2, 0)",
        "INSERT INTO vacancy (id, title, status, is_parsed, workspace_id) "
        "VALUES (1, 'Python', 'New', 1, 2)",
        "INSERT INTO application (id, vacancy_id, via, target, sent_at) "
        "VALUES (1, 1, 'email', 'hr@x.ru', '2026-01-01 12:00:00')",
        "INSERT INTO screening (id, application_id, from_us, text, position) "
        "VALUES (1, 1, 0, 'Опыт?', 0)",
        "INSERT INTO message (id, hr_id, vacancy_id, text) VALUES (1, 1, 1, 'Здравствуйте')",
        "INSERT INTO vacancy_status_history (id, vacancy_id, message_id, status) "
        "VALUES (1, 1, 1, 'Applied')",
        "INSERT INTO trash_event (id, reason, workspace_id) VALUES (1, 'empty', 2)",
        "INSERT INTO profile (id, first_name, last_name, title, email, workspace_id) "
        "VALUES (1, 'Анна', 'Иванова', 'Python', 'a@x.ru', 2)",
        "INSERT INTO profile_skills (id, profile_id, category, name, level) "
        "VALUES (1, 1, 'backend', 'Python', 3)",
        "INSERT INTO profile_experience (id, profile_id, company, role, start_date) "
        "VALUES (1, 1, 'Рога', 'Разработчик', '2020-01-01')",
        "INSERT INTO profile_experience_skills (experience_id, skill_id) VALUES (1, 1)",
    )

    command.downgrade(alembic_config(), INIT_REVISION)

    for table in (
        "vacancy", "application", "screening", "vacancy_status_history", "trash_event",
        "profile", "profile_skills", "profile_experience", "profile_experience_skills",
    ):
        assert sqlite_rows(migrations_target, f"SELECT count(*) FROM {table}") == [(0,)], table
    assert sqlite_rows(migrations_target, "SELECT id, vacancy_id FROM message") == [(1, None)]
    assert sqlite_rows(migrations_target, "PRAGMA foreign_key_check") == []


def test_downgrade_switches_off_a_channel_without_a_workspace_row(migrations_target):
    """Канала без строки профиля прежняя схема включённым не получает."""
    _seeded(migrations_target)
    sqlite_write(migrations_target, "INSERT INTO telegram_channel (id, username) VALUES (5, 'jobs')")

    command.downgrade(alembic_config(), INIT_REVISION)

    assert sqlite_rows(
        migrations_target, "SELECT is_active, last_processed_msg_id FROM telegram_channel"
    ) == [(0, None)]


def test_downgrade_keeps_the_active_workspace_when_it_is_not_the_first(migrations_target):
    """Откат берёт значения и данные активного профиля, а не первого."""
    _seeded(
        migrations_target,
        "INSERT INTO telegram_channel (id, username, is_active) VALUES (5, 'jobs', 0)",
    )
    sqlite_write(
        migrations_target,
        "INSERT INTO workspace (id, is_active, cv_path) VALUES (2, 0, 'C:/второе.pdf')",
        "UPDATE workspace SET is_active = 0 WHERE id = 1",
        "UPDATE workspace SET is_active = 1 WHERE id = 2",
        "INSERT INTO workspace_channel (workspace_id, channel_id, is_active, last_processed_msg_id) "
        "VALUES (1, 5, 0, 10), (2, 5, 1, 20)",
        "INSERT INTO vacancy (id, title, status, is_parsed, workspace_id) VALUES "
        "(1, 'первого', 'New', 1, 1), (2, 'второго', 'New', 1, 2)",
    )

    command.downgrade(alembic_config(), INIT_REVISION)

    assert sqlite_rows(
        migrations_target, "SELECT is_active, last_processed_msg_id FROM telegram_channel"
    ) == [(1, 20)]
    assert sqlite_rows(migrations_target, "SELECT title FROM vacancy") == [("второго",)]
    assert sqlite_rows(
        migrations_target, "SELECT value FROM app_settings WHERE key = 'cv_path'"
    ) == [("C:/второе.pdf",)]
