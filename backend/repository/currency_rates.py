"""Кэш курсов валют: чтение по знакам и замена пришедшим от источника."""

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.ext.asyncio import AsyncSession

from backend.domain.currency import CURRENCY_WRITINGS
from backend.models import CurrencyRate

_SIGN_OF_CODE = {code: sign for sign, code, _ in CURRENCY_WRITINGS}


async def load_rates(session: AsyncSession) -> dict[str, float]:
    """Курсы за 1 USD по знаку валюты — так валюту хранят анкета и вакансия."""
    rows = await session.scalars(select(CurrencyRate))
    return {_SIGN_OF_CODE[row.code]: row.per_usd for row in rows}


async def rates_fetched_at(session: AsyncSession) -> datetime:
    """Когда курсы пришли в последний раз. Самое позднее, а не раннее: код,
    пропавший из ответа источника, иначе держал бы кэш старым навсегда. Кэш
    пустым не бывает: его заполняет миграция."""
    return await session.scalar(select(func.max(CurrencyRate.fetched_at)))


async def save_rates(session: AsyncSession, by_code: dict[str, float], now: datetime) -> int:
    """Записать пришедшие курсы наших валют. Код, которого нет в ответе,
    сохраняет прежний курс. Вставка с заменой, а не «прочитать и дописать»:
    две загрузки слепков разом (опрос и «Прогнать заново») не столкнутся на
    ключе. Транзакцию закрывает зовущий. Отвечает, сколько курсов записано."""
    rows = [{"code": code, "per_usd": rate, "fetched_at": now}
            for code, rate in by_code.items() if code in _SIGN_OF_CODE]
    if not rows:
        return 0
    statement = insert(CurrencyRate).values(rows)
    await session.execute(statement.on_conflict_do_update(
        index_elements=[CurrencyRate.code],
        set_={"per_usd": statement.excluded.per_usd, "fetched_at": statement.excluded.fetched_at},
    ))
    return len(rows)
