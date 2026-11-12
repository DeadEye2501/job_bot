"""Кэш курсов валют: по нему названная сумма переводится в валюту анкеты."""

from datetime import datetime

from sqlalchemy import DateTime
from sqlalchemy.orm import Mapped, mapped_column

from backend.models.base import Base


class CurrencyRate(Base):
    """Курс одной валюты за 1 USD.

    Таблица одна на приложение, а не на профиль: курс от профиля не зависит.
    `fetched_at` — когда курс пришёл от источника; по самому позднему решается,
    пора ли спрашивать снова (`flows/rates_refresh`).
    """

    __tablename__ = "currency_rate"

    code: Mapped[str] = mapped_column(primary_key=True)
    per_usd: Mapped[float]
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
