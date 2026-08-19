"""Следствия чтения и записи режима бота.

Режим живёт единственной строкой состояния и кэшу не подлежит: окно
переключает его, пока бот работает, и запомненное значение означало бы, что
переключатель срабатывает только после перезапуска.
"""

from backend.models import BotMode, BotState
from backend.repository.bot_mode import read_mode, write_mode
from tests.dbio import all_rows, only_row, put
from tests.factories import bot_state_row


async def test_a_missing_row_reads_as_off(session):
    """Без строки состояния режим читается выключенным.

    Пустая база значит первый запуск, и начинать его с рассылки откликов
    нельзя.
    """
    assert await read_mode(session) is BotMode.OFF


async def test_the_stored_mode_is_read_back(session, session_factory):
    """Записанный режим читается тем же, каким записан."""
    await put(session_factory, bot_state_row(BotMode.FULL))

    assert await read_mode(session) is BotMode.FULL


async def test_the_row_is_created_when_it_is_missing(session, session_factory):
    """Первая запись режима заводит строку состояния сама.

    Смотрим саму строку, а не чтение обратно: чтение берёт первую попавшуюся
    и о том, откуда она взялась, не говорит ничего.
    """
    await write_mode(session, BotMode.FULL)
    await session.commit()

    assert (await only_row(session_factory, BotState)).mode is BotMode.FULL


async def test_a_change_updates_the_same_row(session, session_factory):
    """Смена режима правит ту же строку, а не заводит вторую.

    Таблица односрочная, и вторая строка чтению не видна вовсе — оно берёт
    первую. Поэтому считаем строки, а не читаем режим: заводись вторая, бот
    и окно расходились бы в показаниях без всякой приметы.
    """
    await put(session_factory, bot_state_row(BotMode.FULL))

    await write_mode(session, BotMode.DM_ONLY)
    await session.commit()

    rows = await all_rows(session_factory, BotState)
    assert [row.mode for row in rows] == [BotMode.DM_ONLY]
