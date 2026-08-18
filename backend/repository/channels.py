"""Ведение записей о телеграм-каналах."""

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.domain.funnel import APPLIED, FIT_EXCLUDE, RESPONDED, percent_or_none
from backend.models import TelegramChannel, TrashEvent, Vacancy
from backend.payloads import ChannelDetail, ChannelStats, ChannelWithCount

from backend.repository.blacklist_marks import (
    active_blacklist_value,
    preferred_blacklist_value,
    active_blacklist_values,
)
from backend.repository.search import matches_search
from backend.repository.vacancies_common import PARSED_ONLY, count_by_status
from backend.repository.vacancies_life import repoint_vacancies

logger = logging.getLogger(__name__)


async def list_named_channels(
    session: AsyncSession, *, ids: list[int] | None = None
) -> list[TelegramChannel]:
    """Каналы, у которых есть ник, — все или только названные номерами.

    Ник — единственный адрес, по которому канал спрашивают у Telegram, и
    пустая строка адресом не является. Отсеивается она наравне с
    отсутствующей: колонка объявлена обнуляемой, а строки заводились и сырым
    SQL мимо `create_channel` — об этом говорит докстрока
    `find_channel_by_username`.

    Одно объявление на всех, потому что зовущих пятеро — обход, прогон
    одного канала, сводка по номерам, повторный разбор вакансии и подсказки
    чёрного списка, — и разойдись они, канал без адреса доехал бы до
    обращения одной из дорог.
    """
    query = select(TelegramChannel).where(
        TelegramChannel.username.is_not(None),
        TelegramChannel.username != "",
    )
    if ids is not None:
        query = query.where(TelegramChannel.id.in_(ids))
    return list((await session.scalars(query)).all())


def channel_blacklist_candidates(ch: TelegramChannel) -> list[str]:
    """Написания, под которыми канал может стоять в чёрном списке.

    Написание одно — `@ник`, — а объявление всё равно отдаёт список: под тем
    же договором живут написания HR и компании, и отметку по ним ищет один
    перебор в `blacklist_marks`.

    Регистр не приводится: то же написание пишет и кнопка «в чёрный список»
    — она берёт из этого перечня первое (`preferred_blacklist_value`), то
    есть написание у отметки и у поиска отметки одно.
    """
    if not ch.username:
        return []
    return [f"@{ch.username}"]


def channel_blacklist_preferred_value(ch: TelegramChannel) -> str | None:
    return preferred_blacklist_value(channel_blacklist_candidates(ch))


def _is_blacklisted(ch: TelegramChannel, bl_values: set[str]) -> bool:
    """Отмечен ли канал одной из активных строк, прочитанных заранее.

    Отдельное объявление, потому что зовущих трое — перечень, разовый проход
    и сплошное включение, — и разойдись они, канал считался бы отмеченным на
    одном экране и чистым на другом.
    """
    return any(c in bl_values for c in channel_blacklist_candidates(ch))


async def _channel_blacklist_value(
    session: AsyncSession, ch: TelegramChannel
) -> str | None:
    """Если канал сейчас активно в blacklist'е, возвращаем точный
    `value` строки (для UI-чипа в detail-pane). None — если не в нём.
    """
    return await active_blacklist_value(
        session, "channel", channel_blacklist_candidates(ch)
    )


def _channels_with_counts_query():
    """Каналы со счётчиком разобранных вакансий, плодовитые сверху.

    ``coalesce(title, username)`` для сортировки совпадает с тем, как UI
    выбирает заголовок ряда (title если есть, иначе @username) — иначе
    NULL-title каналы в SQLite ASC всплывают наверх и порядок ломается.

    Отбор стоит в условии присоединения, а не в ``where``: в ``where`` он
    отбросил бы канал без единой разобранной вакансии целиком, а тот обязан
    остаться в списке с нулём.
    """
    title_or_username = func.coalesce(
        TelegramChannel.title, TelegramChannel.username
    )
    return (
        select(TelegramChannel, func.count(Vacancy.id).label("cnt"))
        .outerjoin(
            Vacancy,
            and_(Vacancy.source_channel_id == TelegramChannel.id, PARSED_ONLY),
        )
        .group_by(TelegramChannel.id)
        .order_by(
            func.count(Vacancy.id).desc(),
            title_or_username.asc(),
        )
    )


async def list_telegram_channels(
    session: AsyncSession,
    search: str | None = None,
) -> list[ChannelWithCount]:
    """All Telegram channels with their vacancy count.

    Ordered: by vacancy_count desc (prolific channels rank higher), then
    title. is_active НЕ участвует в сортировке — иначе blacklisted каналы
    (forced is_active=false) сваливались бы в самый низ списка, чего юзер
    не просил.

    ``search`` is matched against title and ``username`` (stored without the
    leading ``@``) Python-side — see
    :func:`backend.repository.search.matches_search`.

    No pagination: channel lists are tiny (tens, not thousands).
    """
    rows = (await session.execute(_channels_with_counts_query())).all()
    rows = [
        (ch, cnt) for ch, cnt in rows if matches_search(search, ch.title, ch.username)
    ]

    bl_values = await active_blacklist_values(session, "channel")

    return [
        ChannelWithCount(
            channel=ch,
            vacancy_count=int(cnt or 0),
            is_blacklisted=_is_blacklisted(ch, bl_values),
        )
        for ch, cnt in rows
    ]


