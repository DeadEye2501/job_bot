"""Следствия привязки вакансии к HR и компании и её удаления.

Привязка не просто меняет поле: каждая смена оставляет событие в ленте
обработки, и в событии записаны обе стороны — что было и что стало. Удаление
же выборочное: история и события вакансии стираются вместе с ней, а переписка
остаётся, потеряв только ссылку.
"""

import pytest
from sqlalchemy import select

from backend.models import (
    Application,
    Message,
    Screening,
    Vacancy,
    VacancyContact,
    VacancyEvent,
    VacancyStatusHistory,
)
from backend.repository.vacancies_card import get_vacancy_detail, set_vacancy_company, set_vacancy_hr
from backend.repository.vacancies_life import delete_vacancy
from tests.dbio import put
from tests.factories import (
    company_row,
    hr_row,
    message_row,
    status_history_row,
    vacancy_event_row,
    vacancy_row,
)
from tests.factories_aggregators import application_row, screening_row, vacancy_contact_row


async def test_linking_an_hr_to_a_missing_vacancy_reports_failure(
    session, session_factory
):
    """Привязать HR к несуществующей вакансии нельзя, и вызов об этом сообщает."""
    hr = hr_row()
    await put(session_factory, hr)

    assert await set_vacancy_hr(session, 10_000, hr.id) is False


async def test_linking_an_unknown_hr_is_refused_loudly(session, session_factory):
    """Привязка несуществующего HR не проходит молча, а поднимает ошибку.

    Ответ `False` здесь означал бы «вакансии нет», и вызывающий не отличил бы
    одну беду от другой. Молчаливое согласие оставило бы в базе ссылку в
    никуда.
    """
    vacancy = vacancy_row()
    await put(session_factory, vacancy)

    with pytest.raises(ValueError, match="does not exist"):
        await set_vacancy_hr(session, vacancy.id, 10_000)


async def test_linking_an_hr_records_both_sides_in_the_timeline(
    session, session_factory
):
    """Привязка HR меняет поле и оставляет в ленте событие с обеими сторонами."""
    hr = hr_row(name="Мария")
    await put(session_factory, hr)
    vacancy = vacancy_row(hr_id=None)
    await put(session_factory, vacancy)

    assert await set_vacancy_hr(session, vacancy.id, hr.id) is True

    card = await get_vacancy_detail(session, vacancy.id)
    assert card.vacancy.hr_id == hr.id
    assert [e.kind for e in card.events] == ["linked_hr"]
    assert card.events[0].payload == {
        "previous_id": None,
        "previous_name": None,
        "new_id": hr.id,
        "new_name": "Мария",
    }


async def test_an_hr_without_a_name_is_recorded_by_username(session, session_factory):
    """У HR без имени в событие попадает ник — иначе лента показала бы пустоту."""
    hr = hr_row(name=None, telegram_username="maria_hr")
    await put(session_factory, hr)
    vacancy = vacancy_row(hr_id=None)
    await put(session_factory, vacancy)

    await set_vacancy_hr(session, vacancy.id, hr.id)

    card = await get_vacancy_detail(session, vacancy.id)
    assert card.events[0].payload["new_name"] == "maria_hr"


async def test_relinking_carries_the_previous_hr_into_the_event(
    session, session_factory
):
    """Перепривязка записывает в событие и прежнего HR, и нового."""
    was = hr_row(name="Мария")
    now = hr_row(name="Ольга")
    await put(session_factory, was, now)
    vacancy = vacancy_row(hr_id=was.id)
    await put(session_factory, vacancy)

    await set_vacancy_hr(session, vacancy.id, now.id)

    card = await get_vacancy_detail(session, vacancy.id)
    assert card.events[0].payload["previous_name"] == "Мария"
    assert card.events[0].payload["new_name"] == "Ольга"


async def test_unlinking_leaves_an_event_with_no_new_side(session, session_factory):
    """Отвязка тоже событие: прежняя сторона названа, новой нет."""
    hr = hr_row(name="Мария")
    await put(session_factory, hr)
    vacancy = vacancy_row(hr_id=hr.id)
    await put(session_factory, vacancy)

    assert await set_vacancy_hr(session, vacancy.id, None) is True

    card = await get_vacancy_detail(session, vacancy.id)
    assert card.vacancy.hr_id is None
    assert card.events[0].payload["previous_name"] == "Мария"
    assert card.events[0].payload["new_id"] is None


async def test_relinking_to_the_same_hr_adds_no_second_event(
    session, session_factory
):
    """Повторная привязка того же HR ленту не засоряет.

    Экран шлёт привязку и тогда, когда пользователь выбрал того же HR, что
    уже стоял. Без проверки на равенство лента набивалась бы событиями «с
    Марии на Марию».
    """
    hr = hr_row(name="Мария")
    await put(session_factory, hr)
    vacancy = vacancy_row(hr_id=None)
    await put(session_factory, vacancy)

    assert await set_vacancy_hr(session, vacancy.id, hr.id) is True
    assert await set_vacancy_hr(session, vacancy.id, hr.id) is True

    card = await get_vacancy_detail(session, vacancy.id)
    assert len(card.events) == 1


