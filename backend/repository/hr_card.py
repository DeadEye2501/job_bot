"""Одна запись HR: чтение, правка, слияние, удаление."""

import logging

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import Company, HR, Message, Vacancy
from backend.payloads import HrDetail

from backend.repository.blacklist_marks import (
    active_blacklist_value,
    preferred_blacklist_value,
)
from backend.repository.merging import (
    concat_notes,
    load_merge_pair,
    repoint_vacancies,
)
from backend.repository.messages import UNREAD_INCOMING

logger = logging.getLogger(__name__)


_HR_FIELD_UNSET = object()


async def update_hr_fields(
    session: AsyncSession,
    hr_id: int,
    *,
    name=_HR_FIELD_UNSET,
    telegram_username=_HR_FIELD_UNSET,
    notes=_HR_FIELD_UNSET,
) -> bool:
    """Update one or more HR columns. Caller wraps in ``session.begin()``.

    Sentinel ``_HR_FIELD_UNSET`` distinguishes "don't touch" from "set to
    NULL", so a single call can patch any subset of columns. Empty strings
    collapse to NULL — the schema treats absence and empty equivalently.
    """
    hr = await session.get(HR, hr_id)
    if hr is None:
        return False
    changed = []
    if name is not _HR_FIELD_UNSET:
        hr.name = (str(name).strip() or None) if name is not None else None
        changed.append("name")
    if telegram_username is not _HR_FIELD_UNSET:
        if telegram_username is None:
            hr.telegram_username = None
        else:
            cleaned = str(telegram_username).strip()
            if cleaned.startswith("@"):
                cleaned = cleaned[1:].strip()
            hr.telegram_username = cleaned or None
        changed.append("telegram_username")
    if notes is not _HR_FIELD_UNSET:
        hr.notes = (str(notes).strip() or None) if notes is not None else None
        changed.append("notes")
    await session.flush()
    if changed:
        logger.debug("Updated HR %d fields=%s", hr_id, changed)
    return True


async def get_hr_detail(
    session: AsyncSession, hr_id: int
) -> HrDetail | None:
    """Detail payload for the Contacts / HR pane (05).

    Returns the HR row + most-recent linked company (id + name, by
    ``vacancy.created_at desc``) + total vacancy count + count of unread
    incoming messages. Returns ``None`` if the HR row is gone.
    """
    hr = await session.get(HR, hr_id)
    if hr is None:
        return None

    vacancy_count = int(
        await session.scalar(
            select(func.count(Vacancy.id)).where(Vacancy.hr_id == hr_id)
        )
        or 0
    )

    last_co_row = (
        await session.execute(
            select(Company.id, Company.name)
            .join(Vacancy, Vacancy.company_id == Company.id)
            .where(Vacancy.hr_id == hr_id)
            .order_by(Vacancy.created_at.desc(), Vacancy.id.desc())
            .limit(1)
        )
    ).first()
    last_company_id = last_co_row[0] if last_co_row else None
    last_company_name = last_co_row[1] if last_co_row else None

    unread_count = int(
        await session.scalar(
            select(func.count(Message.id)).where(
                Message.hr_id == hr_id,
                *UNREAD_INCOMING,
            )
        )
        or 0
    )

    blacklist_value = await _hr_blacklist_value(session, hr)

    return HrDetail(
        hr=hr,
        vacancy_count=vacancy_count,
        last_company_id=last_company_id,
        last_company_name=last_company_name,
        unread_count=unread_count,
        blacklist_value=blacklist_value,
    )


def hr_blacklist_candidates(hr: HR) -> list[str]:
    """Possible blacklist `value` strings for this HR — same format the
    `contacts_add_hr_to_blacklist` slot writes. Both forms are checked so
    a row added under one identifier (username) still surfaces if the HR
    later only has the other (user_id), or vice versa.
    
    Порядок значим: первое написание — то, что запишет кнопка
    «в чёрный список» (см. `preferred_blacklist_value`).
    """
    out: list[str] = []
    if hr.telegram_username:
        out.append(f"@{hr.telegram_username}")
    if hr.telegram_user_id is not None:
        out.append(f"user_id:{hr.telegram_user_id}")
    return out


