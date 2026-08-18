"""Следствия удаления канала кнопкой окна.

Кнопка пишет в своей сделке и закрывает её сама. Читает результат окно уже
другим обращением, поэтому незакрытая сделка выглядела бы как кнопка, которая
ничего не сделала.

Сброс курсора сюда не входит: он идёт мимо бота, прямо в репозиторий, и
проверяется на мосту (`tests/client/test_bridge_channel_actions.py`) и в самом
репозитории (`tests/backend/test_repository_channel_cursor.py`).
"""

from backend.models import TelegramChannel, Vacancy
from tests.dbio import all_rows, only_row, put
from tests.factories import channel_row, vacancy_row


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