async def test_linking_a_company_records_both_sides_in_the_timeline(
    session, session_factory
):
    """Привязка компании меняет поле и оставляет своё событие с обеими сторонами."""
    was = company_row(name="Контур")
    now = company_row(name="Ромашка")
    await put(session_factory, was, now)
    vacancy = vacancy_row(company_id=was.id)
    await put(session_factory, vacancy)

    assert await set_vacancy_company(session, vacancy.id, now.id) is True

    card = await get_vacancy_detail(session, vacancy.id)
    assert card.vacancy.company_id == now.id
    assert [e.kind for e in card.events] == ["linked_company"]
    assert card.events[0].payload == {
        "previous_id": was.id,
        "previous_name": "Контур",
        "new_id": now.id,
        "new_name": "Ромашка",
    }


async def test_linking_an_unknown_company_is_refused_loudly(session, session_factory):
    """Привязка несуществующей компании поднимает ошибку, а не отвечает отказом."""
    vacancy = vacancy_row()
    await put(session_factory, vacancy)

    with pytest.raises(ValueError, match="does not exist"):
        await set_vacancy_company(session, vacancy.id, 10_000)


async def test_relinking_to_the_same_company_adds_no_second_event(
    session, session_factory
):
    """Повторная привязка той же компании ленту не засоряет."""
    company = company_row(name="Контур")
    await put(session_factory, company)
    vacancy = vacancy_row(company_id=None)
    await put(session_factory, vacancy)

    assert await set_vacancy_company(session, vacancy.id, company.id) is True
    assert await set_vacancy_company(session, vacancy.id, company.id) is True

    card = await get_vacancy_detail(session, vacancy.id)
    assert len(card.events) == 1


async def test_deleting_a_missing_vacancy_reports_failure(session, session_factory):
    """Удалить несуществующую вакансию нельзя, и вызов об этом сообщает."""
    await put(session_factory, vacancy_row())

    assert await delete_vacancy(session, 10_000) is False


async def test_deleting_a_vacancy_purges_its_history_and_events(
    session, session_factory
):
    """Удаление вакансии уносит её историю и события, но не соседские."""
    doomed = vacancy_row(title="под нож")
    spared = vacancy_row(title="рядом стояла")
    await put(session_factory, doomed, spared)
    await put(
        session_factory,
        status_history_row(doomed.id),
        vacancy_event_row(doomed.id),
        status_history_row(spared.id),
        vacancy_event_row(spared.id),
    )

    assert await delete_vacancy(session, doomed.id) is True

    assert (await session.scalars(select(Vacancy.id))).all() == [spared.id]
    assert (await session.scalars(select(VacancyStatusHistory.vacancy_id))).all() == [
        spared.id
    ]
    assert (await session.scalars(select(VacancyEvent.vacancy_id))).all() == [spared.id]


async def test_deleting_a_vacancy_keeps_the_conversation(session, session_factory):
    """Переписка переживает удаление вакансии, потеряв только ссылку на неё.

    Разговор с HR может понадобиться и после того, как вакансия стёрта, —
    поэтому сообщения не удаляются вместе с ней, а лишь отвязываются.
    """
    hr = hr_row()
    await put(session_factory, hr)
    vacancy = vacancy_row()
    await put(session_factory, vacancy)
    await put(
        session_factory,
        message_row(text="про эту вакансию", hr_id=hr.id, vacancy_id=vacancy.id),
        message_row(text="просто так", hr_id=hr.id, vacancy_id=None),
    )

    await delete_vacancy(session, vacancy.id)

    rows = (await session.scalars(select(Message))).all()
    assert sorted(m.text for m in rows) == sorted(["про эту вакансию", "просто так"])
    assert all(m.vacancy_id is None for m in rows)


async def test_deleting_a_vacancy_takes_its_contacts_and_applications(
    session, session_factory
):
    """Удалённая вакансия уносит контакты, отклики и их скрининг. Чужие остаются."""
    gone, kept = vacancy_row(title="уйдёт"), vacancy_row(title="останется")
    await put(session_factory, gone, kept)
    applied, other = application_row(gone.id), application_row(kept.id)
    await put(
        session_factory, applied, other,
        vacancy_contact_row(gone.id, "a@x.ru"), vacancy_contact_row(kept.id, "b@x.ru"),
    )
    await put(session_factory, screening_row(applied.id, 0), screening_row(other.id, 0))

    assert await delete_vacancy(session, gone.id) is True

    assert (await session.scalars(select(VacancyContact.vacancy_id))).all() == [kept.id]
    assert (await session.scalars(select(Application.vacancy_id))).all() == [kept.id]
    assert (await session.scalars(select(Screening.application_id))).all() == [other.id]
