"""Сопоставление входящего сообщения с записью HR."""

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import HR, Message, Vacancy

logger = logging.getLogger(__name__)


async def find_known_hr(
    session: AsyncSession,
    telegram_user_id: int,
    telegram_username: str | None = None,
) -> HR | None:
    """Look up an HR by telegram user_id, fall back to @username.

    The fallback handles HRs created from the Contacts/HR pane via username
    only — when their first incoming DM arrives we now know their user_id
    via the Pyrogram payload, but the row still has user_id NULL. Caller
    is responsible for backfilling ``hr.telegram_user_id`` after a username
    match so subsequent lookups hit the fast path.
    """
    hr = (
        await session.scalars(
            select(HR).where(HR.telegram_user_id == telegram_user_id)
        )
    ).first()
    if hr is not None:
        return hr
    if telegram_username:
        hr = (
            await session.scalars(
                select(HR).where(HR.telegram_username == telegram_username)
            )
        ).first()
    return hr


async def find_latest_vacancy_id_for_hr(
    session: AsyncSession,
    hr_id: int,
    *,
    as_of: datetime | None = None,
) -> int | None:
    """Самая свежая вакансия, привязанная к HR — по posted_at (с fallback на
    created_at, когда posted_at null'нут). Используется для атрибуции HR-
    ответов: если HR пишет нам, считаем что он реагирует на самую свежую
    из его вакансий, независимо от того, отправляли ли мы ему отклик через
    бот (юзер мог написать с телефона/из десктопа).

    ``as_of`` — таймстемп сообщения HR'а. Вакансии, появившиеся ПОЗЖЕ него,
    отбрасываются: иначе старое сообщение из catch-up может «откатить
    статус» только-что добавленной вакансии (time-travel). Также берутся
    только полностью распаршенные вакансии (``is_parsed=True``), чтобы
    DM в parse-window не флипнул статус ещё не готовой строки.

    Clock-skew nuance: ``as_of`` приходит от Telegram (msg.date), а
    ``Vacancy.created_at`` пишется локальным ``func.now()``. Если часы
    клиента опаздывают относительно Telegram-серверного времени, существует
    тонкий race с auto-send'ом, который committs и сразу шлёт DM — но в
    single-user setup (Pyrogram-сессия привязана к ОС-времени) клиентское
    время и Telegram-серверное обычно синкаются NTP-сервисом, окно
    рассогласования = единицы секунд. Документировано вместо переключения
    ``created_at`` на ``msg.date`` исходного поста (которое потребовало
    бы тащить msg-time через 5 слоёв ingestion'а).
    """
    stmt = (
        select(Vacancy)
        .where(Vacancy.hr_id == hr_id, Vacancy.is_parsed.is_(True))
        .order_by(
            func.coalesce(Vacancy.posted_at, Vacancy.created_at).desc(),
            Vacancy.id.desc(),
        )
        .limit(1)
    )
    if as_of is not None:
        stmt = stmt.where(
            func.coalesce(Vacancy.posted_at, Vacancy.created_at) <= as_of
        )
    latest = (await session.scalars(stmt)).first()
    return latest.id if latest else None


