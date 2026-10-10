"""Ведение записей об агрегаторах."""

from datetime import datetime

from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.domain.hosts import normalize_host, owning_host, owning_hosts
from backend.models import Aggregator, Application, TrashEvent, Vacancy
from backend.payloads import SourceStats
from backend.models.settings import AGGREGATOR_KIND
from backend.repository.blacklist_marks import BlacklistMark
from backend.repository.search import matches_search
from backend.repository.source_stats import source_stats
from backend.repository.vacancies_common import counted_vacancies
from backend.repository.vacancies_life import repoint_vacancies

WEB_SEARCH_NAME = "Поиск по сети"

NOT_A_SITE = "Адрес не похож на сайт"
"""Набранное не сводится к хосту. Одна фраза на заведение агрегатора и на его
запись в чёрный список: человек набирает в обоих окнах одно и то же."""

_LISTED_ORDER = (Aggregator.host.is_not(None), Aggregator.id)
"""«Поиск по сети» первым, дальше в порядке заведения — у обоих перечней."""


async def find_aggregator(session: AsyncSession, host: str) -> Aggregator | None:
    """Агрегатор с этим хостом; пусто — такого не заводили."""
    return await session.scalar(select(Aggregator).where(Aggregator.host == host))


async def create_aggregator(
    session: AsyncSession, address: str, name: str, avatar: bytes | None
) -> tuple[Aggregator | None, str]:
    """Завести агрегатор по адресу, набранному как угодно. Новый выключен и без входа."""
    host = normalize_host(address)
    if not host:
        return None, "invalid"
    known = await find_aggregator(session, host)
    if known is not None:
        return known, "exists"
    row = Aggregator(name=name, host=host, avatar=avatar, is_active=False, is_logged_in=False)
    session.add(row)
    await session.flush()
    return row, "created"


async def list_aggregators(session: AsyncSession) -> list[Aggregator]:
    """Все источники-агрегаторы: «Поиск по сети» первым, дальше в порядке заведения."""
    return list((await session.scalars(
        select(Aggregator).order_by(*_LISTED_ORDER)
    )).all())


async def web_search_id(session: AsyncSession) -> int:
    """Профиль «Поиска по сети»: у формы работодателя своего агрегатора нет."""
    return next((a.id for a in await list_aggregators(session) if a.host is None), 0)


def aggregator_blacklist_candidates(row: Aggregator) -> list[str]:
    """Написания агрегатора в чёрном списке — его хост и сайты, чей он поддомен
    (`owning_hosts`); у «Поиска по сети» хоста нет.

    Поддомен отмеченного сайта — тот же сайт, как и в отсеве ссылок: иначе
    агрегатор на нём обходился бы, а каждая его страница отбивалась отсевом.
    Список — под договором отметок (`blacklist_marks`), общим с людьми,
    компаниями и каналами.
    """
    return owning_hosts(row.host) if row.host else []


AGGREGATOR_BLACKLIST = BlacklistMark(AGGREGATOR_KIND, aggregator_blacklist_candidates)

# Имя для зовущих вне репозитория: им нужно только «чем отмечен», а не вся отметка.
aggregator_blacklist_value = AGGREGATOR_BLACKLIST.value


async def deactivate_blacklisted_aggregators(session: AsyncSession) -> int:
    """Выключить агрегаторы под действующей отметкой; сколько выключено.

    «Поиск по сети» под неё не попадает: написаний у него нет.
    """
    return await AGGREGATOR_BLACKLIST.switch_off(session, Aggregator)


async def barred_hosts(session: AsyncSession) -> set[str]:
    """Хосты сайтов под действующей отметкой отсева.

    Чья ссылка, решает `owning_host` по этому набору: поддомен отмеченного
    сайта — тот же сайт. Набор читается разом, когда ссылок много.
    """
    return await AGGREGATOR_BLACKLIST.marked(session)


async def barred_host_of(session: AsyncSession, urls: list[str]) -> str | None:
    """Отмеченный отсевом хост, которому принадлежит одна из ссылок; пусто — ни одна.

    Принадлежность — та же, что у номера вакансии (`host_owns`): поддомен
    сайта — тот же сайт. Отсеивает и то, что текстовый отсев не видит: адрес
    страницы в её тексте обычно не стоит.
    """
    marked = await barred_hosts(session)
    if not marked:
        return None
    return next((host for host in (owning_host(url, marked) for url in urls) if host), None)


