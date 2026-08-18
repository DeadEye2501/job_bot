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
from backend.telegram_time import tg_moment
from backend.flows.dm_classify import classify_and_apply
from backend.payloads import IncomingMessage, OutgoingMessage, PendingReply
from backend.repository.hr_identify import find_known_hr
from backend.repository.hr_identify import find_latest_vacancy_id_for_hr
from backend.repository.hr_identify import refresh_hr_from_telegram
from backend.repository.hr_identify import resolve_reply_target_vacancy
from backend.repository.messages import find_outgoing_message
from backend.repository.messages import save_incoming_message
from backend.repository.messages import save_outgoing_message

logger = logging.getLogger(__name__)

OutgoingDmOutcome = Literal["stored", "already_stored", "not_stored"]


@dataclass(frozen=True, slots=True)
class _Attachment:
    """Вложение письма: что это, где лежит и как называлось.

    Три значения об одном предмете и ходят вместе: род решает, качать ли
    вообще, путь появляется только после скачивания, имя показывают в
    переписке. Порознь ни одно из них не значит ничего.

    Одно на обе стороны переписки: у нашего письма и у письма HR вложение
    ложится в те же три колонки, и порознь снимки разъехались бы молча.
    """

    kind: str | None = None
    path: str | None = None
    name: str | None = None


async def _attachment_of(client, msg, hr_id: int) -> _Attachment:
    """Вложение письма: род и имя всегда, путь — если было чем скачать.

    Род и имя читаются из самого сообщения, поэтому снимаются и без файла: по
    ним в переписке виден пузырь «была картинка».

    Пустой клиент — не боевой случай, а подпись разбора: он там необязателен,
    и без него зовут со стенда. Ветка есть затем, что иначе загрузка дошла бы
    до `None.download_media` и осела бы в журнале записью об ошибке.
    """
    kind, name = classify_media(msg)
    if kind is None or client is None:
        return _Attachment(kind, None, name)
    return _Attachment(kind, await download_media(client, msg, hr_id), name)


async def _store_outgoing_row(
    session_factory, msg, hr_id: int, media: _Attachment
) -> OutgoingDmOutcome:
    """Положить строку своего сообщения; сказать, чем дело кончилось.

    Отбитый повтор и сорвавшаяся запись отвечают одинаково — «не легло»:
    зовущему в обоих случаях делать нечего, а различие видно в журнале.

    Строка собирается здесь же, под тем же перехватом: чтение текста и
    времени у сообщения Pyrogram тоже может сорваться, и уйди такая беда
    выше — её поймал бы не зовущий, а диспетчер Telegram.
    """
    async with session_factory() as session:
        try:
            row = OutgoingMessage(
                hr_id=hr_id,
                text=extract_dm_text(msg),
                tg_message_id=msg.id,
                sent_at=tg_moment(msg.date),
                media_kind=media.kind,
                media_path=media.path,
                media_name=media.name,
            )
            _, saved = await save_outgoing_message(session, row)
            if not saved:
                logger.debug(
                    "Outgoing DM dedup: hr=%d tg_msg=%d already saved",
                    row.hr_id, row.tg_message_id,
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
    return await _store_outgoing_row(
        session_factory, msg, hr_id, await _attachment_of(client, msg, hr_id)
    )


async def _sender_to_listen_to(session_factory, msg):
    """Кого слушать по этому письму: известный HR не из чёрного списка.

    Пустота значит «разбирать нечего»: либо отправитель нам незнаком, либо
    он в списке — и тогда переписка глохнет в обе стороны, потому что
    исходящее блокируют заслоны отправки. Ни строки, ни разбора, ни смены
    статуса вакансии заблокированный не получает.
    """
    from backend.repository.hr_card import hr_blacklist_value

    logger.debug(
        "DM received: sender_id=%s username=%s",
        msg.from_user.id, msg.from_user.username,
    )
    async with session_factory() as session:
        hr = await find_known_hr(session, msg.from_user.id, msg.from_user.username)
        if hr is None:
            return None
        blacklisted = await hr_blacklist_value(session, hr)
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


def _incoming_row(
    msg, hr_id: int, vacancy_id: int | None, attachment: _Attachment
) -> IncomingMessage:
    """Свёртка входящего письма из сообщения Telegram и того, что о нём знают.

    Текст достаётся общим правилом (`extract_dm_text`): вложение без подписи
    даёт пустой текст, и подпись под ним берётся оттуда же, откуда у эха.
    """
    return IncomingMessage(
        hr_id=hr_id,
        vacancy_id=vacancy_id,
        text=extract_dm_text(msg),
        tg_message_id=msg.id,
        received_at=tg_moment(msg.date),
        media_kind=attachment.kind,
        media_path=attachment.path,
        media_name=attachment.name,
    )


async def _save_incoming(session_factory, msg, attachment: _Attachment, avatar):
    """Записать входящее письмо; отдать номер вакансии и номер строки.

    Пустая пара значит «дальше не идём»: HR исчез, письмо уже лежит (гонка
    живого с догоном) или не записалось. HR ищется заново нарочно: первый
    поиск шёл в своей сессии ради номера, куда класть файл.
    """
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
                session, _incoming_row(msg, hr.id, vacancy_id, attachment)
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
    attachment = await _attachment_of(client, msg, hr_lookup.id)
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
        reply = PendingReply(vacancy_id, new_msg_id, msg.id, classify_text)
        schedule_classification(hr_lookup.id, reply)
        return

    await classify_and_apply(
        session_factory,
        lm_client,
        lm_chat_model,
        classify_text,
        (vacancy_id, new_msg_id, v_status),
    )
