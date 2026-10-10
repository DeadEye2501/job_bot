"""Ведение записей о телеграм-каналах."""

import logging

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import TelegramChannel, TrashEvent, Vacancy
from backend.payloads import ChannelDetail, ChannelWithCount

from backend.models.settings import CHANNEL_KIND
from backend.repository.blacklist_marks import BlacklistMark
from backend.repository.search import matches_search
from backend.repository.source_stats import source_stats
from backend.repository.vacancies_common import with_vacancy_counts
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


CHANNEL_BLACKLIST = BlacklistMark(CHANNEL_KIND, channel_blacklist_candidates)


def _channels_with_counts_query():
    """Каналы со счётчиком разобранных вакансий, плодовитые сверху.

    ``coalesce(title, username)`` для сортировки совпадает с тем, как UI
    выбирает заголовок ряда (title если есть, иначе @username) — иначе
    NULL-title каналы в SQLite ASC всплывают наверх и порядок ломается.

    Как устроен сам счёт и почему отбор стоит в условии присоединения —
    сказано там, где живёт запрос (`vacancies_common.with_vacancy_counts`).
    """
    title_or_username = func.coalesce(
        TelegramChannel.title, TelegramChannel.username
    )
    return with_vacancy_counts(
        TelegramChannel, Vacancy.source_channel_id, title_or_username
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

    bl_values = await CHANNEL_BLACKLIST.marked(session)

    return [
        ChannelWithCount(
            channel=ch,
            vacancy_count=int(cnt or 0),
            is_blacklisted=CHANNEL_BLACKLIST.among(ch, bl_values),
        )
        for ch, cnt in rows
    ]


async def get_channel_detail(
    session: AsyncSession, channel_id: int
) -> ChannelDetail | None:
    """Detail-pane payload: the channel itself + computed stats.

    Запросов четыре: сама строка канала, разбивка по статусам одной
    группировкой, окно темпа (:func:`source_stats.source_stats`) и отметка
    чёрного списка.
    """
    ch = await session.get(TelegramChannel, channel_id)
    if ch is None:
        return None
    stats = await source_stats(session, Vacancy.source_channel_id == channel_id)
    return ChannelDetail(
        channel=ch,
        stats=stats,
        blacklist_value=await CHANNEL_BLACKLIST.value(session, ch),
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
    """Выключить каналы под действующей отметкой; сколько выключено — для журнала.

    Правило общее с агрегаторами (`BlacklistMark.switch_off`); своё здесь —
    только запись в журнал. Caller wraps в ``session.begin()``.
    """
    flipped = await CHANNEL_BLACKLIST.switch_off(session, TelegramChannel)
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
    return await CHANNEL_BLACKLIST.value(session, ch) is not None


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
