"""Отклик в Telegram: письмо HR, доставка и след в базе."""

import logging
from dataclasses import dataclass

from pyrogram.errors import FloodWait
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from adapters import telegram
from backend.agent.kit import AgentKit
from backend.applying.result import GONE, Missed, Outcome, TelegramClosed, delivered
from backend.applying.telegram_ban import clear_flood_wait, note_flood_wait
from backend.applying.telegram_letter import (
    RECENT_SEND_WINDOW_DAYS,
    Letter,
    format_channel_ref,
    full_letter,
    parsed_from_row,
    short_note,
)
from backend.domain.apply_order import Way
from backend.domain.telegram_identity import telegram_peer
from backend.models import ApplicationVia, Vacancy
from backend.payloads import OutgoingMessage, ParsedVacancy
from backend.repository.applications import ApplicationEntry, record_application
from backend.repository.hr_identify import count_recent_outgoing_with_vacancy_for_hr
from backend.repository.messages import save_outgoing_message
from backend.telegram_time import utc_now

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _Errand:
    """Кому и о чём пишем: адресат, вакансия и то, что решает вид письма.

    Счёт прежних писем выбирает ветку — полное письмо или короткое, —
    название и канал идут в текст.
    """

    vacancy_id: int
    hr_id: int
    peer: int | str
    parsed: ParsedVacancy
    prior_count: int
    title: str
    channel_ref: str | None


async def via_telegram(kit: AgentKit, vacancy_id: int, way: Way) -> Outcome:
    """Письмо HR в Telegram: первое за окно — полное с резюме, дальше короткое."""
    errand = await _errand(kit, vacancy_id)
    if errand is None:
        return GONE
    letter = await _letter(kit, errand)
    if isinstance(letter, Missed):
        return letter
    tg_message_id = None
    if not kit.pipeline.rs.send_locked:
        sent = await _deliver(kit, errand.peer, letter)
        if isinstance(sent, Missed):
            return sent
        tg_message_id = sent
    return await delivered(_record(kit, errand, way, letter, tg_message_id), vacancy_id)


async def _errand(kit: AgentKit, vacancy_id: int) -> _Errand | None:
    """Прочитать вакансию, её HR и счёт прежних писем ему; удалённая — пусто.

    Способ «Telegram» выбран по адресу HR, поэтому HR у вакансии есть.
    """
    async with kit.pipeline.session_factory() as session:
        v = (await session.scalars(
            select(Vacancy).where(Vacancy.id == vacancy_id)
            .options(selectinload(Vacancy.hr), selectinload(Vacancy.channel))
        )).first()
        if v is None:
            return None
        prior = await count_recent_outgoing_with_vacancy_for_hr(
            session, v.hr.id, window_days=RECENT_SEND_WINDOW_DAYS, other_than=vacancy_id)
        return _Errand(
            vacancy_id, v.hr.id, telegram_peer(v.hr), parsed_from_row(v), prior,
            (v.title or "").strip(),
            format_channel_ref(v.channel.username if v.channel is not None else None),
        )


async def _letter(kit: AgentKit, errand: _Errand) -> Letter | Missed:
    if errand.prior_count:
        return Letter(short_note(errand.title, errand.channel_ref, errand.prior_count), None)
    letter, refusal = await full_letter(
        kit.pipeline, errand.parsed, errand.channel_ref, errand.vacancy_id)
    return letter if letter is not None else Missed(f"письмо не готово: {refusal}")


async def _deliver(kit: AgentKit, peer: int | str, letter: Letter) -> int | None | Missed:
    """Отдать письмо Telegram; номер сообщения или промах.

    Текст письма в журнал не идёт: в нём имя, работодатели и навыки из анкеты.
    """
    rs = kit.pipeline.rs
    try:
        tg_message_id = await telegram.send_dm(kit.pipeline.client, peer, letter.text, letter.attachment)
    except FloodWait as error:
        return Missed("Telegram просит подождать", TelegramClosed(await note_flood_wait(rs, error)))
    except Exception:
        logger.exception("отклик в Telegram: письмо к %s не ушло", peer)
        return Missed("Telegram не принял письмо")
    await clear_flood_wait(rs)
    return tg_message_id


async def _record(kit: AgentKit, errand: _Errand, way: Way, letter: Letter,
                  tg_message_id: int | None) -> None:
    """Письмо в переписку и отклик — одной сделкой.

    Строка переписки без номера сообщения не пишется: под симуляцией его нет, и
    строка показала бы в окне письмо, которого HR не получал. Зов записи письма
    идёт первым нарочно: на повторе он откатывает сессию, а повтор — выигранная
    эхом гонка, и его строка вакансии не знает, поэтому её дописываем.
    """
    async with kit.pipeline.session_factory() as session:
        if tg_message_id is not None:
            stored, _ = await save_outgoing_message(session, OutgoingMessage(
                hr_id=errand.hr_id, text=letter.text, tg_message_id=tg_message_id,
                sent_at=utc_now(), vacancy_id=errand.vacancy_id))
            stored.vacancy_id = errand.vacancy_id
        await record_application(session, ApplicationEntry(
            vacancy_id=errand.vacancy_id, aggregator_id=None, via=ApplicationVia.TELEGRAM,
            target=way.target, letter=letter.text, letter_by="app", screening=[],
            simulated=kit.pipeline.rs.send_locked))
        await session.commit()
    kit.pipeline.fire_vacancies_changed()