_CHANNEL_RATE_WINDOW_DAYS = 30


async def _vacancies_per_day(session: AsyncSession, channel_id: int) -> float:
    """Сколько разобранных вакансий в день канал приносит в последнем окне.

    Окно своё, а не «за всё время»: канал, замолчавший полгода назад,
    иначе выглядел бы таким же живым, как вчерашний.
    """
    since = datetime.now(timezone.utc) - timedelta(days=_CHANNEL_RATE_WINDOW_DAYS)
    recent_count = int(
        (
            await session.execute(
                select(func.count(Vacancy.id))
                .where(
                    Vacancy.source_channel_id == channel_id,
                    Vacancy.created_at >= since,
                    PARSED_ONLY,
                )
            )
        ).scalar_one()
    )
    return round(recent_count / _CHANNEL_RATE_WINDOW_DAYS, 1)


async def _channel_stats(
    session: AsyncSession, channel_id: int, counts_by_enum: dict
) -> ChannelStats:
    """Числа карточки канала: разбивка по статусам, темп и три доли.

    Доли считаются одна от другой, ступенями воронки: годные от всех,
    отклики от годных, ответы от откликов — каждая отвечает на свой вопрос
    о канале, и общий знаменатель смазал бы все три. Считаются они за всё
    время, а темп — за окно: доли говорят, каков канал вообще, темп — жив
    ли он сейчас.
    """
    per_day = await _vacancies_per_day(session, channel_id)
    total = sum(counts_by_enum.values())
    fit_total = sum(
        n for s, n in counts_by_enum.items() if s not in FIT_EXCLUDE
    )
    applied_total = sum(
        n for s, n in counts_by_enum.items() if s in APPLIED
    )
    responded_total = sum(
        n for s, n in counts_by_enum.items() if s in RESPONDED
    )
    return ChannelStats(
        status_counts={
            status.value: count for status, count in counts_by_enum.items()
        },
        total=total,
        vacancies_per_day=per_day,
        fit_percent=percent_or_none(fit_total, total),
        apply_percent=percent_or_none(applied_total, fit_total),
        response_percent=percent_or_none(responded_total, applied_total),
    )


async def get_channel_detail(
    session: AsyncSession, channel_id: int
) -> ChannelDetail | None:
    """Detail-pane payload: the channel itself + computed stats.

    Запросов четыре: сама строка канала, разбивка по статусам одной
    группировкой, окно темпа (:func:`_channel_stats`) и отметка чёрного
    списка.
    """
    ch = await session.get(TelegramChannel, channel_id)
    if ch is None:
        return None
    counts_by_enum = await count_by_status(
        session, Vacancy.source_channel_id == channel_id, PARSED_ONLY
    )
    stats = await _channel_stats(session, channel_id, counts_by_enum)
    return ChannelDetail(
        channel=ch,
        stats=stats,
        blacklist_value=await _channel_blacklist_value(session, ch),
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


async def create_channel(
    session: AsyncSession, username: str, title: str | None, avatar: bytes | None
) -> int:
    """Завести канал-источник и отдать его номер.

    Ник приводится к нижнему регистру: Telegram на регистр не смотрит, а
    колонка смотрит — иначе «PyJobs» и «pyjobs» лягут двумя каналами, и
    поиск по нику найдёт то один, то другой.

    Транзакцию закрывает зовущий.
    """
    channel = TelegramChannel(
        username=username.lower(),
        title=title,
        is_active=True,
        avatar=avatar,
    )
    session.add(channel)
    await session.flush()
    return channel.id


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

    Отметку читает ``_is_blacklisted`` — то же правило, что у перечня и у
    сплошного включения. Caller wraps в ``session.begin()``.
    """
    bl_values = await active_blacklist_values(session, "channel")
    if not bl_values:
        return 0
    channels = (
        await session.scalars(
            select(TelegramChannel).where(TelegramChannel.is_active.is_(True))
        )
    ).all()
    flipped = 0
    for ch in channels:
        if _is_blacklisted(ch, bl_values):
            ch.is_active = False
            flipped += 1
    if flipped:
        logger.info("Deactivated %d channel(s) by blacklist", flipped)
    return flipped


async def is_channel_blacklisted(
    session: AsyncSession, channel_id: int
) -> bool:
    """True если в blacklist'е активна строка kind=channel, value которой
    совпадает с одним из blacklist-кандидатов канала.

    Зовут двое: мост — чтобы отказать во включении отсеянного канала, и ручной
    прогон одного канала (`flows/channels.poll_one_channel`) — чтобы не тащить
    из него вакансии в обход отметки.
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
        bl_values = await active_blacklist_values(session, "channel")
        if bl_values:
            # Отмеченные отбираются тем же правилом, что и везде, а не
            # обратным предикатом по SQL: перечень каналов невелик (десятки),
            # и лишний проход по нему дешевле второго написания правила.
            channels = (await session.scalars(select(TelegramChannel))).all()
            marked = [ch.id for ch in channels if _is_blacklisted(ch, bl_values)]
            if marked:
                stmt = stmt.where(TelegramChannel.id.notin_(marked))
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
    detached = await repoint_vacancies(
        session, Vacancy.source_channel_id, absorbed_id=channel_id, survivor_id=None
    )
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
