"""Что схема заводит для агрегаторов и что держит база."""

import pytest
from alembic import command
from sqlalchemy.exc import IntegrityError

from backend.bootstrap import alembic_config
from backend.models import Vacancy, VacancyContact
from tests.dbio import all_rows, put, sqlite_rows
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
