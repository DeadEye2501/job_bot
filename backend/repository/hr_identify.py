"""Соответствие записи HR данным Telegram."""

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import HR, Message, Vacancy

logger = logging.getLogger(__name__)


HAS_TELEGRAM_IDENTITY = or_(
    HR.telegram_user_id.is_not(None), HR.telegram_username.is_not(None)
)
"""Отбор «человека есть чем опознать в Telegram»: номер учётной записи либо ник.

Одно объявление на двоих — догон переписки и подсказки чёрного списка, — потому
что согласны они сегодня лишь тем, что никто не забыл вторую половину «или».
Что расхождение здесь достижимо, видно по `hr_list.list_open_hr_chats`: тот
сужен до одного номера учётной записи нарочно, и правило отбора людей в проекте
уже не одно.
"""


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

    Ник в Telegram свободно достаётся другому человеку, поэтому запись с
    чужим идентификатором под тем же ником принадлежит не отправителю.
    Оговорка «либо идентификатор равен искомому» не написана нарочно: своя
    запись до запасного пути не доходит, её отдаёт поиск по идентификатору.
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
                select(HR).where(
                    HR.telegram_username == telegram_username,
                    HR.telegram_user_id.is_(None),
                )
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
    window_days: int,
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


def telegram_full_name(user) -> str | None:
    """Имя собеседника, собранное из имени и фамилии Telegram."""
    return " ".join(filter(None, [user.first_name, user.last_name])).strip() or None


def refresh_hr_from_telegram(hr: HR, user, *, avatar: bytes | None) -> None:
    """Дополнить найденную запись тем, что пришло от Telegram.

    Номер собеседника узнаётся только с первым его письмом: карточку
    заводят одним ником из окна «Контакты», и пока номера нет, поиск идёт
    запасным путём. Проставленный, он переводит все следующие поиски на
    прямое попадание.

    Заполняется только пустое: записанное имя и картинку правят руками в
    окне, и написанное там точнее того, как собеседник назвался сам. Ник —
    наоборот: он не наш, а его, и сменившийся подхватывается.

    **Пустота не удерживается:** очистка поля в окне тоже пустота, и
    следующее же входящее письмо впишет туда имя из Telegram. Отличить «не
    было никогда» от «стёрли нарочно» нечем — для этого нужна ещё колонка.

    Картинка держится того же правила намеренно: обновляй её каждый раз, и
    свежая заменялась бы устаревшей с любого запоздавшего пути. Цена
    известна: сменивший фотографию собеседник остаётся со старой, пока
    колонку не очистят руками.
    """
    if hr.telegram_user_id is None:
        hr.telegram_user_id = user.id
    if user.username and hr.telegram_username != user.username:
        hr.telegram_username = user.username
    full_name = telegram_full_name(user)
    if not hr.name and full_name:
        hr.name = full_name
    if avatar is not None and hr.avatar is None:
        hr.avatar = avatar


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

    Единственное место, где заводится строка собеседника: и по кнопке из
    окна, и опознанием автора вакансии в `find_or_create_hr`. Картинка
    профиля довода не получила нарочно: приносит её только второй путь, и
    дописывает он её сам, сразу за заведением, — у новой строки перебивать
    нечего, поэтому оговорок `refresh_hr_from_telegram` ей не нужно.
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
        "Created HR id=%d name=%r username=%s telegram_user_id=%s",
        hr.id,
        name,
        telegram_username,
        telegram_user_id,
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
    hr = await find_known_hr(session, user.id, user.username)

    if hr is None:
        hr = await create_hr(
            session,
            name=telegram_full_name(user),
            telegram_username=user.username,
            telegram_user_id=user.id,
        )
        hr.avatar = avatar
        return hr, True

    refresh_hr_from_telegram(hr, user, avatar=avatar)
    return hr, False
