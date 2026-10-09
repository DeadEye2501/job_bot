"""Отметки о мусоре: по одной на объявление, сколько бы раз его ни разбирали.

Объявление, признанное мусором, строки вакансии после себя не оставляет —
значит и отпечатка, которым отсеиваются повторы, у него нет. Пост канала
после сброса отметки прочитанного и объявление агрегатора на следующем обходе
проходят весь путь заново, и без сверки по номеру числа «сколько мусора
прислал источник» росли бы от каждого повтора.
"""

from backend.models import TelegramChannel, TrashEvent
from backend.repository.vacancies_life import record_trash_event
from tests.dbio import all_rows, only_row, put
from tests.factories import channel_row, vacancy_row
from tests.factories_aggregators import aggregator_row


async def _noted(session, channel_id: int, msg_id: int, reason: str) -> None:
    await record_trash_event(
        session, vacancy_row(source_channel_id=channel_id, source_msg_id=msg_id), reason
    )
    await session.commit()


async def test_the_same_post_is_not_noted_twice(session, session_factory):
    """Второй разбор того же поста второй отметки не заводит.

    Считаются строки, а не читается первая: утверждение о первой истинно и
    при двух, а вторая — это ровно та прибавка к «сколько мусора прислал
    канал», ради которой сверка и стоит.
    """
    await put(session_factory, channel_row(username="noisy"))
    channel = await only_row(session_factory, TelegramChannel)

    await _noted(session, channel.id, 7, "реклама")
    await _noted(session, channel.id, 7, "реклама")

    noted = await all_rows(session_factory, TrashEvent)
    assert [row.source_msg_id for row in noted] == [7]


async def test_the_same_post_number_in_another_channel_is_noted(
    session, session_factory
):
    """Тот же номер поста в другом канале свою отметку получает.

    Ключ отметки — пара «канал и номер»: номера Telegram раздаёт свои в
    каждом канале, и сверка по одному номеру глушила бы мусор всех каналов,
    кроме приславшего этот номер первым.
    """
    noisy = channel_row(username="noisy")
    other = channel_row(username="other")
    await put(session_factory, noisy, other)

    await _noted(session, noisy.id, 7, "реклама")
    await _noted(session, other.id, 7, "реклама")

    noted = await all_rows(session_factory, TrashEvent)
    assert {row.source_channel_id for row in noted} == {noisy.id, other.id}


async def test_another_post_of_the_same_channel_is_noted(session, session_factory):
    """Другой пост того же канала отметку получает: мусор в нём свой."""
    await put(session_factory, channel_row(username="noisy"))
    channel = await only_row(session_factory, TelegramChannel)

    await _noted(session, channel.id, 7, "реклама")
    await _noted(session, channel.id, 8, "реклама")

    assert len(await all_rows(session_factory, TrashEvent)) == 2


async def test_the_same_number_on_one_aggregator_is_not_noted_twice(
    session, session_factory
):
    """Объявление с агрегатора, снова удалённое как мусор, второй отметки не даёт."""
    hh = aggregator_row()
    await put(session_factory, hh)
    seen = vacancy_row(source_aggregator_id=hh.id, source_key="vacancy/1")

    await record_trash_event(session, seen, "не вакансия")
    await session.commit()
    await record_trash_event(session, seen, "не вакансия")
    await session.commit()

    marks = await all_rows(session_factory, TrashEvent)
    assert [(m.source_aggregator_id, m.source_key) for m in marks] == [(hh.id, "vacancy/1")]


async def test_the_same_number_on_another_aggregator_is_noted(session, session_factory):
    """Номер на агрегаторе свой у каждого сайта: совпадение номеров — не повтор."""
    hh, gm = aggregator_row(), aggregator_row(name="GetMatch", host="getmatch.ru")
    await put(session_factory, hh, gm)

    await record_trash_event(
        session, vacancy_row(source_aggregator_id=hh.id, source_key="v/1"), None
    )
    await session.commit()
    await record_trash_event(
        session, vacancy_row(source_aggregator_id=gm.id, source_key="v/1"), None
    )
    await session.commit()

    assert len(await all_rows(session_factory, TrashEvent)) == 2
