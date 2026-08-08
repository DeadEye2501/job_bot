"""Ведение записей о телеграм-каналах."""

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import Blacklist, TelegramChannel, TrashEvent, Vacancy, VacancyStatus
from backend.payloads import ChannelDetail, ChannelStats, ChannelWithCount

logger = logging.getLogger(__name__)


# Voronka classification — derived once, reused by `get_channel_detail`:
# - `_FIT_EXCLUDE`: статусы, которые НЕ считаются подходящими — либо
#   валидатор отверг как Not Fit, либо это Scam (мы заведомо не будем
#   взаимодействовать с источником).
# - `_APPLIED`: что мы реально отправили, либо ответ уже пришёл / заглох.
#   New = подходит, но ещё не отправили.
# - `_RESPONDED`: получили ответ от работодателя (включая отказ — Decline
#   тоже ответ). Applied = ждём, Ghosting = тишина.
_FIT_EXCLUDE: frozenset[VacancyStatus] = frozenset({
    VacancyStatus.NOT_FIT, VacancyStatus.SCAM,
})
_APPLIED: frozenset[VacancyStatus] = frozenset({
    VacancyStatus.APPLIED,
    VacancyStatus.ANSWERED,
    VacancyStatus.TEST,
    VacancyStatus.INVITATION,
    VacancyStatus.IN_PROGRESS,
    VacancyStatus.OFFER,
    VacancyStatus.DECLINE,
    VacancyStatus.GHOSTING,
})
_RESPONDED: frozenset[VacancyStatus] = frozenset({
    VacancyStatus.ANSWERED,
    VacancyStatus.TEST,
    VacancyStatus.INVITATION,
    VacancyStatus.IN_PROGRESS,
    VacancyStatus.OFFER,
    VacancyStatus.DECLINE,
})


def channel_blacklist_candidates(ch: TelegramChannel) -> list[str]:
    """Возможные blacklist `value` строки для канала. Используется для
    case-insensitive lookup'а — username может быть mixed-case или нет.
    Сейчас возвращаем только @username; формат и регистр совпадает с
    тем, что пишет ``contacts_add_channel_to_blacklist`` slot.
    """
    if not ch.username:
        return []
    return [f"@{ch.username}"]


def channel_blacklist_preferred_value(ch: TelegramChannel) -> str | None:
    if not ch.username:
        return None
    return f"@{ch.username}"


async def _channel_blacklist_value(
    session: AsyncSession, ch: TelegramChannel
) -> str | None:
    """Если канал сейчас активно в blacklist'е, возвращаем точный
    `value` строки (для UI-чипа в detail-pane). None — если не в нём.
    """
    candidates = channel_blacklist_candidates(ch)
    if not candidates:
        return None
    row = (
        await session.scalars(
            select(Blacklist)
            .where(
                Blacklist.kind == "channel",
                Blacklist.value.in_(candidates),
                Blacklist.active.is_(True),
            )
            .order_by(Blacklist.id.asc())
            .limit(1)
        )
    ).first()
    return row.value if row is not None else None


async def list_telegram_channels(
    session: AsyncSession,
    search: str | None = None,
) -> list[ChannelWithCount]:
    """All Telegram channels with their vacancy count.

    Ordered: by vacancy_count desc (prolific channels rank higher), then
    title. is_active НЕ участвует в сортировке — иначе blacklisted каналы
    (forced is_active=false) сваливались бы в самый низ списка, чего юзер
    не просил.

    ``search`` is matched against title and ``@username`` Python-side via
    ``str.casefold()`` — Cyrillic safety, same as HR/Company lists.

    No pagination: channel lists are tiny (tens, not thousands).
    """
    # ``coalesce(title, username)`` для сортировки совпадает с тем, как UI
    # выбирает заголовок ряда (title если есть, иначе @username) — иначе
    # NULL-title каналы в SQLite ASC всплывают наверх и порядок ломается.
    title_or_username = func.coalesce(TelegramChannel.title, TelegramChannel.username)
    base = (
        select(TelegramChannel, func.count(Vacancy.id).label("cnt"))
        .outerjoin(Vacancy, Vacancy.source_channel_id == TelegramChannel.id)
        .group_by(TelegramChannel.id)
        .order_by(
            func.count(Vacancy.id).desc(),
            title_or_username.asc(),
        )
    )
    rows = (await session.execute(base)).all()

    if search:
        q = search.strip().casefold()
        if q:
            rows = [
                (ch, cnt) for ch, cnt in rows
                if q in (ch.title or "").casefold()
                or q in (ch.username or "").casefold()
            ]

    bl_values = set(
        (
            await session.scalars(
                select(Blacklist.value).where(
                    Blacklist.kind == "channel",
                    Blacklist.active.is_(True),
                )
            )
        ).all()
    )

    def _is_blacklisted(ch: TelegramChannel) -> bool:
        return any(c in bl_values for c in channel_blacklist_candidates(ch))

    return [
        ChannelWithCount(
            channel=ch,
            vacancy_count=int(cnt or 0),
            is_blacklisted=_is_blacklisted(ch),
        )
        for ch, cnt in rows
    ]


