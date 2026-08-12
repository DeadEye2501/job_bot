"""Личная переписка с HR: запись сообщения в обе стороны, привязка, разбор."""

import logging
from dataclasses import dataclass
from typing import Literal

from sqlalchemy.exc import IntegrityError

from backend.bot.media import classify_media, download_media
from backend.flows.auto_gate import status_open_for_auto
from backend.message_text import extract_dm_text
from backend.message_text import extract_text
from backend.telegram_lookup import fetch_telegram_avatar
from backend.flows.dm_classify import classify_and_apply
from backend.payloads import OutgoingMessage
from backend.repository.hr_identify import find_known_hr
from backend.repository.hr_identify import find_latest_vacancy_id_for_hr
from backend.repository.hr_identify import refresh_hr_from_telegram
from backend.repository.hr_identify import resolve_reply_target_vacancy
from backend.repository.messages import find_outgoing_message
from backend.repository.messages import save_incoming_message
from backend.repository.messages import save_outgoing_message

logger = logging.getLogger(__name__)

OutgoingDmOutcome = Literal["stored", "already_stored", "not_stored"]


async def persist_outgoing_dm(session_factory, client, msg, hr_id: int) -> OutgoingDmOutcome:
    """Записать наше исходящее из Telegram; сказать, чем дело кончилось.

    Своё сообщение прилетает и эхом от Telegram, и хвостом при догоне
    переписки, а строку о нём мог завести ещё и сам отправитель. Поэтому
    исходов три, и зовущие разбирают их по-своему: «записали впервые»,
    «строка уже лежала» и «записать не вышло».

    **Проверка «уже лежит» стоит до скачивания вложения нарочно.** Путь в
    кэше собран из номера сообщения, то есть повторная загрузка целится в
    тот же файл, который в это время может читать окно, и оставляет его
    рваным — `download_media` гонится с `shutil.copy2` за один путь.
    """
    async with session_factory() as session:
        if await find_outgoing_message(session, hr_id, msg.id) is not None:
            return "already_stored"
    media_kind, media_name = classify_media(msg)
    media_path = (
        await download_media(client, msg, hr_id) if media_kind is not None else None
    )
    async with session_factory() as session:
        try:
            _, saved = await save_outgoing_message(
                session,
                OutgoingMessage(
                    hr_id=hr_id,
                    text=extract_dm_text(msg),
                    tg_message_id=msg.id,
                    sent_at=msg.date,
                    media_kind=media_kind,
                    media_path=media_path,
                    media_name=media_name,
                ),
            )
            if not saved:
                logger.debug(
                    "Outgoing DM dedup: hr=%d tg_msg=%d already saved",
                    hr_id, msg.id,
                )
                return "not_stored"
            await session.commit()
        except Exception:
            logger.exception(
                "outgoing DM persistence failed",
                extra={"hr_id": hr_id, "tg_message_id": msg.id},
            )
            return "not_stored"
    return "stored"


@dataclass(frozen=True, slots=True)
class _Attachment:
    """Вложение входящего письма: что это, где лежит и как называлось.

    Три значения об одном предмете и ходят вместе: род решает, качать ли
    вообще, путь появляется только после скачивания, имя показывают в
    переписке. Порознь ни одно из них не значит ничего.
    """

    kind: str | None = None
    path: str | None = None
    name: str | None = None


async def _sender_to_listen_to(session_factory, msg):
    """Кого слушать по этому письму: известный HR не из чёрного списка.

    Пустота значит «разбирать нечего»: либо отправитель нам незнаком, либо
    он в списке — и тогда переписка глохнет в обе стороны, потому что
    исходящее блокируют заслоны отправки. Ни строки, ни разбора, ни смены
    статуса вакансии заблокированный не получает.
    """
    from backend.repository.hr_card import _hr_blacklist_value

    logger.debug(
        "DM received: sender_id=%s username=%s",
        msg.from_user.id, msg.from_user.username,
    )
    async with session_factory() as session:
        hr = await find_known_hr(session, msg.from_user.id, msg.from_user.username)
        if hr is None:
            return None
        blacklisted = await _hr_blacklist_value(session, hr)
    if not blacklisted:
        return hr
    logger.info(
        "DM from blacklisted HR ignored",
        extra={
            "hr_id": hr.id,
            "blacklist_value": blacklisted,
            "tg_message_id": msg.id,
        },
    )
    return None


async def _incoming_attachment(client, msg, hr_id: int) -> _Attachment:
    """Скачать вложение письма, если оно есть и есть чем качать."""
    if client is None:
        return _Attachment()
    kind, name = classify_media(msg)
    if kind is None:
        return _Attachment(name=name)
    return _Attachment(kind, await download_media(client, msg, hr_id), name)


