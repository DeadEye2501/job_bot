"""Следствия отбора по строке в списке каналов.

Отбор идёт в питоне, а не в запросе: список каналов невелик, и отбирать его
после выборки дешевле, чем городить условие на каждое искомое поле.
"""

from backend.repository.channels import list_telegram_channels
from tests.dbio import put
from tests.factories import channel_row


async def titles_of(session, **kwargs) -> list[str]:
    """Заголовки каналов в порядке выдачи."""
    return [
        row.channel.title for row in await list_telegram_channels(session, **kwargs)
    ]


async def test_search_looks_at_the_title_and_the_username(session, session_factory):
    """Поиск смотрит и в заголовок, и в ник, не различая регистра кириллицы."""
    await put(
        session_factory,
        channel_row(username="pyjobs", title="Питон-вакансии"),
        channel_row(username="jsjobs", title="Фронтенд"),
    )

    assert await titles_of(session, search="Питон") == ["Питон-вакансии"]
    assert await titles_of(session, search="ПИТОН") == ["Питон-вакансии"]
    assert await titles_of(session, search="jsjobs") == ["Фронтенд"]


async def test_a_blank_search_selects_everything(session, session_factory):
    """Поиск из одних пробелов никого не отсекает."""
    await put(
        session_factory,
        channel_row(username="a", title="Акация"),
        channel_row(username="b", title="Берёза"),
    )

    assert await titles_of(session, search="   ") == ["Акация", "Берёза"]