_CHANNEL_RATE_WINDOW_DAYS = 30


def _percent_or_none(numerator: int, denominator: int) -> int | None:
    if denominator <= 0:
        return None
    return int(round(numerator / denominator * 100))


async def get_channel_detail(
    session: AsyncSession, channel_id: int
) -> ChannelDetail | None:
    """Detail-pane payload: the channel itself + computed stats.

    Two queries: one for the channel row, one GROUP BY status to compute
    counts. Per-day rate is a separate windowed COUNT(*) over the last
    30 days. KPI ratios come from the lifetime status_counts.
    """
    ch = await session.get(TelegramChannel, channel_id)
    if ch is None:
        return None

    rows = (
        await session.execute(
            select(Vacancy.status, func.count(Vacancy.id))
            .where(Vacancy.source_channel_id == channel_id)
            .group_by(Vacancy.status)
        )
    ).all()

    counts_by_enum: dict[VacancyStatus, int] = {}
    for status_enum, cnt in rows:
        counts_by_enum[status_enum] = int(cnt or 0)

    total = sum(counts_by_enum.values())
    fit_total = sum(
        n for s, n in counts_by_enum.items() if s not in _FIT_EXCLUDE
    )
    applied_total = sum(
        n for s, n in counts_by_enum.items() if s in _APPLIED
    )
    responded_total = sum(
        n for s, n in counts_by_enum.items() if s in _RESPONDED
    )

    since = datetime.now(timezone.utc) - timedelta(days=_CHANNEL_RATE_WINDOW_DAYS)
    recent_count = int(
        (
            await session.execute(
                select(func.count(Vacancy.id))
                .where(
                    Vacancy.source_channel_id == channel_id,
                    Vacancy.created_at >= since,
                )
            )
        ).scalar_one()
    )
    vacancies_per_day = round(recent_count / _CHANNEL_RATE_WINDOW_DAYS, 1)

    status_counts = {
        status.value: counts_by_enum.get(status, 0) for status in VacancyStatus
    }

    blacklist_value = await _channel_blacklist_value(session, ch)

    return ChannelDetail(
        channel=ch,
        stats=ChannelStats(
            status_counts=status_counts,
            total=total,
            vacancies_per_day=vacancies_per_day,
            fit_percent=_percent_or_none(fit_total, total),
            apply_percent=_percent_or_none(applied_total, fit_total),
            response_percent=_percent_or_none(responded_total, applied_total),
        ),
        blacklist_value=blacklist_value,
    )


async def find_channel_by_username(
    session: AsyncSession, username: str
) -> TelegramChannel | None:
    """Locate an existing channel by @username, case-insensitive.

    Telegram treats usernames as case-insensitive — `@MyChan` and `@mychan`
    refer to the same channel. Existing rows in the DB могут быть с
    разным регистром (исторически сидились через сырой SQL), поэтому
    сравниваем через ``LOWER()``.
    """
    return (
        await session.scalars(
            select(TelegramChannel).where(
                func.lower(TelegramChannel.username) == username.lower()
            )
        )
    ).first()


async def set_channel_active(
    session: AsyncSession, channel_id: int, is_active: bool
) -> bool:
    """Toggle TelegramChannel.is_active. Returns False if the row is missing.

    Caller wraps in ``session.begin()``; only a single row mutation here so
    no extra invariants to enforce.
    """
    ch = await session.get(TelegramChannel, channel_id)
    if ch is None:
        return False
    prev = ch.is_active
    ch.is_active = bool(is_active)
    if prev != ch.is_active:
        logger.info(
            "Channel %d (@%s) is_active %s -> %s",
            channel_id,
            ch.username,
            prev,
            ch.is_active,
        )
    return True