async def _hr_blacklist_value(session: AsyncSession, hr: HR) -> str | None:
    return await active_blacklist_value(session, "hr", hr_blacklist_candidates(hr))


async def delete_hr(session: AsyncSession, hr_id: int) -> bool:
    """Cascade-delete the HR row. Caller commits.

    Messages are removed (chat history is meaningless without the HR);
    vacancies survive with ``hr_id`` set to NULL — they're intrinsic to
    their source channel, not to who messaged us about them. Returns
    ``True`` if the HR existed and was removed, ``False`` if not found.
    """
    hr = await session.get(HR, hr_id)
    if hr is None:
        return False
    hr_label = hr.name or hr.telegram_username
    msgs_deleted = (
        await session.execute(delete(Message).where(Message.hr_id == hr_id))
    ).rowcount
    detached = (
        await session.execute(
            update(Vacancy).where(Vacancy.hr_id == hr_id).values(hr_id=None)
        )
    ).rowcount
    await session.delete(hr)
    logger.info(
        "Deleted HR %d (%r), messages purged=%d, vacancies detached=%d",
        hr_id,
        hr_label,
        int(msgs_deleted or 0),
        int(detached or 0),
    )
    return True


def hr_blacklist_preferred_value(hr: HR) -> str | None:
    """The single value the «Add to blacklist» action should write.

    Prefers @username (human-readable on the Blacklist screen); falls
    back to user_id when no username is set.
    """
    return preferred_blacklist_value(hr_blacklist_candidates(hr))


async def merge_hr(
    session: AsyncSession, *, absorbed_id: int, survivor_id: int
) -> None:
    """Merge ``absorbed`` HR into ``survivor``. Irreversible.

    Caller must wrap in ``session.begin()``.

    Semantics:
    * Vacancies are unioned (absorbed's get repointed onto survivor).
    * **TG account + chat history travel together as one unit.** If
      survivor has a ``telegram_user_id`` → keep its TG identity + chat,
      DROP absorbed's chat (and its TG identity is discarded with it). If
      survivor has no ``telegram_user_id`` → take absorbed's
      ``telegram_user_id`` + ``telegram_username`` AND move its chat onto
      survivor. Username alone doesn't count as an account — without a
      user_id it's just a manual hint.
    * Name falls back from absorbed only when survivor's is empty.
    * Notes are concatenated so nothing is silently lost.
    """
    absorbed, survivor = await load_merge_pair(
        session,
        HR,
        absorbed_id=absorbed_id,
        survivor_id=survivor_id,
        subject="merge_hr",
    )

    abs_tg_user_id = absorbed.telegram_user_id
    abs_tg_username = absorbed.telegram_username
    abs_name = absorbed.name
    abs_notes = absorbed.notes
    survivor_has_tg = survivor.telegram_user_id is not None

    moved_vacancies = await repoint_vacancies(
        session, Vacancy.hr_id, absorbed_id=absorbed_id, survivor_id=survivor_id
    )
    if survivor_has_tg:
        dropped_messages = (
            await session.execute(
                delete(Message).where(Message.hr_id == absorbed_id)
            )
        ).rowcount or 0
        moved_messages = 0
    else:
        moved_messages = (
            await session.execute(
                update(Message)
                .where(Message.hr_id == absorbed_id)
                .values(hr_id=survivor_id)
            )
        ).rowcount or 0
        dropped_messages = 0

    await session.delete(absorbed)
    await session.flush()

    if not survivor_has_tg:
        # TG identity travels with the chat — only adopt absorbed's tg
        # when survivor didn't have an account of its own.
        if abs_tg_user_id is not None:
            survivor.telegram_user_id = abs_tg_user_id
        if abs_tg_username:
            survivor.telegram_username = abs_tg_username
    if not survivor.name and abs_name:
        survivor.name = abs_name
    survivor.notes = concat_notes(survivor.notes, abs_notes)

    logger.info(
        "merged HR #%d -> #%d (vacancies=%d, messages moved=%d, dropped=%d)",
        absorbed_id, survivor_id, moved_vacancies, moved_messages, dropped_messages,
    )
