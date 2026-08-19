"""Режим бота, записанный в единственной строке состояния.

Живёт порознь от кэша настроек нарочно: тот держит прочитанное в памяти и
отдаёт его без обращения к базе, а режим переключают из окна и читают на
каждом ударе часов бота — кэшировать его значило бы отвечать вчерашним
словом. Общего у них только дом в той же таблице настроек.
"""

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import BotMode, BotState

logger = logging.getLogger(__name__)


async def _state_row(session: AsyncSession) -> BotState | None:
    """Единственная строка состояния бота, если она заведена."""
    return (await session.scalars(select(BotState))).first()


async def read_mode(session: AsyncSession) -> BotMode:
    """Режим, записанный в базе; без строки состояния — выключен.

    Выключен, а не «полный вперёд»: пустая база значит первый запуск, и
    начинать его с рассылки откликов нельзя.
    """
    row = await _state_row(session)
    return row.mode if row is not None else BotMode.OFF


async def write_mode(session: AsyncSession, mode: BotMode) -> None:
    """Записать режим. Транзакцию закрывает зовущий.

    Смена пишется в журнал здесь же, под чужой ещё не закрытой сделкой:
    откатись она, в журнале осталась бы запись о переключении, которого не
    было. Плата принята сознательно — переключений считанные единицы за день,
    а зов у записи всегда один и тот же, и вынеси запись к зовущим, её забыл
    бы первый же новый.
    """
    row = await _state_row(session)
    prev = row.mode.value if row is not None else None
    if row is None:
        session.add(BotState(id=1, mode=mode))
    else:
        row.mode = mode
    if prev != mode.value:
        logger.info("Bot mode changed: %s -> %s", prev, mode.value)
