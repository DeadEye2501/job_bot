"""Следствия порядка в списке каналов-источников.

Вперёд идут те, откуда пришло больше вакансий, при равенстве — по заголовку, а
у канала без заголовка вместо него подставляется ник: экран показывает такой
канал именно ником. Включённость в порядке не участвует нарочно — канал,
выключенный чёрным списком, иначе проваливался бы в самый низ.
"""

from backend.repository import list_telegram_channels
from tests.dbio import put
from tests.factories import channel_row, vacancy_row


async def titles_of(session, **kwargs) -> list[str]:
    """Заголовки каналов в порядке выдачи."""
    return [
        row.channel.title for row in await list_telegram_channels(session, **kwargs)
    ]


async def test_the_list_leads_with_the_most_prolific_channel(
    session, session_factory
):
    """Вперёд идёт канал, откуда пришло больше вакансий.

    Порядок вставки обратен ожидаемому: совпади они — и выдача без
    сортировки прошла бы проверку.
    """
    empty = channel_row(username="c", title="Пусто")
    few = channel_row(username="b", title="Немного")
    many = channel_row(username="a", title="Много")
    await put(session_factory, empty, few, many)
    await put(
        session_factory,
        vacancy_row(source_channel_id=many.id),
        vacancy_row(source_channel_id=many.id),
        vacancy_row(source_channel_id=few.id),
    )

    assert await titles_of(session) == ["Много", "Немного", "Пусто"]


async def test_an_equal_count_is_broken_by_the_title(session, session_factory):
    """При равном числе вакансий порядок решает заголовок."""
    await put(
        session_factory,
        channel_row(username="ya", title="Ясень"),
        channel_row(username="ak", title="Акация"),
        channel_row(username="be", title="Берёза"),
    )

    assert await titles_of(session) == ["Акация", "Берёза", "Ясень"]


async def test_a_channel_without_a_title_is_ordered_by_its_username(
    session, session_factory
):
    """Канал без заголовка встаёт по нику, а не в начало списка.

    Экран показывает такой канал ником, и упорядочивать его по пустому
    заголовку значило бы ставить не туда, где пользователь его ищет.

    Заголовки соседей взяты строчной латиницей нарочно. Ники в Telegram
    только латинские, а база сравнивает строки по кодам символов: с
    кириллическими заголовками или с заглавной латиницей канал без
    заголовка встал бы с краю по свойствам кодировки, а не по подстановке
    ника, и подстановку это не доказывало бы.
    """
    await put(
        session_factory,
        channel_row(username="mike", title=None),
        channel_row(username="ignored", title="alpha"),
        channel_row(username="ignored2", title="zulu"),
    )

    assert await titles_of(session) == ["alpha", None, "zulu"]


async def test_a_deactivated_channel_keeps_its_place(session, session_factory):
    """Выключенный канал остаётся на своём месте по числу вакансий."""
    off = channel_row(username="a", title="Выключён", is_active=False)
    on = channel_row(username="b", title="Включён", is_active=True)
    await put(session_factory, off, on)
    await put(session_factory, vacancy_row(source_channel_id=off.id))

    assert await titles_of(session) == ["Выключён", "Включён"]
