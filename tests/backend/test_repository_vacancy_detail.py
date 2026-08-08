"""Следствия чтения карточки вакансии.

Карточка собирается тремя запросами: сама вакансия со связями, история
статусов и события обработки. Связей от вакансии к двум последним в модели
нет нарочно, поэтому и запроса три, а не один.
"""

from backend.models import VacancyStatus
from backend.repository.vacancies_card import get_vacancy_detail
from tests.dbio import put
from tests.factories import (
    at,
    channel_row,
    company_row,
    hr_row,
    status_history_row,
    vacancy_event_row,
    vacancy_row,
)


async def test_a_missing_vacancy_has_no_card(session, session_factory):
    """У несуществующей вакансии карточки нет, и это не ошибка."""
    await put(session_factory, vacancy_row())

    assert await get_vacancy_detail(session, 10_000) is None


async def test_the_card_carries_the_linked_hr_company_and_channel(
    session, session_factory
):
    """Карточка отдаёт вакансию вместе со связанными HR, компанией и каналом."""
    hr = hr_row(name="Мария")
    company = company_row(name="Контур")
    channel = channel_row(username="pyjobs")
    await put(session_factory, hr, company, channel)
    vacancy = vacancy_row(hr_id=hr.id, company_id=company.id, source_channel_id=channel.id)
    await put(session_factory, vacancy)

    card = await get_vacancy_detail(session, vacancy.id)

    assert card.vacancy.id == vacancy.id
    assert card.vacancy.hr.name == "Мария"
    assert card.vacancy.company.name == "Контур"
    assert card.vacancy.channel.username == "pyjobs"


async def test_a_card_without_history_or_events_carries_empty_lists(
    session, session_factory
):
    """У вакансии без истории и событий карточка отдаёт пустые списки, а не None."""
    vacancy = vacancy_row()
    await put(session_factory, vacancy)

    card = await get_vacancy_detail(session, vacancy.id)

    assert card.history == []
    assert card.events == []


async def test_history_comes_newest_first(session, session_factory):
    """История статусов отдаётся от поздней записи к ранней."""
    vacancy = vacancy_row()
    await put(session_factory, vacancy)
    await put(
        session_factory,
        status_history_row(vacancy.id, changed_at=at(10), status=VacancyStatus.APPLIED),
        status_history_row(vacancy.id, changed_at=at(30), status=VacancyStatus.OFFER),
        status_history_row(vacancy.id, changed_at=at(20), status=VacancyStatus.TEST),
    )

    card = await get_vacancy_detail(session, vacancy.id)

    assert [h.status for h in card.history] == [
        VacancyStatus.OFFER,
        VacancyStatus.TEST,
        VacancyStatus.APPLIED,
    ]


async def test_history_written_at_the_same_moment_comes_newest_first_by_id(
    session, session_factory
):
    """Две записи истории с одним временем упорядочены по идентификатору, поздняя первой.

    Времена в истории проставляет код, и две смены подряд легко получают одно
    и то же значение. Без разрешителя порядок задавала бы база по своему
    усмотрению, и карточка показывала бы смены в случайной последовательности.
    """
    vacancy = vacancy_row()
    await put(session_factory, vacancy)
    await put(
        session_factory,
        status_history_row(vacancy.id, changed_at=at(10), status=VacancyStatus.APPLIED),
        status_history_row(vacancy.id, changed_at=at(10), status=VacancyStatus.OFFER),
    )

    card = await get_vacancy_detail(session, vacancy.id)

    assert [h.status for h in card.history] == [
        VacancyStatus.OFFER,
        VacancyStatus.APPLIED,
    ]


async def test_events_come_newest_first(session, session_factory):
    """События обработки отдаются от позднего к раннему."""
    vacancy = vacancy_row()
    await put(session_factory, vacancy)
    await put(
        session_factory,
        vacancy_event_row(vacancy.id, kind="ранний", created_at=at(10)),
        vacancy_event_row(vacancy.id, kind="поздний", created_at=at(30)),
        vacancy_event_row(vacancy.id, kind="средний", created_at=at(20)),
    )

    card = await get_vacancy_detail(session, vacancy.id)

    assert [e.kind for e in card.events] == ["поздний", "средний", "ранний"]


async def test_events_of_a_neighbouring_vacancy_stay_out_of_the_card(
    session, session_factory
):
    """Чужие события и чужая история в карточку не попадают."""
    mine = vacancy_row(title="моя")
    other = vacancy_row(title="соседняя")
    await put(session_factory, mine, other)
    await put(
        session_factory,
        vacancy_event_row(mine.id, kind="мой"),
        vacancy_event_row(other.id, kind="чужой"),
        status_history_row(other.id),
    )

    card = await get_vacancy_detail(session, mine.id)

    assert [e.kind for e in card.events] == ["мой"]
    assert card.history == []