async def list_aggregators_with_counts(
    session: AsyncSession, search: str | None = None
) -> list[tuple[Aggregator, int, bool]]:
    """Источники для экрана «Агрегаторы»: счёт разобранных вакансий и отметка отсева.

    Поиск по имени и хосту идёт питоном, как у каналов: перечень невелик, а
    правило совпадения одно на все экраны (`search.matches_search`).
    """
    rows = (await session.execute(
        counted_vacancies(Aggregator, Vacancy.source_aggregator_id).order_by(*_LISTED_ORDER)
    )).all()
    marked = await barred_hosts(session)
    return [(row, int(cnt or 0), AGGREGATOR_BLACKLIST.among(row, marked))
            for row, cnt in rows if matches_search(search, row.name, row.host)]


async def get_aggregator_detail(
    session: AsyncSession, aggregator_id: int
) -> tuple[Aggregator, SourceStats, str | None] | None:
    """Агрегатор, числа его карточки — те же, что у канала, — и значение его отметки отсева."""
    row = await session.get(Aggregator, aggregator_id)
    if row is None:
        return None
    stats = await source_stats(session, Vacancy.source_aggregator_id == aggregator_id)
    return row, stats, await aggregator_blacklist_value(session, row)


async def set_aggregator_active(session: AsyncSession, aggregator_id: int, active: bool) -> str:
    """Включить или выключить агрегатор. Без входа и в отсеве включить нельзя.

    Запрет отсева стоит здесь, а не в окне: пройди включение — отметка была бы
    отменена нажатием, которое про неё ничего не знает.
    """
    row = await session.get(Aggregator, aggregator_id)
    if row is None:
        return "missing"
    if active and not row.is_logged_in:
        return "not_logged_in"
    if active and await aggregator_blacklist_value(session, row) is not None:
        return "blacklisted"
    row.is_active = active
    return "ok"


async def set_logged_in(session: AsyncSession, aggregator_id: int, logged_in: bool) -> None:
    """Отметка входа. Включённость не трогает: без входа агрегатор просто не обходится."""
    row = await session.get(Aggregator, aggregator_id)
    if row is not None and row.host is not None:
        row.is_logged_in = logged_in


async def mark_run(session: AsyncSession, aggregator_id: int, started_at: datetime) -> None:
    row = await session.get(Aggregator, aggregator_id)
    if row is not None:
        row.last_run_at = started_at


async def applications_of(session: AsyncSession, aggregator_id: int) -> int:
    """Откликов, связанных с агрегатором, — их число окно называет перед удалением.

    Свои — и по вакансиям с него, и отклики его кнопкой на вакансии из других
    источников.
    """
    return int(await session.scalar(
        select(func.count(Application.id))
        .join(Vacancy, Vacancy.id == Application.vacancy_id)
        .where(or_(Vacancy.source_aggregator_id == aggregator_id,
                   Application.aggregator_id == aggregator_id))
    ) or 0)


async def delete_aggregator(session: AsyncSession, aggregator_id: int) -> str:
    """Удалить агрегатор. Вакансии, отклики и отметки о мусоре остаются, ссылка на него — нет.

    Ссылки обнуляет код: правила «обнулить при удалении» у внешних ключей нет.
    Вакансии отвязывает общее `repoint_vacancies`; отклики и мусор — другие
    таблицы, и у каждой свой запрос: обобщать `repoint_vacancies` на любую
    модель его докстрока запрещает.
    """
    block = await deletion_block(session, aggregator_id)
    if block is not None:
        return block
    row = await session.get(Aggregator, aggregator_id)
    await repoint_vacancies(
        session, Vacancy.source_aggregator_id, absorbed_id=aggregator_id, survivor_id=None
    )
    await session.execute(
        update(Application).where(Application.aggregator_id == aggregator_id)
        .values(aggregator_id=None)
    )
    await session.execute(
        update(TrashEvent).where(TrashEvent.source_aggregator_id == aggregator_id)
        .values(source_aggregator_id=None)
    )
    await session.delete(row)
    return "ok"


async def deletion_block(session: AsyncSession, aggregator_id: int) -> str | None:
    """Почему агрегатор не удалить: `missing` — его нет, `protected` — это «Поиск по сети»."""
    row = await session.get(Aggregator, aggregator_id)
    if row is None:
        return "missing"
    return "protected" if row.host is None else None


async def round_sources(session: AsyncSession) -> list[Aggregator]:
    """Источники общего обхода: включённые агрегаторы со входом, затем «Поиск по сети».

    Отмеченные отсевом отбрасываются и включёнными: строку могли включить мимо
    окна, а обход сайта из отсева принёс бы ровно то, от чего ограждались.
    """
    marked = await barred_hosts(session)
    rows = (await session.scalars(
        select(Aggregator)
        .where(Aggregator.is_active.is_(True), Aggregator.is_logged_in.is_(True))
        .order_by(Aggregator.host.is_(None), Aggregator.id)
    )).all()
    return [row for row in rows if not AGGREGATOR_BLACKLIST.among(row, marked)]
