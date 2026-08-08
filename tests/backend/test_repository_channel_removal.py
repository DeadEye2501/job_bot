"""Следствия удаления канала-источника.

Удаление щадящее: вакансии остаются, теряя лишь ссылку на источник — их сырой
текст и разобранные поля по-прежнему ищутся.
"""

from sqlalchemy import select

from backend.models import TelegramChannel, TrashEvent, Vacancy
from backend.repository import delete_channel
from tests.dbio import put
from tests.factories import channel_row, vacancy_row


async def test_deleting_a_missing_channel_reports_nothing(session):
    """Удалить несуществующий канал нельзя, и это видно по ответу.

    Ответ здесь не «ложь», а «ничего»: у удачного удаления ответ — число
    отвязанных вакансий, и ноль отвязанных был бы неотличим от отказа.
    """
    assert await delete_channel(session, 10_000) is None


async def test_deleting_a_channel_detaches_its_vacancies_and_trash(
    session, session_factory
):
    """Удаление канала отвязывает его вакансии и отметки о мусоре, но не чужие.

    Про вакансии проверка честная: у их ссылки на канал нет правила «обнулить
    при удалении», и без явной записи вставка упала бы на ссылочной
    целостности. Про отметки о мусоре — нет: у них такое правило есть, база
    обнулила бы ссылку и сама, а явная запись в коде стоит второй линией на
    случай выключенных внешних ключей. Отличить одно от другого отсюда
    нечем, и проверка закрепляет итог, а не его причину.
    """
    doomed = channel_row(username="doomed")
    spared = channel_row(username="spared")
    await put(session_factory, doomed, spared)
    await put(
        session_factory,
        vacancy_row(title="была его", source_channel_id=doomed.id),
        vacancy_row(title="чужая", source_channel_id=spared.id),
        TrashEvent(source_channel_id=doomed.id, source_msg_id=1, reason="мусор"),
        TrashEvent(source_channel_id=spared.id, source_msg_id=2, reason="мусор"),
    )

    assert await delete_channel(session, doomed.id) == 1

    vacancies = (await session.scalars(select(Vacancy))).all()
    assert {v.title: v.source_channel_id for v in vacancies} == {
        "была его": None,
        "чужая": spared.id,
    }
    trash = (await session.scalars(select(TrashEvent))).all()
    assert sorted(t.source_channel_id or 0 for t in trash) == [0, spared.id]
    assert [ch.username for ch in (await session.scalars(select(TelegramChannel))).all()] == [
        "spared"
    ]
