"""Воронка по каналам для экрана статистики."""

from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.domain.funnel import INVITED, RESPONDED
from backend.domain.verdict import TRASH_SKIP_PREFIX
from backend.models import (
    TelegramChannel,
    TrashEvent,
    Vacancy,
    VacancyStatus,
)

from backend.repository.stats_common import (
    first_transition_subq,
    stats_period_since,
)
from backend.repository.vacancies_common import PARSED_ONLY

def _channel_item(
    ch_id: int,
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
    """
    total_vac, rerun_trash, not_fit = counts
    return {
        "id": ch_id,
        "label": title or (f"@{username}" if username else f"#{ch_id}"),
        "_total_vac": int(total_vac or 0),
        "_rerun_trash": int(rerun_trash or 0),
        "not_fit": int(not_fit or 0),
    }


async def get_stats_channels_pipeline(
    session: AsyncSession, *, period: str
) -> dict:
    """Per-channel pipeline-таблица для карточки «Каналы».

    Ингест-колонки (по `Vacancy.created_at >= since`):
      - total: всё, что канал прислал в окно (Vacancy-ряды + trash_events)
      - trash: auto-ingest deletions (`trash_event`) + ряды с
        `status=NOT_FIT` и `skip_reason` с меткой `TRASH_SKIP_PREFIX` (rerun-режим)
      - not_fit: `status=NOT_FIT` БЕЗ trash-маркера (отсев фит-валидатором)
      - fit = max(0, total − trash − not_fit)

    Funnel-колонки (по `min(changed_at) >= since` — distinct vacancy_id,
    у которых ПЕРВЫЙ переход в соответствующий набор статусов случился
    в окне period; для period='all' — лайфтайм без фильтра по времени):
      - sent: первый переход в Applied
      - answered: первый переход в любой из
        {Answered, Test, Invitation, In Progress, Offer, Decline}
      - invite_plus: первый переход в {Invitation, In Progress, Offer}
      - decline: первый переход в Decline
      - conv_answ_sent = answered/sent (None если sent=0)
      - conv_invite_sent = invite_plus/sent (None если sent=0)

    Канал попадает в таблицу, если в окне есть хоть что-то: ингест,
    trash-event или funnel-активность.

    Сортировка: по total desc, тай-брейкер по label.
    """
    since = stats_period_since(period)
    base_filter = [PARSED_ONLY]
    if since is not None:
        base_filter.append(Vacancy.created_at >= since)

    # Шаг 1: total / trash / not_fit per channel.
    #
    # «Trash» — посты, отсеянные LLM-валидатором как мусор. В auto-ingest
    # режиме они УДАЛЯЮТСЯ из ``vacancy``, и счётчик хранится в отдельной
    # таблице ``trash_event`` (см. flows/cleanup.py, delete_vacancy_as_trash).
    # В rerun-режиме ряд остаётся как ``status=NOT_FIT`` + ``skip_reason``
    # начинается с ``TRASH_SKIP_PREFIX`` — таких добавим к trash-счётчику ниже.
    # Not Fit (clean) — отсев фит-валидатором по языку/локации/уровню,
    # т.е. ``status=NOT_FIT`` БЕЗ trash-маркера в skip_reason.
    # Образец один на два условия: они обязаны быть отрицанием друг друга,
    # а набранные порознь разъехались бы молча. Пробел у метки в образец
    # не идёт — за ним следует сама причина.
    marked_trash = Vacancy.skip_reason.like(f"{TRASH_SKIP_PREFIX.rstrip()}%")
    is_rerun_trash = and_(
        Vacancy.status == VacancyStatus.NOT_FIT,
        marked_trash,
    )
    is_not_fit_clean = and_(
        Vacancy.status == VacancyStatus.NOT_FIT,
        or_(
            Vacancy.skip_reason.is_(None),
            ~marked_trash,
        ),
    )
    rows = (
        await session.execute(
            select(
                TelegramChannel.id,
                TelegramChannel.title,
                TelegramChannel.username,
                func.count(Vacancy.id).label("total"),
                func.sum(case((is_rerun_trash, 1), else_=0)).label("rerun_trash"),
                func.sum(case((is_not_fit_clean, 1), else_=0)).label("not_fit"),
            )
            .join(Vacancy, Vacancy.source_channel_id == TelegramChannel.id)
            .where(*base_filter)
            .group_by(TelegramChannel.id)
        )
    ).all()

    # Шаг 1b: trash-events за period (auto-ingest deletions). Per-channel
    # COUNT(*) по той же временной рамке, что и Vacancy.created_at.
    trash_event_filter = []
    if since is not None:
        trash_event_filter.append(TrashEvent.created_at >= since)
    trash_events_rows = (
        await session.execute(
            select(
                TrashEvent.source_channel_id,
                func.count(TrashEvent.id),
            )
            .where(*trash_event_filter)
            .group_by(TrashEvent.source_channel_id)
        )
    ).all()
    trash_events_by_ch: dict[int, int] = {}
    for ch_id, cnt in trash_events_rows:
        if ch_id is not None:
            trash_events_by_ch[ch_id] = int(cnt or 0)

    # Шаг 2: history-based «sent / answered / invite+ / decline» per channel.
    # Distinct vacancy_id, у которых ПЕРВЫЙ переход в нужный набор статусов
    # (min(changed_at)) попал в окно period. Привязка к самому факту
    # перехода, а не к Vacancy.created_at — чтобы funnel показывал именно
    # «прогресс за период», совпадая с верхним KPI-блоком.
    async def _first_in_period_by_channel(statuses) -> dict[int, set[int]]:
        sub = first_transition_subq(statuses)
        q = (
            select(Vacancy.source_channel_id, sub.c.vid)
            .join(sub, sub.c.vid == Vacancy.id)
            .where(PARSED_ONLY)
        )
        if since is not None:
            q = q.where(sub.c.first_at >= since)
        by_ch: dict[int, set[int]] = {}
        for ch_id, vid in (await session.execute(q)).all():
            if ch_id is None:
                continue
            by_ch.setdefault(ch_id, set()).add(vid)
        return by_ch

    sent_by_ch = await _first_in_period_by_channel(VacancyStatus.APPLIED)
    answered_by_ch = await _first_in_period_by_channel(RESPONDED)
    invite_by_ch = await _first_in_period_by_channel(INVITED)
    decline_by_ch = await _first_in_period_by_channel(VacancyStatus.DECLINE)

    # Сводим. Канал должен попасть в таблицу, если в окне периода у него
    # есть хоть что-то: Vacancy-ряды (ингест), TrashEvent (auto-deletions)
    # или funnel-активность (старая вакансия впервые перешла в нужный
    # статус внутри окна).
    items_by_ch: dict[int, dict] = {}
    for ch_id, title, username, total_vac, rerun_trash, not_fit in rows:
        items_by_ch[ch_id] = _channel_item(
            ch_id, title, username, (total_vac, rerun_trash, not_fit)
        )
    needed_ch_ids: set[int] = set()
    needed_ch_ids.update(trash_events_by_ch.keys())
    needed_ch_ids.update(sent_by_ch.keys())
    needed_ch_ids.update(answered_by_ch.keys())
    needed_ch_ids.update(invite_by_ch.keys())
    needed_ch_ids.update(decline_by_ch.keys())
    orphan_ids = [c for c in needed_ch_ids if c not in items_by_ch]
    if orphan_ids:
        orphan_rows = (
            await session.execute(
                select(TelegramChannel.id, TelegramChannel.title, TelegramChannel.username)
                .where(TelegramChannel.id.in_(orphan_ids))
            )
        ).all()
        for ch_id, title, username in orphan_rows:
            items_by_ch[ch_id] = _channel_item(ch_id, title, username)
    if not items_by_ch:
        return {"period": period, "channels": []}

    items = []
    for ch_id, item in items_by_ch.items():
        trash_events = trash_events_by_ch.get(ch_id, 0)
        # total = всё что канал «прислал» за period: Vacancy-ряды + trash_events
        # (auto-ingest deletions, которых уже нет в vacancy table)
        total = item["_total_vac"] + trash_events
        # Полный trash = удалённые auto-ingest + помеченные rerun
        trash = trash_events + item["_rerun_trash"]
        not_fit = item["not_fit"]
        fit = max(0, total - trash - not_fit)
        sent = len(sent_by_ch.get(ch_id, set()))
        answered = len(answered_by_ch.get(ch_id, set()))
        invite_plus = len(invite_by_ch.get(ch_id, set()))
        decline = len(decline_by_ch.get(ch_id, set()))
        conv_answ = (answered / sent * 100) if sent > 0 else None
        conv_invite = (invite_plus / sent * 100) if sent > 0 else None
        items.append({
            "id": ch_id,
            "label": item["label"],
            "total": total,
            "trash": trash,
            "not_fit": not_fit,
            "fit": fit,
            "sent": sent,
            "answered": answered,
            "invite_plus": invite_plus,
            "decline": decline,
            "conv_answ_sent": (round(conv_answ, 1) if conv_answ is not None else None),
            "conv_invite_sent": (round(conv_invite, 1) if conv_invite is not None else None),
        })
    items.sort(key=lambda it: (-it["total"], it["label"].casefold()))
    return {"period": period, "channels": items}
