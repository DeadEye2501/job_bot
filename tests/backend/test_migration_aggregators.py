"""Следствия схемной ревизии агрегаторов: что она заводит и что держит база."""

import pytest
from alembic import command
from sqlalchemy.exc import IntegrityError

from backend.bootstrap import alembic_config
from backend.models import Vacancy, VacancyContact
from tests.conftest import INIT_REVISION
from tests.dbio import all_rows, put, sqlite_rows, sqlite_tables, sqlite_write
from tests.factories import vacancy_row
from tests.factories_aggregators import aggregator_row, vacancy_contact_row


def test_a_fresh_database_gets_one_web_search_row(migrations_target):
    """Новая база получает строку «Поиск по сети»: без хоста, выключенной, со входом.

    Входа у поиска по сети нет. Заведись строка «не вошёл», её нельзя было бы
    включить никогда.
    """
    command.upgrade(alembic_config(), "head")

    rows = sqlite_rows(
        migrations_target,
        "SELECT name, host, is_active, is_logged_in FROM aggregator",
    )
    assert rows == [("Поиск по сети", None, 0, 1)]


def test_the_revision_rolls_back_to_init(migrations_target):
    """Откат снимает всё, что ревизия завела, и база снова стоит на init."""
    command.upgrade(alembic_config(), "head")

    command.downgrade(alembic_config(), INIT_REVISION)

    assert not sqlite_tables(migrations_target) & {
        "aggregator", "vacancy_contact", "application", "screening", "mail_account"
    }
    left = {
        (table, row[1])
        for table in ("vacancy", "trash_event", "profile")
        for row in sqlite_rows(migrations_target, f"PRAGMA table_info({table})")
    }
    assert not left & {
        ("vacancy", "source_aggregator_id"), ("vacancy", "source_key"),
        ("trash_event", "source_aggregator_id"), ("trash_event", "source_key"),
        ("profile", "expected_salary"), ("profile", "gender"),
    }
    assert sqlite_rows(
        migrations_target, "SELECT version_num FROM alembic_version"
    ) == [(INIT_REVISION,)]


def test_the_rollback_keeps_the_rows_of_rebuilt_tables(migrations_target):
    """Откат пересобирает `vacancy`, и её строки вместе со ссылками на них живы.

    Пересборка таблицы, на которую ссылаются, при включённых ключах падает
    только на непустой базе: на пустой ссылаться нечему.
    """
    command.upgrade(alembic_config(), "head")
    sqlite_write(migrations_target,
                 "INSERT INTO vacancy (id) VALUES (1)",
                 "INSERT INTO vacancy_event (vacancy_id, kind) VALUES (1, 'found')")

    command.downgrade(alembic_config(), INIT_REVISION)

    assert sqlite_rows(migrations_target, "SELECT id FROM vacancy") == [(1,)]
    assert sqlite_rows(migrations_target, "SELECT vacancy_id FROM vacancy_event") == [(1,)]


async def test_the_same_contact_on_two_vacancies_is_allowed(session_factory):
    """Один адрес у двух вакансий — по строке у каждой: по нему и ищут вакансию."""
    first, second = vacancy_row(), vacancy_row()
    await put(session_factory, first, second)

    await put(
        session_factory,
        vacancy_contact_row(first.id, "hr@x.ru"),
        vacancy_contact_row(second.id, "hr@x.ru"),
    )

    assert len(await all_rows(session_factory, VacancyContact)) == 2


async def test_the_same_number_on_two_aggregators_is_allowed(session_factory):
    """Номер вакансии уникален только в пределах своего агрегатора."""
    hh, habr = aggregator_row(), aggregator_row(name="Хабр Карьера", host="career.habr.com")
    await put(session_factory, hh, habr)

    await put(
        session_factory,
        vacancy_row(source_aggregator_id=hh.id, source_key="vacancy/1"),
        vacancy_row(source_aggregator_id=habr.id, source_key="vacancy/1"),
    )

    assert len(await all_rows(session_factory, Vacancy)) == 2


async def test_a_second_aggregator_with_the_same_host_is_refused(session_factory):
    """Один сайт не заводится дважды."""
    await put(session_factory, aggregator_row(host="hh.ru"))

    with pytest.raises(IntegrityError):
        await put(session_factory, aggregator_row(name="hh", host="hh.ru"))


async def test_the_same_number_on_one_aggregator_is_refused(session_factory):
    """Вакансия с тем же номером на том же агрегаторе второй строкой не ложится."""
    hh = aggregator_row()
    await put(session_factory, hh)
    await put(session_factory, vacancy_row(source_aggregator_id=hh.id, source_key="vacancy/1"))

    with pytest.raises(IntegrityError):
        await put(
            session_factory,
            vacancy_row(source_aggregator_id=hh.id, source_key="vacancy/1"),
        )


async def test_the_same_contact_twice_on_one_vacancy_is_refused(session_factory):
    """Один контакт у одной вакансии — одна строка."""
    vacancy = vacancy_row()
    await put(session_factory, vacancy)
    await put(session_factory, vacancy_contact_row(vacancy.id, "hr@x.ru"))

    with pytest.raises(IntegrityError):
        await put(session_factory, vacancy_contact_row(vacancy.id, "hr@x.ru"))
