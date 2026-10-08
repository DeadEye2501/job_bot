"""Воронка по каналам для экрана статистики."""

from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.domain.funnel import INVITED, RESPONDED
from backend.domain.verdict import JUNK_SKIP_PREFIXES
from backend.models import (
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
from backend.repository.vacancies_common import PARSED_ONLY

def _channel_item(
    ch_id: int | None,
    title: str | None,
    username: str | None,
    counts: tuple[int, int, int] = (0, 0, 0),
) -> dict:
    """Строка канала в таблице статистики.

    Строку собирают два прохода — по тем, кто прислал что-то в окне, и по
    тем, кто попал в неё только воронкой. Разойдись сборка, один и тот же
    канал выглядел бы в таблице по-разному в зависимости от того, каким
    проходом он туда попал.

    Счётчики приходят тройкой, потому что тройкой их и отдаёт запрос; у
    канала, попавшего в таблицу воронкой, их нет вовсе, и нули у него значат
    «ничего не было», а не «пока неизвестно».

    Подписи здесь нет: её собирает окно тем же правилом, что в Контактах. Пустой
    номер — строка всего, что пришло не из канала.
    """
    total_vac, rerun_trash, not_fit = counts
    return {
        "id": ch_id,
        "title": title,
        "username": username,
        "_total_vac": int(total_vac or 0),
        "_rerun_trash": int(rerun_trash or 0),
        "not_fit": int(not_fit or 0),
    }


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


async def _ingest_by_channel(session: AsyncSession, since) -> list:
    """Сколько каждый канал прислал за окно: всего, мусора, «не подошло».

    Соединение внешнее: вакансии без канала собираются под пустым номером.
    """
    is_rerun_trash, is_not_fit_clean = _trash_predicates()
    return (
        await session.execute(
            select(
                Vacancy.source_channel_id,
                TelegramChannel.title,
                TelegramChannel.username,
                func.count(Vacancy.id).label("total"),
                func.sum(case((is_rerun_trash, 1), else_=0)).label("rerun_trash"),
                func.sum(case((is_not_fit_clean, 1), else_=0)).label("not_fit"),
            )
            .select_from(Vacancy)
            .outerjoin(TelegramChannel, Vacancy.source_channel_id == TelegramChannel.id)
            .where(*parsed_in_window(since))
            .group_by(Vacancy.source_channel_id)
        )
    ).all()


async def _trash_events_by_channel(
    session: AsyncSession, since
) -> dict[int | None, int]:
    """Сколько мусора удалено у каждого канала за то же окно.

    Отдельным запросом потому, что удалённых строк в `vacancy` уже нет:
    счёт живёт своей таблицей, и рамка времени у неё своя, но та же.
    """
    where = [TrashEvent.created_at >= since] if since is not None else []
    rows = (
        await session.execute(
            select(TrashEvent.source_channel_id, func.count(TrashEvent.id))
            .where(*where)
            .group_by(TrashEvent.source_channel_id)
        )
    ).all()
    return {ch_id: int(cnt or 0) for ch_id, cnt in rows}


async def _first_in_period_by_channel(
    session: AsyncSession, statuses, since
) -> dict[int | None, set[int]]:
    """Чьи вакансии впервые дошли до этих статусов внутри окна.

    Считается по самому переходу, а не по заведению вакансии: воронка
    показывает продвижение за период и обязана сходиться с верхними
    числами экрана, которые считаются так же.
    """
    sub = first_transition_subq(statuses)
    q = (
        select(Vacancy.source_channel_id, sub.c.vid)
        .join(sub, sub.c.vid == Vacancy.id)
        .where(PARSED_ONLY)
    )
    if since is not None:
        q = q.where(sub.c.first_at >= since)
    by_ch: dict[int | None, set[int]] = {}
    for ch_id, vid in (await session.execute(q)).all():
        by_ch.setdefault(ch_id, set()).add(vid)
    return by_ch


async def _funnel_by_channel(
    session: AsyncSession, since
) -> dict[str, dict[int | None, set[int]]]:
    """Четыре ступени воронки, разложенные по каналам.

    Ключи здесь — это имена колонок в ответе окну: `_pipeline_row` кладёт
    их в строку как есть. Переименуй ступень тут — и колонка на экране
    опустеет, потому что окно читает её по имени.
    """
    return {
        "sent": await _first_in_period_by_channel(
            session, VacancyStatus.APPLIED, since
        ),
        "answered": await _first_in_period_by_channel(session, RESPONDED, since),
        "invite_plus": await _first_in_period_by_channel(session, INVITED, since),
        "decline": await _first_in_period_by_channel(
            session, VacancyStatus.DECLINE, since
        ),
    }


async def _channels_without_ingest(
    session: AsyncSession, missing_ids: set[int | None]
) -> dict[int | None, dict]:
    """Пустые строки для каналов, у которых в окне не было ингеста.

    Старая вакансия могла впервые дойти до нужного статуса внутри окна, а
    мусор — удалиться, не оставив строки. Без этих строк такой канал из
    таблицы выпал бы, хотя за период у него кое-что было.

    Строке без канала спрашивать базу не о чем: подпись у неё своя, а пустой
    номер в `IN` ничего бы и не нашёл.
    """
    found = (
        {None: _channel_item(None, None, None)} if None in missing_ids else {}
    )
    channel_ids = missing_ids - {None}
    if not channel_ids:
        return found
    rows = (
        await session.execute(
            select(
                TelegramChannel.id, TelegramChannel.title, TelegramChannel.username
            ).where(TelegramChannel.id.in_(channel_ids))
        )
    ).all()
    found.update(
        (ch_id, _channel_item(ch_id, title, username))
        for ch_id, title, username in rows
    )
    return found


def _pipeline_row(ch_id: int | None, item: dict, trash_events: int, funnel) -> dict:
    """Строка таблицы по одному каналу: ингест, воронка и две доли.

    Всего — это и строки вакансий, и удалённый мусор: последнего в
    `vacancy` уже нет, а прислан каналом он был.

    Доли считаются по одной когорте: и в числителе, и в знаменателе только
    те вакансии, отклик на которые ушёл внутри окна. Считай мы числитель по
    своему множеству — вакансия, откликнутая до окна и ответившая внутри,
    попадала бы в числитель, минуя знаменатель, и доля переваливала бы за
    сотню. Столбцы воронки рядом остаются как есть: они отвечают на другой
    вопрос — сколько вообще прошло ступень за период.

    При нуле отправленных долей нет вовсе — ноль там означал бы «отвечают
    нулю процентов», а не «спрашивать не с чего».
    """
    total = item["_total_vac"] + trash_events
    trash = trash_events + item["_rerun_trash"]
    not_fit = item["not_fit"]
    reached = {name: by_ch.get(ch_id, set()) for name, by_ch in funnel.items()}
    counts = {name: len(ids) for name, ids in reached.items()}
    sent_ids = reached["sent"]

    def share(stage: str) -> float | None:
        if not sent_ids:
            return None
        return round(len(reached[stage] & sent_ids) / len(sent_ids) * 100, 1)

    return {
        "id": ch_id,
        "title": item["title"],
        "username": item["username"],
        "total": total,
        "trash": trash,
        "not_fit": not_fit,
        "fit": max(0, total - trash - not_fit),
        **counts,
        "conv_answ_sent": share("answered"),
        "conv_invite_sent": share("invite_plus"),
    }


async def get_stats_channels_pipeline(
    session: AsyncSession, *, period: str
) -> dict:
    """Таблица «что канал прислал и куда это дошло» за выбранное окно.

    Ингест считается по времени заведения вакансии, воронка — по времени
    самого перехода; состав строки и обе доли — у `_pipeline_row`, ступени
    воронки — у `_funnel_by_channel`. Окно `all` времени не спрашивает.

    Канал попадает в таблицу, если в окне у него было хоть что-то: ингест,
    удалённый мусор или продвижение по воронке. Порядок строк задаёт окно:
    равных в нём решает подпись, а её собирает окно.
    """
    since = stats_period_since(period)
    trash_events_by_ch = await _trash_events_by_channel(session, since)
    funnel = await _funnel_by_channel(session, since)

    items_by_ch: dict[int | None, dict] = {}
    for ch_id, title, username, total_vac, rerun_trash, not_fit in (
        await _ingest_by_channel(session, since)
    ):
        items_by_ch[ch_id] = _channel_item(
            ch_id, title, username, (total_vac, rerun_trash, not_fit)
        )
    seen_elsewhere = set(trash_events_by_ch)
    for by_ch in funnel.values():
        seen_elsewhere.update(by_ch)
    items_by_ch.update(
        await _channels_without_ingest(session, seen_elsewhere - set(items_by_ch))
    )

    items = [
        _pipeline_row(ch_id, item, trash_events_by_ch.get(ch_id, 0), funnel)
        for ch_id, item in items_by_ch.items()
    ]
    return {"period": period, "channels": items}
