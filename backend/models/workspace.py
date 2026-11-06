"""Профили (в интерфейсе «Профиль») и их строки «профиль × предмет».

Профиль — одно направление поиска: своя анкета, вакансии, тумблеры источников
и отметки чтения. Сами каналы, агрегаторы и записи чёрного списка общие, а их
тумблеры лежат здесь, по строке на профиль. Строки нет — выключено и не
читано: так своё, заведённое в одном профиле, в остальных выключено.

Внешние ключи названы строками имён таблиц, а моделей модуль не ввозит: его
ввозят модули общих моделей, и обратный ввоз замкнул бы круг.
"""

from datetime import datetime

from sqlalchemy import BigInteger, ColumnElement, DateTime, ForeignKey, Index, select, text
from sqlalchemy.orm import InstrumentedAttribute, Mapped, mapped_column
from sqlalchemy.sql import expression

from backend.models.base import Base, CreatedAtMixin, IdMixin


class Workspace(IdMixin, CreatedAtMixin, Base):
    """Профиль. Активен всегда ровно один; номер активного помнит база.

    Пустая строка пути значит «пути нет»: значение одно, а не два
    (`NULL` и `''`), чтобы его не сравнивали двумя способами.

    Номер удалённого профиля не достаётся новому (`AUTOINCREMENT`): разбор
    резюме идёт мимо места прогона и пишет в запомненный номер — с повтором
    номера анкета удалённого профиля легла бы в новый, а не упала бы на ключе.
    """

    __tablename__ = "workspace"
    __table_args__ = (
        Index(
            "uq_workspace_active",
            "is_active",
            unique=True,
            postgresql_where=text("is_active"),
            sqlite_where=text("is_active"),
        ),
        {"sqlite_autoincrement": True},
    )

    is_active: Mapped[bool] = mapped_column(server_default=expression.false())
    cv_path: Mapped[str] = mapped_column(server_default="")
    photo_path: Mapped[str] = mapped_column(server_default="")


class WorkspaceChannel(Base):
    """Тумблер и отметка чтения канала в профиле."""

    __tablename__ = "workspace_channel"

    workspace_id: Mapped[int] = mapped_column(
        ForeignKey("workspace.id", ondelete="CASCADE"), primary_key=True
    )
    channel_id: Mapped[int] = mapped_column(
        ForeignKey("telegram_channel.id", ondelete="CASCADE"), primary_key=True
    )
    is_active: Mapped[bool] = mapped_column(server_default=expression.false())
    # BigInteger: номер поста в долгоживущем массовом канале выходит за 2^31.
    last_processed_msg_id: Mapped[int | None] = mapped_column(BigInteger)


class WorkspaceAggregator(Base):
    """Тумблер, отметка чтения и выбранное резюме агрегатора в профиле.

    Выбранное резюме одно на сайт в профиле: это держит первичный ключ, а не
    частичный индекс. Удалённое резюме снимается с выбора само (`SET NULL`).
    """

    __tablename__ = "workspace_aggregator"

    workspace_id: Mapped[int] = mapped_column(
        ForeignKey("workspace.id", ondelete="CASCADE"), primary_key=True
    )
    aggregator_id: Mapped[int] = mapped_column(
        ForeignKey("aggregator.id", ondelete="CASCADE"), primary_key=True
    )
    is_active: Mapped[bool] = mapped_column(server_default=expression.false())
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    chosen_resume_id: Mapped[int | None] = mapped_column(
        ForeignKey("aggregator_resume.id", ondelete="SET NULL")
    )


class WorkspaceBlacklist(Base):
    """Включена ли запись чёрного списка в профиле."""

    __tablename__ = "workspace_blacklist"

    workspace_id: Mapped[int] = mapped_column(
        ForeignKey("workspace.id", ondelete="CASCADE"), primary_key=True
    )
    blacklist_id: Mapped[int] = mapped_column(
        ForeignKey("blacklist.id", ondelete="CASCADE"), primary_key=True
    )
    active: Mapped[bool] = mapped_column(server_default=expression.false())


ACTIVE_WORKSPACE_ID = (
    select(Workspace.id).where(Workspace.is_active).scalar_subquery()
)
"""Номер активного профиля подзапросом: читатели берут его в том же запросе,
что и строку, а не отдельным походом в базу."""


def switch_in(
    column: ColumnElement,
    link: InstrumentedAttribute[int],
    owner_id: ColumnElement[int],
    workspace: int | ColumnElement[int],
) -> ColumnElement:
    """Значение из строки «профиль × предмет» этого предмета в профиле `workspace`.

    Коррелированный подзапрос для загружаемых атрибутов общих моделей. Своя
    таблица исключена из корреляции: иначе запрос, уже соединённый с ней
    (гашение отметок, слияние), оставил бы подзапрос без FROM. Строки нет —
    подзапрос пуст, и обёртку под «выключено» ставит зовущий.
    """
    table = link.class_
    return (
        select(column)
        .where(link == owner_id, table.workspace_id == workspace)
        .correlate_except(table)
        .scalar_subquery()
    )
