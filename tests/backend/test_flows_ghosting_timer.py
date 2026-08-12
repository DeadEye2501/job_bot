"""Следствия проверки на молчание HR.

Отклик, на который никто не ответил, висел бы в «отправлен» вечно и мешал бы
пользователю видеть, где переписка живая. Поэтому раз в оборот цикла бот
смотрит, по каким вакансиям HR молчит дольше положенного, и переводит их в
«молчание».

Сама проверка дешёвая: в короткий список попадают только отправленные и
идущие вакансии. Сбой её не роняет оборот — она удобство, а не работа, ради
которой бот запущен.
"""

import pytest

from backend.models import Vacancy, VacancyStatus
from tests.dbio import all_rows, put
from tests.factories import days_ago, vacancy_row

# Границы названы числами нарочно, а не через `GHOSTING_TIMEOUT_DAYS`. Считай
# их из самого срока — и проверки поедут вместе с ним: смени его на четверо
# суток, и всё останется зелёным, а отклики уходили бы в «молчание» через
# четыре дня. Две недели — обещание пользователю, и сторожить надо его.
_SILENT_DAYS = 15
_STILL_WAITING_DAYS = 13


def _long_ago():
    """Время, с которого молчание уже считается затянувшимся."""
    return days_ago(_SILENT_DAYS)


def _recently():
    """Время, с которого ждать ответа ещё рано."""
    return days_ago(_STILL_WAITING_DAYS)


async def test_a_long_silence_moves_the_vacancy(make_pipeline, session_factory):
    """Затянувшееся молчание переводит вакансию в «молчание»."""
    await put(
        session_factory,
        vacancy_row(title="молчат", status=VacancyStatus.APPLIED, created_at=_long_ago()),
    )
    pipeline = await make_pipeline()

    assert await pipeline.check_ghosting_timeouts() == 1

    rows = await all_rows(session_factory, Vacancy)
    assert [row.status for row in rows] == [VacancyStatus.GHOSTING]


async def test_a_fresh_application_is_left_alone(make_pipeline, session_factory):
    """Свежий отклик не трогают: ответа ещё ждут."""
    await put(
        session_factory,
        vacancy_row(title="ждём", status=VacancyStatus.APPLIED, created_at=_recently()),
    )
    pipeline = await make_pipeline()

    assert await pipeline.check_ghosting_timeouts() == 0

    rows = await all_rows(session_factory, Vacancy)
    assert [row.status for row in rows] == [VacancyStatus.APPLIED]


@pytest.mark.parametrize(
    "status",
    [
        pytest.param(VacancyStatus.NEW, id="ещё не откликались"),
        pytest.param(VacancyStatus.DECLINE, id="уже отказали"),
        pytest.param(VacancyStatus.OFFER, id="уже предложили"),
    ],
)
async def test_only_a_waiting_vacancy_can_fall_silent(
    make_pipeline, session_factory, status
):
    """В «молчание» уходит только та вакансия, где ответа и правда ждут.

    По вакансии без отклика молчать некому, а из состояния, где разговор
    уже кончился, «молчание» было бы шагом назад.
    """
    await put(
        session_factory,
        vacancy_row(title="не в счёт", status=status, created_at=_long_ago()),
    )
    pipeline = await make_pipeline()

    assert await pipeline.check_ghosting_timeouts() == 0

    rows = await all_rows(session_factory, Vacancy)
    assert [row.status for row in rows] == [status]


async def test_nothing_waiting_means_nothing_to_do(make_pipeline, session_factory):
    """На пустой базе проверка ничего не делает и не падает."""
    pipeline = await make_pipeline()

    assert await pipeline.check_ghosting_timeouts() == 0


async def test_the_window_hears_about_the_silenced_vacancies(
    make_pipeline, session_factory
):
    """Окно узнаёт о переехавших вакансиях: список обновится сразу."""
    await put(
        session_factory,
        vacancy_row(title="молчат", status=VacancyStatus.APPLIED, created_at=_long_ago()),
    )
    pipeline = await make_pipeline()
    heard: list[int] = []
    pipeline.on_vacancies_changed = lambda: heard.append(1)

    await pipeline.check_ghosting_timeouts()

    assert heard == [1]


async def test_the_window_is_not_told_when_nothing_moved(
    make_pipeline, session_factory
):
    """Когда двигать нечего, окно не дёргают.

    Проверка идёт каждый оборот цикла — то есть раз в полчаса и после
    каждой побудки; перерисовывать список впустую незачем.
    """
    pipeline = await make_pipeline()
    heard: list[int] = []
    pipeline.on_vacancies_changed = lambda: heard.append(1)

    await pipeline.check_ghosting_timeouts()

    assert heard == []


async def test_a_broken_window_hook_does_not_undo_the_move(
    make_pipeline, session_factory
):
    """Сломанное оповещение окна перевод вакансий не отменяет."""
    await put(
        session_factory,
        vacancy_row(title="молчат", status=VacancyStatus.APPLIED, created_at=_long_ago()),
    )
    pipeline = await make_pipeline()

    def broken():
        raise RuntimeError("окно")

    pipeline.on_vacancies_changed = broken

    assert await pipeline.check_ghosting_timeouts() == 1

    rows = await all_rows(session_factory, Vacancy)
    assert [row.status for row in rows] == [VacancyStatus.GHOSTING]


async def test_a_failed_check_does_not_break_the_turn(
    make_pipeline, session_factory, monkeypatch
):
    """Сбой проверки оборот цикла не роняет.

    Она удобство, а не работа, ради которой бот запущен: из-за неё не
    собрать вакансии было бы обменом важного на второстепенное. Вакансия
    здесь такая, которую проверка перевела бы, — иначе ноль в ответе
    ничего не доказывал бы.
    """
    await put(
        session_factory,
        vacancy_row(title="молчат", status=VacancyStatus.APPLIED, created_at=_long_ago()),
    )
    pipeline = await make_pipeline()

    async def broken(session, timeout_days):
        raise OSError("база недоступна")

    monkeypatch.setattr(
        "backend.repository.vacancies_life.mark_ghosted_vacancies", broken
    )

    assert await pipeline.check_ghosting_timeouts() == 0

    rows = await all_rows(session_factory, Vacancy)
    assert [row.status for row in rows] == [VacancyStatus.APPLIED]
