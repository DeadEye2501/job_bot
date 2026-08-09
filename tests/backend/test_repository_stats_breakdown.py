"""Следствия разбивки вакансий по статусам за период.

Разбивка называет все статусы, включая те, которых сейчас нет ни у одной
вакансии: экран рисует воронку постоянным набором столбцов, и пропущенный
статус сдвинул бы их.

В отличие от сводных счётчиков в шапке, здесь считается нынешний статус, а не
история: это снимок «где всё лежит сейчас», а не «через что прошло».
"""

from backend.models import VacancyStatus
from backend.repository.stats_summary import get_stats_status_breakdown
from tests.dbio import put
from tests.factories import days_ago, status_history_row, vacancy_row


async def test_an_empty_database_names_every_status_with_a_zero(session):
    """На пустой базе названы все статусы, у каждого ноль."""
    got = await get_stats_status_breakdown(session, period="all")

    assert got["period"] == "all"
    assert set(got["counts"]) == {s.value for s in VacancyStatus}
    assert set(got["counts"].values()) == {0}


async def test_only_parsed_vacancies_are_counted(session, session_factory):
    """Недоразобранные вакансии в разбивку не идут."""
    await put(
        session_factory,
        vacancy_row(status=VacancyStatus.NEW, is_parsed=True),
        vacancy_row(status=VacancyStatus.NEW, is_parsed=False),
    )

    counts = (await get_stats_status_breakdown(session, period="all"))["counts"]

    assert counts["New"] == 1


async def test_the_current_status_is_counted_not_the_history(
    session, session_factory
):
    """Считается нынешний статус, а не пройденные.

    Вакансия побывала в «отправлено», а сейчас снова новая: в шапке она
    останется отправленной навсегда, а здесь лежит в «новых».
    """
    vacancy = vacancy_row(status=VacancyStatus.NEW)
    await put(session_factory, vacancy)
    await put(
        session_factory,
        status_history_row(vacancy.id, status=VacancyStatus.APPLIED),
    )

    counts = (await get_stats_status_breakdown(session, period="all"))["counts"]

    assert counts["New"] == 1
    assert counts["Applied"] == 0


async def test_the_window_cuts_by_the_creation_date(session, session_factory):
    """Окно отсекает по дате появления вакансии."""
    await put(
        session_factory,
        vacancy_row(status=VacancyStatus.NEW, created_at=days_ago(1)),
        vacancy_row(status=VacancyStatus.NEW, created_at=days_ago(40)),
    )

    within = (await get_stats_status_breakdown(session, period="week"))["counts"]
    lifetime = (await get_stats_status_breakdown(session, period="all"))["counts"]

    assert within["New"] == 1
    assert lifetime["New"] == 2


async def test_each_status_gets_its_own_tally(session, session_factory):
    """Каждый статус получает свой счёт, а не общий."""
    await put(
        session_factory,
        vacancy_row(status=VacancyStatus.NEW),
        vacancy_row(status=VacancyStatus.NEW),
        vacancy_row(status=VacancyStatus.OFFER),
        vacancy_row(status=VacancyStatus.GHOSTING),
    )

    counts = (await get_stats_status_breakdown(session, period="all"))["counts"]

    assert counts["New"] == 2
    assert counts["Offer"] == 1
    assert counts["Ghosting"] == 1
    assert counts["Decline"] == 0
