"""Воронка по источникам — каналам и агрегаторам — для экрана статистики."""

from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.domain.funnel import INVITED, RESPONDED
from backend.domain.verdict import JUNK_SKIP_PREFIXES
from backend.models import (
    Aggregator,
    TelegramChannel,
    TrashEvent,
    Vacancy,
    VacancyStatus,
)

from backend.repository.stats_common import (
    first_transition_subq,
    parsed_in_window,
    stats_period_since,
)
from backend.repository.stats_rows import SourceKey, pipeline_row, source_item
from backend.repository.vacancies_common import PARSED_ONLY

_VACANCY_SOURCE = (Vacancy.source_channel_id, Vacancy.source_aggregator_id)

def _trash_predicates():
    """Два условия «мусор» и «просто не подошло», набранные одним образцом.

    Мусор — посты, не бывшие вакансией: отвергнутые вердиктом и пустые. При
    обычном разборе строку удаляют, и счёт хранится в `trash_event`; при
    повторном строка остаётся со статусом «не подходит» и меткой в причине
    отказа. Метки две (`JUNK_SKIP_PREFIXES`), и обе значат здесь одно.
    Чистое «не подошло» — тот же статус **без** меток: отсев по языку,
    месту, уровню.

    Образец один на оба условия нарочно: они обязаны быть отрицанием друг
    друга, а набранные порознь разъехались бы молча. Пробел у метки в
    образец не идёт — за ним следует сама причина.
    """
    marked_trash = or_(
        *[
            Vacancy.skip_reason.like(f"{prefix.rstrip()}%")
            for prefix in JUNK_SKIP_PREFIXES
        ]
    )
    is_rerun_trash = and_(Vacancy.status == VacancyStatus.NOT_FIT, marked_trash)
    is_not_fit_clean = and_(
        Vacancy.status == VacancyStatus.NOT_FIT,
        or_(Vacancy.skip_reason.is_(None), ~marked_trash),
    )
    return is_rerun_trash, is_not_fit_clean


async def _ingest_by_source(session: AsyncSession, since) -> list:
    """Сколько каждый источник прислал за окно: всего, мусора, «не подошло».

    Соединения внешние: вакансии без источника собираются под пустой парой.
    Подпись агрегатора — его имя, в той же колонке, что название канала.
    """
    is_rerun_trash, is_not_fit_clean = _trash_predicates()
    return (
        await session.execute(
            select(
                *_VACANCY_SOURCE,
                func.coalesce(TelegramChannel.title, Aggregator.name),
                TelegramChannel.username,
                func.count(Vacancy.id).label("total"),
                func.sum(case((is_rerun_trash, 1), else_=0)).label("rerun_trash"),
                func.sum(case((is_not_fit_clean, 1), else_=0)).label("not_fit"),
            )
            .select_from(Vacancy)
            .outerjoin(TelegramChannel, Vacancy.source_channel_id == TelegramChannel.id)
            .outerjoin(Aggregator, Vacancy.source_aggregator_id == Aggregator.id)
            .where(*parsed_in_window(since))
            .group_by(*_VACANCY_SOURCE)
        )
    ).all()


async def _trash_events_by_source(session: AsyncSession, since) -> dict[SourceKey, int]:
    """Сколько мусора удалено у каждого источника за то же окно.

    Отдельным запросом потому, что удалённых строк в `vacancy` уже нет:
    счёт живёт своей таблицей, и рамка времени у неё своя, но та же.
    """
    where = [TrashEvent.created_at >= since] if since is not None else []
    rows = (
        await session.execute(
            select(TrashEvent.source_channel_id, TrashEvent.source_aggregator_id,
                   func.count(TrashEvent.id))
            .where(*where)
            .group_by(TrashEvent.source_channel_id, TrashEvent.source_aggregator_id)
        )
    ).all()
    return {(ch_id, agg_id): int(cnt or 0) for ch_id, agg_id, cnt in rows}


