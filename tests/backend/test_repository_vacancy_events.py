"""Следствия записи события в ленту обработки вакансии.

Лента и история статусов — разные таблицы и разные предметы: сюда попадает
всё, что с вакансией делали, кроме смены статуса, — разбор, повторный разбор,
привязка. Тесты привязки смотрят на события со своей стороны; здесь предмет —
сама запись.
"""

from backend.repository import add_vacancy_event, get_vacancy_detail
from tests.dbio import put
from tests.factories import vacancy_row


async def test_an_event_lands_in_the_timeline_with_its_payload(
    session, session_factory
):
    """Событие обработки попадает в ленту вместе с полезной нагрузкой."""
    vacancy = vacancy_row()
    await put(session_factory, vacancy)

    await add_vacancy_event(session, vacancy.id, "reparsed", {"причина": "вручную"})

    card = await get_vacancy_detail(session, vacancy.id)
    assert [(e.kind, e.payload) for e in card.events] == [
        ("reparsed", {"причина": "вручную"})
    ]


async def test_an_empty_payload_is_stored_as_absence(session, session_factory):
    """Пустая нагрузка записывается как отсутствие, а не как пустой словарь.

    Экран отличает событие без подробностей от события с подробностями, и
    пустой словарь попал бы во вторую ветку.
    """
    vacancy = vacancy_row()
    await put(session_factory, vacancy)

    await add_vacancy_event(session, vacancy.id, "ingested", {})

    card = await get_vacancy_detail(session, vacancy.id)
    assert card.events[0].payload is None
