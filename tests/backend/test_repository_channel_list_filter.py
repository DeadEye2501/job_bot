"""Следствия отбора по строке в списке каналов.

Отбор идёт в питоне, а не в запросе: список каналов невелик, и отбирать его
после выборки дешевле, чем городить условие на каждое искомое поле.
"""

from tests.dbio import put
from tests.factories import channel_row


async def test_search_looks_at_the_title_and_the_username(channel_titles, session_factory):
    """Поиск смотрит и в заголовок, и в ник, не различая регистра кириллицы."""
    await put(
        session_factory,
        channel_row(username="pyjobs", title="Питон-вакансии"),
        channel_row(username="jsjobs", title="Фронтенд"),
    )

    assert await channel_titles(search="Питон") == ["Питон-вакансии"]
    assert await channel_titles(search="ПИТОН") == ["Питон-вакансии"]
    assert await channel_titles(search="jsjobs") == ["Фронтенд"]


async def test_a_blank_search_selects_everything(channel_titles, session_factory):
    """Поиск из одних пробелов никого не отсекает."""
    await put(
        session_factory,
        channel_row(username="a", title="Акация"),
        channel_row(username="b", title="Берёза"),
    )

    assert await channel_titles(search="   ") == ["Акация", "Берёза"]


async def test_search_finds_a_channel_by_the_handle_as_it_is_shown(
    channel_titles, session_factory
):
    """Ник, набранный с собачкой, находит канал.

    Список рисует ник как `@ник`, и образец человек списывает оттуда же.
    """
    await put(
        session_factory,
        channel_row(username="pyjobs", title="Питон-вакансии"),
        channel_row(username="jsjobs", title="Фронтенд"),
    )

    assert await channel_titles(search="@pyjobs") == ["Питон-вакансии"]
