"""Основание, от которого объявляются таблицы."""

from datetime import datetime

from sqlalchemy import DateTime, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


# `sort_order` держит колонку на её нынешнем месте среди объявленных: без него
# пришедшее из примеси встаёт раньше собственных колонок класса, потому что
# порядок берётся из мига объявления, а примесь объявлена здесь — до них.
# Схему пишет не этот порядок, а миграция, но пересобирают её автогенерацией
# по этим же объявлениям — то есть отметки времени переехали бы в начало
# таблиц при ближайшей пересборке.


class IdMixin:
    """Числовой первичный ключ, одинаковый у всех таблиц."""

    id: Mapped[int] = mapped_column(primary_key=True, sort_order=-100)


class CreatedAtMixin:
    """Время заведения строки, проставляемое базой."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        sort_order=100,
    )


class UpdatedAtMixin:
    """Время последней правки строки, обновляемое базой на каждый UPDATE."""

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        sort_order=100,
    )
