"""Следствия наполнения строки списка каналов.

Счётчик вакансий и отметка чёрного списка собираются отдельными запросами и
раскладываются по строкам одним проходом — вместо запроса на каждый канал.
"""

from backend.repository.channels import list_telegram_channels
from tests.dbio import put
from tests.factories import channel_marks, marked_channels, vacancy_row


async def test_the_row_carries_its_count_and_blacklist_mark(
    session, session_factory
):
    """В строке списка едут счётчик вакансий и отметка чёрного списка."""
    listed, switched_off, other_kind = marked_channels()
    await put(session_factory, listed, switched_off, other_kind)
    await put(
        session_factory,
        vacancy_row(source_channel_id=listed.id),
        *channel_marks(),
    )

    rows = {r.channel.title: r for r in await list_telegram_channels(session)}

    assert rows["В списке"].vacancy_count == 1
    assert rows["В списке"].is_blacklisted is True
    assert rows["Отметка снята"].is_blacklisted is False
    assert rows["Чужой род"].is_blacklisted is False


async def test_an_unparsed_vacancy_is_not_counted(session, session_factory):
    """Недоразобранная вакансия в счётчик не идёт.

    Счётчик обещает то же, что человек увидит, открыв канал. Строка,
    заведённая, но ещё не прошедшая разбор, в выдачу не попадает, и
    посчитанная она давала бы «единицу», за которой ничего нет.
    """
    listed, _, _ = marked_channels()
    await put(session_factory, listed)
    await put(
        session_factory,
        vacancy_row(source_channel_id=listed.id),
        vacancy_row(source_channel_id=listed.id, is_parsed=False, title=None),
    )

    rows = {r.channel.title: r for r in await list_telegram_channels(session)}

    assert rows["В списке"].vacancy_count == 1
