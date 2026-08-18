"""Следствия автоматического перевода молчащих вакансий в «пропала».

Проверка идёт по вакансиям в двух статусах — «отклик отправлен» и «в
работе», — и переводит те, где HR не подаёт голоса дольше заданного срока.
Отсчёт ведётся от самого позднего из трёх событий: создания вакансии,
последнего входящего сообщения и последней смены в нынешний статус.

Времена здесь считаются от «сейчас», а не от опорного момента: проверяемый
код сам берёт текущее время и отмеряет от него.
"""

from backend.models import VacancyStatus
from backend.repository.vacancies_card import get_vacancy_detail
from backend.repository.vacancies_ghosting import mark_ghosted_vacancies
from tests.dbio import put
from tests.factories import (
    days_ago,
    hr_row,
    message_row,
    status_history_row,
    vacancy_row,
)

TIMEOUT = 14


async def test_an_empty_database_yields_nothing_to_ghost(session):
    """На пустой базе переводить нечего, и это не ошибка."""
    assert await mark_ghosted_vacancies(session, timeout_days=TIMEOUT) == []


async def test_a_long_silent_application_becomes_ghosted(session, session_factory):
    """Давно отправленный отклик без ответа переводится в «пропала»."""
    vacancy = vacancy_row(status=VacancyStatus.APPLIED, created_at=days_ago(30))
    await put(session_factory, vacancy)

    assert await mark_ghosted_vacancies(session, timeout_days=TIMEOUT) == [vacancy.id]

    card = await get_vacancy_detail(session, vacancy.id)
    assert card.vacancy.status is VacancyStatus.GHOSTING


async def test_the_ghosting_is_recorded_with_a_reason(session, session_factory):
    """Перевод оставляет в истории запись с причиной и прежним статусом."""
    vacancy = vacancy_row(status=VacancyStatus.IN_PROGRESS, created_at=days_ago(30))
    await put(session_factory, vacancy)

    await mark_ghosted_vacancies(session, timeout_days=TIMEOUT)

    card = await get_vacancy_detail(session, vacancy.id)
    assert len(card.history) == 1
    written = card.history[0]
    assert written.previous_status is VacancyStatus.IN_PROGRESS
    assert written.status is VacancyStatus.GHOSTING
    assert written.applied is True
    assert written.message_id is None
    assert f"более {TIMEOUT} дней" in written.explanation


async def test_a_status_outside_the_two_is_never_ghosted(session, session_factory):
    """Вакансия в любом другом статусе не переводится, сколько бы ни молчала.

    Перечислены все девять статусов, кроме двух подходящих: неполный список
    оставлял бы лазейку — расширение множества подходящих на статус, которого
    в наборе нет, прошло бы незамеченным.
    """
    spared = [
        s
        for s in VacancyStatus
        if s not in (VacancyStatus.APPLIED, VacancyStatus.IN_PROGRESS)
    ]
    assert len(spared) == 9
    await put(
        session_factory,
        *[vacancy_row(status=s, created_at=days_ago(300)) for s in spared],
    )

    assert await mark_ghosted_vacancies(session, timeout_days=TIMEOUT) == []


async def test_a_recent_application_is_left_alone(session, session_factory):
    """Свежий отклик не трогают: срок молчания ещё не вышел."""
    fresh = vacancy_row(status=VacancyStatus.APPLIED, created_at=days_ago(1))
    stale = vacancy_row(status=VacancyStatus.APPLIED, created_at=days_ago(30))
    await put(session_factory, fresh, stale)

    assert await mark_ghosted_vacancies(session, timeout_days=TIMEOUT) == [stale.id]


async def test_an_incoming_message_restarts_the_countdown(session, session_factory):
    """Недавнее входящее сообщение отодвигает срок, даже если отклик давний."""
    hr = hr_row()
    await put(session_factory, hr)
    answered = vacancy_row(status=VacancyStatus.APPLIED, created_at=days_ago(30))
    silent = vacancy_row(status=VacancyStatus.APPLIED, created_at=days_ago(30))
    await put(session_factory, answered, silent)
    await put(
        session_factory,
        message_row(
            text="скоро вернёмся",
            hr_id=hr.id,
            vacancy_id=answered.id,
            is_incoming=True,
            sent_at=days_ago(1),
        ),
    )

    assert await mark_ghosted_vacancies(session, timeout_days=TIMEOUT) == [silent.id]


async def test_our_own_message_does_not_restart_the_countdown(
    session, session_factory
):
    """Наше собственное недавнее сообщение срок не отодвигает.

    Молчит здесь HR, а не мы: напоминание, отправленное вчера, ответом не
    является и ждать из-за него ещё две недели незачем.
    """
    hr = hr_row()
    await put(session_factory, hr)
    vacancy = vacancy_row(status=VacancyStatus.APPLIED, created_at=days_ago(30))
    await put(session_factory, vacancy)
    await put(
        session_factory,
        message_row(
            text="напоминаю о себе",
            hr_id=hr.id,
            vacancy_id=vacancy.id,
            is_incoming=False,
            sent_at=days_ago(1),
        ),
    )

    assert await mark_ghosted_vacancies(session, timeout_days=TIMEOUT) == [vacancy.id]


async def test_a_recent_move_into_the_current_status_restarts_the_countdown(
    session, session_factory
):
    """Недавний перевод в нынешний статус отодвигает срок."""
    vacancy = vacancy_row(status=VacancyStatus.APPLIED, created_at=days_ago(30))
    await put(session_factory, vacancy)
    await put(
        session_factory,
        status_history_row(
            vacancy.id, status=VacancyStatus.APPLIED, changed_at=days_ago(1)
        ),
    )

    assert await mark_ghosted_vacancies(session, timeout_days=TIMEOUT) == []


async def test_a_recent_move_into_some_other_status_does_not_count(
    session, session_factory
):
    """Недавняя запись о другом статусе срок не отодвигает.

    В счёт идёт только переход в тот статус, в котором вакансия стоит
    сейчас. Запись о каком-то былом состоянии свежести нынешнему не
    добавляет.
    """
    vacancy = vacancy_row(status=VacancyStatus.APPLIED, created_at=days_ago(30))
    await put(session_factory, vacancy)
    await put(
        session_factory,
        status_history_row(
            vacancy.id, status=VacancyStatus.NEW, changed_at=days_ago(1)
        ),
    )

    assert await mark_ghosted_vacancies(session, timeout_days=TIMEOUT) == [vacancy.id]


async def test_a_longer_timeout_spares_what_a_shorter_one_would_take(
    session, session_factory
):
    """Срок и вправду читается из довода, а не зашит в код."""
    vacancy = vacancy_row(status=VacancyStatus.APPLIED, created_at=days_ago(30))
    await put(session_factory, vacancy)

    assert await mark_ghosted_vacancies(session, timeout_days=60) == []
    assert await mark_ghosted_vacancies(session, timeout_days=7) == [vacancy.id]
