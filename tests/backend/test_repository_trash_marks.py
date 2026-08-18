"""Отметки о мусоре: по одной на пост, сколько бы раз его ни разбирали.

Пост, признанный мусором, строки вакансии после себя не оставляет — значит и
отпечатка, которым отсеиваются повторы, у него нет. После сброса отметки
прочитанного он проходит весь путь заново, и без сверки по номеру числа
«сколько мусора прислал канал» росли бы от каждого сброса.
"""

from backend.models import TelegramChannel, TrashEvent
from backend.repository.vacancies_life import record_trash_event
from tests.dbio import all_rows, only_row, put
from tests.factories import channel_row


async def _noted(session, channel_id: int, msg_id: int, reason: str) -> None:
    await record_trash_event(
        session,
        source_channel_id=channel_id,
        source_msg_id=msg_id,
        reason=reason,
    )
    await session.commit()


async def test_the_same_post_is_not_noted_twice(session, session_factory):
    """Второй разбор того же поста второй отметки не заводит."""
    await put(session_factory, channel_row(username="noisy"))
    channel = await only_row(session_factory, TelegramChannel)

    await _noted(session, channel.id, 7, "реклама")
    await _noted(session, channel.id, 7, "реклама")

    assert (await only_row(session_factory, TrashEvent)).source_msg_id == 7


async def test_another_post_of_the_same_channel_is_noted(session, session_factory):
    """Другой пост того же канала отметку получает: мусор в нём свой."""
    await put(session_factory, channel_row(username="noisy"))
    channel = await only_row(session_factory, TelegramChannel)

    await _noted(session, channel.id, 7, "реклама")
    await _noted(session, channel.id, 8, "реклама")

    assert len(await all_rows(session_factory, TrashEvent)) == 2
