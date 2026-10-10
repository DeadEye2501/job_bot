"""Ревизия следа откликов: одно событие отклика вместо пяти родов."""

from alembic import command

from backend.bootstrap import alembic_config
from tests.dbio import sqlite_rows, sqlite_write

_BEFORE = "a9c3e1f07b42"
_OLD_KINDS = ("applied_elsewhere", "auto_send", "apply_failed", "vacancy_closed",
              "applied_sent", "parsed")


def _with_old_events(target) -> None:
    command.upgrade(alembic_config(), _BEFORE)
    sqlite_write(target, "INSERT INTO vacancy (id) VALUES (1)",
                 *(f"INSERT INTO vacancy_event (vacancy_id, kind) VALUES (1, '{kind}')"
                   for kind in _OLD_KINDS))


def test_old_apply_events_become_one_kind(migrations_target):
    _with_old_events(migrations_target)

    command.upgrade(alembic_config(), "head")

    kinds = {k for (k,) in sqlite_rows(migrations_target, "SELECT kind FROM vacancy_event")}
    assert kinds == {"applied", "parsed"}


def test_the_rollback_names_the_application_as_before(migrations_target):
    _with_old_events(migrations_target)
    command.upgrade(alembic_config(), "head")

    command.downgrade(alembic_config(), _BEFORE)

    kinds = {k for (k,) in sqlite_rows(migrations_target, "SELECT kind FROM vacancy_event")}
    assert kinds == {"applied_elsewhere", "parsed"}