async def count_recent_outgoing_with_vacancy_for_hr(
    session: AsyncSession,
    hr_id: int,
    *,
    window_days: int = 14,
) -> int:
    """Сколько cover-letter'ов мы отправили этому HR'у за последние
    ``window_days`` дней. Считаются только outgoing rows с привязанным
    ``vacancy_id`` — ручные сообщения из чата Contacts (без vacancy_id)
    игнорируются. Подписан на 0 при отсутствии истории.

    Используется в auto / manual send-ветке для решения «полный cover
    letter + CV (count==0) vs short follow-up без вложений (count>=1)».
    Cutoff считаем в Python, чтобы не зависеть от диалекта date-arithmetic.

    SEND_LOCKED dev-режим Message-rows не пишет → в dev-сценариях count
    всегда 0, что и нужно: dev тестирует full-cover-letter путь.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=window_days)
    stmt = select(func.count(Message.id)).where(
        Message.hr_id == hr_id,
        ~Message.is_incoming,
        Message.vacancy_id.is_not(None),
        Message.sent_at >= cutoff,
    )
    return (await session.scalar(stmt)) or 0


async def resolve_reply_target_vacancy(
    session: AsyncSession,
    hr_id: int,
    reply_to_tg_msg_id: int,
) -> int | None:
    """Найти vacancy_id нашего outgoing-сообщения, на которое HR ответил
    через Telegram-reply (`reply_to_message_id`). Возвращает ``None``
    если процитированное сообщение не наше / не найдено / без vacancy_id
    (ручная переписка из Contacts).

    Уникальность гарантирует UniqueConstraint
    ``(hr_id, tg_message_id, is_incoming)`` — outgoing-row с заданным
    tg_message_id для HR'а ровно одна.
    """
    stmt = (
        select(Message.vacancy_id)
        .where(
            Message.hr_id == hr_id,
            ~Message.is_incoming,
            Message.tg_message_id == reply_to_tg_msg_id,
        )
        .limit(1)
    )
    return await session.scalar(stmt)


def refresh_hr_username(hr: HR, sender_username: str | None) -> None:
    if sender_username and hr.telegram_username != sender_username:
        hr.telegram_username = sender_username


async def create_hr(
    session: AsyncSession,
    *,
    name: str | None,
    telegram_username: str | None,
    telegram_user_id: int | None = None,
    notes: str | None = None,
) -> HR:
    """Insert a new HR row. Caller wraps in ``session.begin()``.

    No deduping by username — the UI's HR-picker already shows existing
    HRs and the user has to explicitly click "Создать нового HR". If they
    chose to create rather than link, we trust that.
    """
    hr = HR(
        name=(name or None),
        telegram_username=(telegram_username or None),
        telegram_user_id=telegram_user_id,
        notes=(notes or None),
    )
    session.add(hr)
    await session.flush()
    logger.info(
        "Created HR id=%d name=%r username=%s",
        hr.id,
        name,
        telegram_username,
    )
    return hr


async def find_or_create_hr(
    session: AsyncSession, user, *, avatar: bytes | None = None
) -> tuple[HR, bool]:
    """Return (hr, created). ``created=True`` ⇒ row только что вставлен —
    caller (vacancy parse path: основная ветка с автоотправкой и NotFit-
    save) использует это, чтобы запустить per-HR backfill DM-истории.
    Catch-up для всех HR'ов крутится только на OFF→active transition;
    новый HR, созданный в активном режиме, без этого хука остался бы с
    пустым чатом до рестарта."""
    hr = (
        await session.scalars(
            select(HR).where(HR.telegram_user_id == user.id)
        )
    ).first()
    if hr is None and user.username:
        hr = (
            await session.scalars(
                select(HR).where(
                    HR.telegram_username == user.username,
                    HR.telegram_user_id.is_(None),
                )
            )
        ).first()

    full_name = " ".join(
        filter(None, [user.first_name, user.last_name])
    ).strip() or None

    if hr is None:
        hr = HR(
            telegram_user_id=user.id,
            telegram_username=user.username,
            name=full_name,
            avatar=avatar,
        )
        session.add(hr)
        await session.flush()
        logger.info(
            "Created HR id=%d telegram_user_id=%s username=%s name=%r",
            hr.id,
            user.id,
            user.username,
            full_name,
        )
        return hr, True

    if hr.telegram_user_id is None:
        hr.telegram_user_id = user.id
    if user.username and hr.telegram_username != user.username:
        hr.telegram_username = user.username
    if not hr.name and full_name:
        hr.name = full_name
    # Backfill only when empty — keeps a freshly-fetched photo from being
    # overwritten by a stale fetch on a later flow. Trade-off: if the HR
    # changes their Telegram photo, the bot keeps the old one until the
    # column is manually cleared.
    if avatar is not None and hr.avatar is None:
        hr.avatar = avatar
    return hr, False