async def _attributed_vacancy(session, hr_id: int, msg) -> int | None:
    """К какой вакансии относится письмо HR.

    Ответ на наше конкретное сообщение говорит это точно: у нашей строки
    записан номер вакансии. Без ответа берётся самая свежая вакансия
    этого HR — приближение верное, пока вакансия у него одна, а на пяти
    оно промахивается: HR пишет про вторую, а мы относим к пятой. Цепочка
    ответов эту беду и решает.
    """
    reply_to_id = getattr(msg, "reply_to_message_id", None)
    if reply_to_id:
        by_reply = await resolve_reply_target_vacancy(session, hr_id, reply_to_id)
        if by_reply is not None:
            return by_reply
    return await find_latest_vacancy_id_for_hr(session, hr_id, as_of=msg.date)


async def _save_incoming(session_factory, msg, attachment: _Attachment, avatar):
    """Записать входящее письмо; отдать номер вакансии и номер строки.

    Пустая пара значит «дальше не идём»: HR исчез, письмо уже лежит (гонка
    живого с догоном) или не записалось. HR ищется заново нарочно: первый
    поиск шёл в своей сессии ради номера, куда класть файл.
    """
    text = extract_dm_text(msg)
    async with session_factory() as session:
        try:
            hr = await find_known_hr(
                session, msg.from_user.id, msg.from_user.username
            )
            if hr is None:
                return None, None
            refresh_hr_from_telegram(hr, msg.from_user, avatar=avatar)
            vacancy_id = await _attributed_vacancy(session, hr.id, msg)
            new_msg = await save_incoming_message(
                session, hr.id, vacancy_id, text, msg.id, msg.date,
                media_kind=attachment.kind,
                media_path=attachment.path,
                media_name=attachment.name,
            )
            await session.commit()
            return vacancy_id, new_msg.id
        except IntegrityError:
            # Повтор: живой обработчик наложился на догон или два догона
            # пересеклись; строка уже в базе, разбор по ней прошёл первым
            # проходом. Запись отладочная — под поиск систематических.
            logger.debug(
                "DM duplicate skipped",
                extra={"sender_id": msg.from_user.id, "tg_message_id": msg.id},
            )
            return None, None
        except Exception:
            logger.exception(
                "DM persistence failed",
                extra={"sender_id": msg.from_user.id, "tg_message_id": msg.id},
            )
            return None, None


async def _status_open_for_reply(session_factory, vacancy_id: int):
    """Статус вакансии, если она ещё открыта для разбора; иначе пустота.

    Письмо к этому времени уже записано, и следа достаточно: закрытая
    вакансия разбора не получит, а призрачной строки в истории не появится.
    """
    is_open, v_status = await status_open_for_auto(session_factory, vacancy_id)
    if is_open:
        return v_status
    logger.info(
        "vacancy %s: status=%s closed for auto, skip classification",
        vacancy_id, v_status.value if v_status else "gone",
    )
    return None


async def process_dm(
    msg, lm_client, lm_chat_model, session_factory,
    *, client=None, schedule_classification=None,
) -> None:
    """Провести входящее письмо: записать, отнести к вакансии, разобрать.

    В базу текст идёт с цитатой ответа, в разбор — без неё: иначе разборщик
    оценил бы как слова HR то, что мы сами же процитировали.
    """
    if not msg.from_user or msg.from_user.is_bot:
        return
    hr_lookup = await _sender_to_listen_to(session_factory, msg)
    if hr_lookup is None:
        return
    attachment = await _incoming_attachment(client, msg, hr_lookup.id)
    avatar = None
    if client is not None and hr_lookup.avatar is None:
        avatar = await fetch_telegram_avatar(client, msg.from_user)
    vacancy_id, new_msg_id = await _save_incoming(
        session_factory, msg, attachment, avatar
    )
    if vacancy_id is None:
        return
    v_status = await _status_open_for_reply(session_factory, vacancy_id)
    if v_status is None:
        return
    # С планировщиком письмо ложится в накопитель и разбирается отложенно;
    # без него — на месте.
    classify_text = extract_text(msg)
    if schedule_classification is not None:
        schedule_classification(hr_lookup.id, vacancy_id, new_msg_id, classify_text)
        return

    await classify_and_apply(
        session_factory,
        lm_client,
        lm_chat_model,
        classify_text,
        (vacancy_id, new_msg_id, v_status),
    )
