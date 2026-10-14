"""Ревизия автозаполнения резюме: новые поля профиля и резюме на агрегаторах."""

import pytest
from alembic import command
from sqlalchemy.exc import IntegrityError

from backend.bootstrap import alembic_config
from backend.models import AggregatorResume
from tests.dbio import all_rows, put, sqlite_rows, sqlite_tables, sqlite_write
from tests.factories_aggregators import aggregator_resume_row, aggregator_row

_BEFORE = "6cc10045aeb6"
_NEW_PROFILE_COLUMNS = {
    "patronymic", "patronymic_latin", "birth_date", "citizenship", "about_me", "resume_url",
}


def _columns(target, table: str) -> set[str]:
    return {row[1] for row in sqlite_rows(target, f"PRAGMA table_info({table})")}


def _with_a_person_and_a_site(target) -> None:
    command.upgrade(alembic_config(), _BEFORE)
    sqlite_write(
        target,
        "INSERT INTO profile (id, first_name, last_name, title, email, updated_at)"
        " VALUES (1, 'Иван', 'Петров', 'Разработчик', 'ivan@example.com', '2026-01-01')",
        "INSERT INTO aggregator (id, name, host) VALUES (2, 'HeadHunter', 'hh.ru')",
    )


def test_the_upgrade_keeps_the_rows_and_leaves_the_new_fields_empty(migrations_target):
    _with_a_person_and_a_site(migrations_target)

    command.upgrade(alembic_config(), "head")

    assert sqlite_rows(
        migrations_target,
        "SELECT first_name, patronymic, patronymic_latin, birth_date, citizenship,"
        " about_me, resume_url FROM profile",
    ) == [("Иван", None, None, None, None, None, None)]
    assert sqlite_rows(
        migrations_target, "SELECT host, can_add_resume FROM aggregator WHERE id = 2"
    ) == [("hh.ru", 0)]


def test_the_rollback_removes_what_it_added_and_keeps_the_rows(migrations_target):
    _with_a_person_and_a_site(migrations_target)
    command.upgrade(alembic_config(), "head")
    sqlite_write(
        migrations_target,
        "INSERT INTO aggregator_resume (aggregator_id, title, url, position)"
        " VALUES (2, 'Разработчик', 'https://hh.ru/resume/1', 0)",
    )

    command.downgrade(alembic_config(), _BEFORE)

    assert "aggregator_resume" not in sqlite_tables(migrations_target)
    assert not _columns(migrations_target, "profile") & _NEW_PROFILE_COLUMNS
    assert "can_add_resume" not in _columns(migrations_target, "aggregator")
    assert sqlite_rows(migrations_target, "SELECT first_name FROM profile") == [("Иван",)]
    assert sqlite_rows(
        migrations_target, "SELECT host FROM aggregator WHERE id = 2"
    ) == [("hh.ru",)]


async def test_one_resume_link_twice_on_one_site_is_refused(session_factory):
    hh = aggregator_row()
    await put(session_factory, hh)
    await put(session_factory, aggregator_resume_row(hh.id, url="https://hh.ru/resume/1"))

    with pytest.raises(IntegrityError):
        await put(session_factory, aggregator_resume_row(hh.id, url="https://hh.ru/resume/1"))


async def test_two_chosen_resumes_on_one_site_are_refused(session_factory):
    hh = aggregator_row()
    await put(session_factory, hh)
    await put(session_factory, aggregator_resume_row(hh.id, url="https://hh.ru/resume/1",
                                                     is_chosen=True))

    with pytest.raises(IntegrityError):
        await put(session_factory, aggregator_resume_row(hh.id, url="https://hh.ru/resume/2",
                                                         is_chosen=True))


async def test_each_site_has_its_own_chosen_resume(session_factory):
    hh, habr = aggregator_row(), aggregator_row(name="Хабр Карьера", host="career.habr.com")
    await put(session_factory, hh, habr)

    await put(
        session_factory,
        aggregator_resume_row(hh.id, url="https://hh.ru/resume/1", is_chosen=True),
        aggregator_resume_row(hh.id, url="https://hh.ru/resume/2"),
        aggregator_resume_row(habr.id, url="https://career.habr.com/r/1", is_chosen=True),
    )

    assert len(await all_rows(session_factory, AggregatorResume)) == 3