async def deactivate_blacklisted_channels(session: AsyncSession) -> int:
    """Set is_active=False для всех каналов, чьи blacklist-кандидаты
    совпадают с активной строкой kind=channel. Idempotent: уже-выключенные
    не трогаем. Returns count flipped — для логов/тостов.

    Зеркалит matching-логику ``list_telegram_channels._is_blacklisted``
    (exact match, case-sensitive). Caller wraps в ``session.begin()``.
    """
    bl_values = set(
        (
            await session.scalars(
                select(Blacklist.value).where(
                    Blacklist.kind == "channel",
                    Blacklist.active.is_(True),
                )
            )
        ).all()
    )
    if not bl_values:
        return 0
    channels = (
        await session.scalars(
            select(TelegramChannel).where(TelegramChannel.is_active.is_(True))
        )
    ).all()
    flipped = 0
    for ch in channels:
        if any(c in bl_values for c in channel_blacklist_candidates(ch)):
            ch.is_active = False
            flipped += 1
    if flipped:
        logger.info("Deactivated %d channel(s) by blacklist", flipped)
    return flipped


async def is_channel_blacklisted(
    session: AsyncSession, channel_id: int
) -> bool:
    """True если в blacklist'е активна строка kind=channel, value которой
    совпадает с одним из blacklist-кандидатов канала. Используется в
    set_channel_active для отказа re-enable'а.
    """
    ch = await session.get(TelegramChannel, channel_id)
    if ch is None:
        return False
    return await _channel_blacklist_value(session, ch) is not None


async def set_all_channels_active(
    session: AsyncSession, is_active: bool
) -> int:
    """Bulk-flip every TelegramChannel.is_active to the same value.
    Returns row count for the toast. Caller wraps in ``session.begin()``.

    При is_active=True пропускаем каналы, попавшие в blacklist — их
    нельзя включить никаким образом, в т.ч. через «Включить все».
    """
    stmt = update(TelegramChannel).values(is_active=bool(is_active))
    if is_active:
        bl_values = list(
            (
                await session.scalars(
                    select(Blacklist.value).where(
                        Blacklist.kind == "channel",
                        Blacklist.active.is_(True),
                    )
                )
            ).all()
        )
        if bl_values:
            # Совпадение по `@username` — то же exact-match, что в
            # `channel_blacklist_candidates`.
            stripped = [v.lstrip("@") for v in bl_values]
            stmt = stmt.where(TelegramChannel.username.notin_(stripped))
    result = await session.execute(stmt)
    affected = int(result.rowcount or 0)
    logger.info(
        "Bulk channel toggle is_active=%s, affected=%d",
        bool(is_active),
        affected,
    )
    return affected


async def reset_channel_cursor(session: AsyncSession, channel_id: int) -> bool:
    """Clear ``last_processed_msg_id`` so the next poll re-pulls recent
    history. Returns False if the row is missing.
    """
    ch = await session.get(TelegramChannel, channel_id)
    if ch is None:
        return False
    ch.last_processed_msg_id = None
    return True


async def delete_channel(
    session: AsyncSession, channel_id: int
) -> int | None:
    """Delete a channel. Severs the FK on existing vacancies (sets
    ``source_channel_id = NULL``) so we don't lose forensic data — the
    raw_text + LLM-parsed fields stay searchable, just without the
    channel link. Returns the count of detached vacancies, or None if
    the channel didn't exist.
    """
    ch = await session.get(TelegramChannel, channel_id)
    if ch is None:
        return None
    ch_username = ch.username
    detached = (
        await session.execute(
            update(Vacancy)
            .where(Vacancy.source_channel_id == channel_id)
            .values(source_channel_id=None)
        )
    ).rowcount
    # TrashEvent держит ondelete=SET NULL — PRAGMA foreign_keys=ON
    # (adapters/db.py) сделает это автоматически при session.delete(ch).
    # Дублирующий UPDATE — defense-in-depth: если FK по какой-то причине
    # disabled (dev sqlite3 CLI / отсутствие listener'а), события не
    # останутся «висячими» с указателем на удалённый канал.
    detached_trash = (
        await session.execute(
            update(TrashEvent)
            .where(TrashEvent.source_channel_id == channel_id)
            .values(source_channel_id=None)
        )
    ).rowcount
    await session.delete(ch)
    detached_n = int(detached or 0)
    detached_trash_n = int(detached_trash or 0)
    logger.info(
        "Deleted channel %d (@%s), detached %d vacancies, %d trash events",
        channel_id,
        ch_username,
        detached_n,
        detached_trash_n,
    )
    return detached_n