async def _first_in_period_by_source(
    session: AsyncSession, statuses, since
) -> dict[SourceKey, set[int]]:
    """Чьи вакансии впервые дошли до этих статусов внутри окна.

    Считается по самому переходу, а не по заведению вакансии: воронка
    показывает продвижение за период и обязана сходиться с верхними
    числами экрана, которые считаются так же.
    """
    sub = first_transition_subq(statuses)
    q = (
        select(*_VACANCY_SOURCE, sub.c.vid)
        .join(sub, sub.c.vid == Vacancy.id)
        .where(PARSED_ONLY)
    )
    if since is not None:
        q = q.where(sub.c.first_at >= since)
    by_source: dict[SourceKey, set[int]] = {}
    for ch_id, agg_id, vid in (await session.execute(q)).all():
        by_source.setdefault((ch_id, agg_id), set()).add(vid)
    return by_source


async def _funnel_by_source(
    session: AsyncSession, since
) -> dict[str, dict[SourceKey, set[int]]]:
    """Четыре ступени воронки, разложенные по источникам.

    Ключи здесь — это имена колонок в ответе окну: `pipeline_row` кладёт
    их в строку как есть. Переименуй ступень тут — и колонка на экране
    опустеет, потому что окно читает её по имени.
    """
    return {
        "sent": await _first_in_period_by_source(
            session, VacancyStatus.APPLIED, since
        ),
        "answered": await _first_in_period_by_source(session, RESPONDED, since),
        "invite_plus": await _first_in_period_by_source(session, INVITED, since),
        "decline": await _first_in_period_by_source(
            session, VacancyStatus.DECLINE, since
        ),
    }


async def _sources_without_ingest(
    session: AsyncSession, missing: set[SourceKey]
) -> dict[SourceKey, dict]:
    """Пустые строки для источников, у которых в окне не было ингеста.

    Старая вакансия могла впервые дойти до нужного статуса внутри окна, а
    мусор — удалиться, не оставив строки. Без этих строк такой источник из
    таблицы выпал бы, хотя за период у него кое-что было.

    Строке без источника спрашивать базу не о чем: подпись у неё своя.
    """
    found = {key: source_item(key, None, None) for key in missing if key == (None, None)}
    channel_ids = {ch for ch, _ in missing if ch is not None}
    aggregator_ids = {agg for ch, agg in missing if ch is None and agg is not None}
    if channel_ids:
        rows = (await session.execute(
            select(TelegramChannel.id, TelegramChannel.title, TelegramChannel.username)
            .where(TelegramChannel.id.in_(channel_ids))
        )).all()
        found.update({(ch, None): source_item((ch, None), title, username)
                      for ch, title, username in rows})
    if aggregator_ids:
        rows = (await session.execute(
            select(Aggregator.id, Aggregator.name).where(Aggregator.id.in_(aggregator_ids))
        )).all()
        found.update({(None, agg): source_item((None, agg), name, None) for agg, name in rows})
    return found


async def get_stats_channels_pipeline(
    session: AsyncSession, *, period: str
) -> dict:
    """Таблица «что источник прислал и куда это дошло» за выбранное окно.

    Ингест считается по времени заведения вакансии, воронка — по времени
    самого перехода; состав строки и обе доли — у `pipeline_row`, ступени
    воронки — у `_funnel_by_source`. Окно `all` времени не спрашивает.

    Источник попадает в таблицу, если в окне у него было хоть что-то: ингест,
    удалённый мусор или продвижение по воронке. Порядок строк задаёт окно:
    равных в нём решает подпись, а её собирает окно.
    """
    since = stats_period_since(period)
    trash_events = await _trash_events_by_source(session, since)
    funnel = await _funnel_by_source(session, since)

    items: dict[SourceKey, dict] = {}
    for ch_id, agg_id, title, username, total_vac, rerun_trash, not_fit in (
        await _ingest_by_source(session, since)
    ):
        key = (ch_id, agg_id)
        items[key] = source_item(key, title, username, (total_vac, rerun_trash, not_fit))
    seen_elsewhere = set(trash_events)
    for by_source in funnel.values():
        seen_elsewhere.update(by_source)
    items.update(await _sources_without_ingest(session, seen_elsewhere - set(items)))

    rows = [pipeline_row(key, item, trash_events.get(key, 0), funnel) for key, item in items.items()]
    return {"period": period, "channels": rows}
