"""Следствия правки строки канала кнопками окна.

Обе кнопки — «сбросить курсор» и «удалить» — пишут в своей сделке и
закрывают её сами. Читает результат окно уже другим обращением, поэтому
незакрытая сделка выглядела бы как кнопка, которая ничего не сделала.
"""

from backend.models import TelegramChannel, Vacancy
from tests.dbio import all_rows, only_row, put
from tests.factories import channel_row, vacancy_row


async def test_resetting_a_cursor_survives_the_transaction(make_bot, session_factory):
    """Сброс курсора виден следующему обращению, а не только своему.

    Окно перечитывает список отдельным запросом: незакрытая сделка
    показала бы кнопку, которая ничего не сделала.
    """
    await put(session_factory, channel_row(last_processed_msg_id=500))
    bot = await make_bot()

    saved = await only_row(session_factory, TelegramChannel)
    assert await bot.reset_channel_cursor(saved.id) is True

    again = await only_row(session_factory, TelegramChannel)
    assert again.last_processed_msg_id is None


async def test_resetting_a_missing_cursor_says_so(make_bot):
    """Сброс курсора у несуществующего канала отвечает отказом, а не падает."""
    bot = await make_bot()

    assert await bot.reset_channel_cursor(404) is False


async def test_deleting_a_channel_keeps_its_vacancies(make_bot, session_factory):
    """Удаление канала оставляет собранные из него вакансии.

    Вакансия — итог работы пользователя со статусами и письмами; терять
    её вместе с источником было бы дороже, чем оставить без ссылки.
    """
    await put(session_factory, channel_row())
    saved = await only_row(session_factory, TelegramChannel)
    await put(
        session_factory,
        vacancy_row(title="осталась", source_channel_id=saved.id),
        vacancy_row(title="тоже осталась", source_channel_id=saved.id),
    )
    bot = await make_bot()

    assert await bot.delete_channel(saved.id) == 2

    assert await all_rows(session_factory, TelegramChannel) == []
    kept = await all_rows(session_factory, Vacancy)
    assert sorted(v.title for v in kept) == ["осталась", "тоже осталась"]
    assert [v.source_channel_id for v in kept] == [None, None]


async def test_deleting_a_missing_channel_says_so(make_bot):
    """Удаление несуществующего канала отвечает отсутствием, а не нулём.

    Ноль означал бы «удалили, вакансий не было», и окно показало бы
    успех там, где строки не было вовсе.
    """
    bot = await make_bot()

    assert await bot.delete_channel(404) is None
