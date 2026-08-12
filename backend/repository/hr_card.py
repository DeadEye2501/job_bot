"""Одна запись HR: чтение, правка, слияние, удаление."""

import logging
from dataclasses import dataclass

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.domain.telegram_identity import typed_username
from backend.models import Company, HR, Message, Vacancy
from backend.payloads import HrDetail

from backend.repository.blacklist_marks import (
    active_blacklist_value,
    preferred_blacklist_value,
)
from backend.repository.merging import concat_notes, load_merge_pair
from backend.repository.vacancies_life import repoint_vacancies
from backend.repository.messages import UNREAD_INCOMING

logger = logging.getLogger(__name__)


LAST_VACANCY_ORDER = (Vacancy.created_at.desc(), Vacancy.id.desc())
"""Порядок «самая свежая вакансия человека», по которому берут его компанию.

Одно объявление на карточку и на список: спрашивают они одно и то же, а
приёмы разные — карточке хватает одной строки с ограничением, списку нужна
оконная нумерация по всем людям разом. Разойдись порядки, два экрана называли
бы разные компании, и заметить это было бы нечем.

Разрешитель по идентификатору не украшение: время заведения проставляет база
одним `CURRENT_TIMESTAMP`, и две вакансии подряд легко получают одну метку.

Свежую вакансию без компании оба читают одинаково — как «компании нет»:
важно, с кем человек работает сейчас, а не с кем работал когда-то.
"""


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

    Ник разбирается тем же объявлением, что и при заведении: правка того же
    поля не может принимать то, что форма заведения отвергает. Не
    телеграмовское роняет ``ValueError`` — прежний ник при этом остаётся
    цел, а молча записанное имя человека обнаружилось бы только тогда,
    когда отправка перестала находить собеседника.
    """
    hr = await session.get(HR, hr_id)
    if hr is None:
        return False
    changed = []
    if name is not _HR_FIELD_UNSET:
        hr.name = (str(name).strip() or None) if name is not None else None
        changed.append("name")
    if telegram_username is not _HR_FIELD_UNSET:
        hr.telegram_username = (
            None if telegram_username is None else typed_username(telegram_username)
        )
        changed.append("telegram_username")
    if notes is not _HR_FIELD_UNSET:
        hr.notes = (str(notes).strip() or None) if notes is not None else None
        changed.append("notes")
    await session.flush()
    if changed:
        logger.debug("Updated HR %d fields=%s", hr_id, changed)
    return True


async def _vacancy_count_of(session: AsyncSession, hr_id: int) -> int:
    """Сколько вакансий человек принёс за всё время."""
    return int(
        await session.scalar(
            select(func.count(Vacancy.id)).where(Vacancy.hr_id == hr_id)
        )
        or 0
    )


async def _last_company_of(
    session: AsyncSession, hr_id: int
) -> tuple[int | None, str | None]:
    """Компания последней вакансии человека — номер и имя.

    Соединение внешнее: последняя вакансия могла быть без компании, и тогда
    у карточки нет её ни номером, ни именем. Порядок — общий
    `LAST_VACANCY_ORDER`: разойдись он со списком, карточка и перечень
    называли бы разные компании.
    """
    row = (
        await session.execute(
            select(Company.id, Company.name)
            .select_from(Vacancy)
            .outerjoin(Company, Company.id == Vacancy.company_id)
            .where(Vacancy.hr_id == hr_id)
            .order_by(*LAST_VACANCY_ORDER)
            .limit(1)
        )
    ).first()
    return (row[0], row[1]) if row else (None, None)


async def _unread_count_of(session: AsyncSession, hr_id: int) -> int:
    """Сколько непрочитанных входящих у человека."""
    return int(
        await session.scalar(
            select(func.count(Message.id)).where(
                Message.hr_id == hr_id,
                *UNREAD_INCOMING,
            )
        )
        or 0
    )


async def get_hr_detail(
    session: AsyncSession, hr_id: int
) -> HrDetail | None:
    """Detail payload for the Contacts / HR pane (05).

    Returns the HR row + компания с самой свежей его вакансии (id + name,
    порядок — `LAST_VACANCY_ORDER`; пусто, если та вакансия ни к какой
    компании не привязана) + total vacancy count + count of unread
    incoming messages. Returns ``None`` if the HR row is gone.
    """
    hr = await session.get(HR, hr_id)
    if hr is None:
        return None
    vacancy_count = await _vacancy_count_of(session, hr_id)
    last_company_id, last_company_name = await _last_company_of(session, hr_id)
    return HrDetail(
        hr=hr,
        vacancy_count=vacancy_count,
        last_company_id=last_company_id,
        last_company_name=last_company_name,
        unread_count=await _unread_count_of(session, hr_id),
        blacklist_value=await _hr_blacklist_value(session, hr),
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
    detached = await repoint_vacancies(
        session, Vacancy.hr_id, absorbed_id=hr_id, survivor_id=None
    )
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


@dataclass(frozen=True, slots=True)
class _AbsorbedHr:
    """Что уносится с поглощаемым человеком.

    Снимок читается **до** удаления строки: после него обращение к полям
    удалённой записи — уже не чтение, а поведение сессии.
    """

    telegram_user_id: int | None
    telegram_username: str | None
    name: str | None
    notes: str | None


async def _move_or_drop_chat(
    session: AsyncSession, absorbed_id: int, survivor_id: int,
    survivor_has_tg: bool,
) -> tuple[int, int]:
    """Переписка поглощаемого: перенести или стереть. Сколько того и другого.

    Учётная запись Telegram и переписка ходят вместе: у выжившего своя
    запись — чужая переписка стирается вместе с ней, нет своей — переписка
    переезжает на него целиком.
    """
    if survivor_has_tg:
        dropped = (
            await session.execute(
                delete(Message).where(Message.hr_id == absorbed_id)
            )
        ).rowcount or 0
        return 0, dropped
    moved = (
        await session.execute(
            update(Message)
            .where(Message.hr_id == absorbed_id)
            .values(hr_id=survivor_id)
        )
    ).rowcount or 0
    return moved, 0


def _carry_to_survivor(
    survivor: HR, taken: _AbsorbedHr, survivor_has_tg: bool
) -> None:
    """Перенести на выжившего то, что не пропадает вместе с поглощённым.

    Учётная запись Telegram достаётся только тому, у кого своей не было —
    вместе с перееханной перепиской. Один ник учётной записью не считается:
    без числового идентификатора это ручная подсказка, а не аккаунт. Имя
    берётся, только если у выжившего пусто, а заметки склеиваются — иначе
    написанное человеком пропадало бы молча.
    """
    if not survivor_has_tg:
        if taken.telegram_user_id is not None:
            survivor.telegram_user_id = taken.telegram_user_id
        if taken.telegram_username:
            survivor.telegram_username = taken.telegram_username
    if not survivor.name and taken.name:
        survivor.name = taken.name
    survivor.notes = concat_notes(survivor.notes, taken.notes)


async def merge_hr(
    session: AsyncSession, *, absorbed_id: int, survivor_id: int
) -> None:
    """Merge ``absorbed`` HR into ``survivor``. Irreversible.

    Caller must wrap in ``session.begin()``. Вакансии объединяются, а что
    делается с учётной записью, перепиской, именем и заметками — см.
    :func:`_move_or_drop_chat` и :func:`_carry_to_survivor`.
    """
    absorbed, survivor = await load_merge_pair(
        session,
        HR,
        absorbed_id=absorbed_id,
        survivor_id=survivor_id,
        subject="merge_hr",
    )
    taken = _AbsorbedHr(
        telegram_user_id=absorbed.telegram_user_id,
        telegram_username=absorbed.telegram_username,
        name=absorbed.name,
        notes=absorbed.notes,
    )
    survivor_has_tg = survivor.telegram_user_id is not None

    moved_vacancies = await repoint_vacancies(
        session, Vacancy.hr_id, absorbed_id=absorbed_id, survivor_id=survivor_id
    )
    moved_messages, dropped_messages = await _move_or_drop_chat(
        session, absorbed_id, survivor_id, survivor_has_tg
    )
    await session.delete(absorbed)
    await session.flush()
    _carry_to_survivor(survivor, taken, survivor_has_tg)

    logger.info(
        "merged HR #%d -> #%d (vacancies=%d, messages moved=%d, dropped=%d)",
        absorbed_id, survivor_id, moved_vacancies, moved_messages, dropped_messages,
    )
