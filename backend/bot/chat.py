"""Переписка с HR из окна: отправка текста, файла и отметка о прочтении."""

import logging

from datetime import datetime, timezone
from pathlib import Path

from backend.models import BotMode
from backend.models import HR
from backend.models import Message
from backend.payloads import OutgoingMessage
from backend.telegram_time import tg_moment
from backend.repository.messages import mark_incoming_read
from backend.repository.messages import save_outgoing_message

from backend.bot import can_send
from backend.bot import media

logger = logging.getLogger(__name__)

EMPTY_MESSAGE = "Пустое сообщение."
"""Отказ на пустой текст письма.

Объявлен здесь, а спрашивают его двое: сам заслон отправки и мост, который
отбивает пустое поле ещё до бота. Порознь эти два написания разъехались бы, а
человек видит их на одном экране."""


async def mark_hr_chat_read(bot, hr_id: int) -> int:
    """Погасить непрочитанное этого HR в базе и в Telegram; сказать, сколько.

    Выключенный бот не делает ни того ни другого: «выключен» значит, что он не
    трогает ни базу, ни Telegram.

    Отметку в Telegram видит живой человек на том конце, поэтому она проходит
    через общий заслон отправки, а не через один режим: при «симуляции
    отправки» и у отсеянного собеседника наружу не уходит ничего. Счётчик в
    окне при этом гасится — прочитанное всё равно прочитано.
    """
    if (await bot.current_mode()) is BotMode.OFF:
        return 0
    now = datetime.now(timezone.utc)
    async with bot.session_factory() as session:
        hr = await session.get(HR, hr_id)
        if hr is None:
            return 0
        updated = await mark_incoming_read(session, hr_id, now)
        await session.commit()

    if updated > 0:
        await _tell_telegram_it_is_read(bot, hr, hr_id)
        logger.debug("Marked %d msgs read for hr %d", updated, hr_id)
    return updated


async def _tell_telegram_it_is_read(bot, hr: HR, hr_id: int) -> None:
    """Погасить подсветку у собеседника и на своих остальных клиентах.

    Сорвавшаяся отметка местную не отменяет: счётчик непрочитанного в окне
    важнее подсветки на телефоне, и откатывать первое из-за второго было бы
    обменом не в ту сторону.
    """
    permission = await can_send.can_send_to_hr(bot, hr)
    if permission.refusal is not None:
        logger.debug(
            "read receipt for hr %d held back: %s", hr_id, permission.refusal
        )
        return
    try:
        await bot.client.read_chat_history(permission.target)
    except Exception:
        logger.exception(
            "read_chat_history failed for hr %d", hr_id,
            extra={"hr_id": hr_id},
        )


_REFUSAL_TEXTS = {
    can_send.NO_TARGET: (
        "У HR нет ни telegram_user_id, ни @username — нечем отправить."
    ),
    can_send.BOT_OFF: "Бот выключен. Включите DM Only или Full.",
    can_send.BLACKLISTED: "HR в blacklist ({value}). Сначала уберите из blacklist.",
    can_send.SENDING_LOCKED: "Отправка отключена: защита от случайной отправки.",
}


async def _target_or_refuse(bot, hr_id: int) -> int | str:
    """Кому слать — либо отказ словами, которые окно покажет подсказкой.

    Заслоны спрашиваются общим объявлением (`can_send`), своё здесь только
    слова: причина, годная для журнала, человеку ничего не говорит. Слово без
    перевода роняет отправку нарочно — молчаливый отказ окно показать не может.
    """
    async with bot.session_factory() as session:
        hr = await session.get(HR, hr_id)
    if hr is None:
        raise RuntimeError(f"HR id={hr_id} не найден.")

    permission = await can_send.can_send_to_hr(bot, hr)
    if permission.refusal is None:
        return permission.target
    raise RuntimeError(
        _REFUSAL_TEXTS[permission.refusal].format(value=permission.blacklist_value)
    )


async def _persist_outgoing(bot, outgoing: OutgoingMessage) -> Message:
    """Записать наше исходящее своей транзакцией и отдать строку.

    Обе отправки из окна — текстом и вложением — кладут строку одинаково
    устроенной; своё у каждой только то, чем заполнена сама `OutgoingMessage`.
    """
    async with bot.session_factory() as session:
        row, _ = await save_outgoing_message(session, outgoing)
        await session.commit()
    return row


async def send_to_hr_chat(bot, hr_id: int, text: str) -> Message:
    """Send a chat message to an HR from the Contacts/HR pane.

    Returns the persisted Message row. Raises ``RuntimeError`` for any
    failure mode the UI can usefully surface — мост показывает текст
    отказа подсказкой.

    Заслоны спрашиваются первыми, до проверки самого сообщения: «этому HR
    писать нельзя» — беда, которую человек чинит правкой HR или переключа-
    телем, а пустое поле ввода он видит и так.
    """
    target = await _target_or_refuse(bot, hr_id)

    clean = (text or "").strip()
    if not clean:
        raise RuntimeError(EMPTY_MESSAGE)

    pyro_msg = await bot.client.send_message(target, clean)
    logger.info(
        "Chat DM sent to hr %d (tg_msg=%d, %d chars)",
        hr_id, pyro_msg.id, len(clean),
    )

    return await _persist_outgoing(
        bot,
        OutgoingMessage(
            hr_id=hr_id,
            text=clean,
            tg_message_id=pyro_msg.id,
            sent_at=tg_moment(pyro_msg.date),
        ),
    )


def _checked_kind(src: Path, file_path: str) -> bool:
    """Отбить файл, которого нет или который Telegram не примет; сказать вид.

    Отказ идёт до отправки и словами человека: он выбирал файл руками, и
    молчаливый отказ выглядел бы потерянным сообщением. Путь называется тем
    же написанием, каким пришёл из окна, — приведённый выглядел бы чужим.

    Вид вложения решается **после** проверки существования: узнавание фото
    читает начало файла, и на несуществующем оно сыпало бы в журнал лишнее
    предупреждение. Пределы размера у фото и документа разные, потому вид и
    нужен здесь же.
    """
    if not src.exists() or not src.is_file():
        raise RuntimeError(f"Файл не найден: {file_path}")
    as_photo = media.looks_like_photo(src)
    try:
        size = src.stat().st_size
    except OSError as e:
        raise RuntimeError(f"Не удалось прочитать файл: {e}")
    cap = media.PHOTO_SIZE_LIMIT if as_photo else media.DOCUMENT_SIZE_LIMIT
    if size > cap:
        mb_cap = cap // (1024 * 1024)
        kind_ru = "фото" if as_photo else "документ"
        raise RuntimeError(
            f"Слишком большой {kind_ru}: {size / (1024*1024):.1f} MB "
            f"> лимит {mb_cap} MB."
        )
    return as_photo


async def send_to_hr_media(bot, hr_id: int, file_path: str) -> Message:
    """Send a photo or document to the HR.

    Заслоны те же, что у отправки текстом, — одно объявление на двоих; строка
    в переписке кладётся тем же `_persist_outgoing`. Своё здесь — проверки
    самого файла и копия в кэше ``media/``, чтобы окно показало вложение, не
    забирая его из Telegram заново.
    """
    target = await _target_or_refuse(bot, hr_id)
    src = Path(file_path)
    as_photo = _checked_kind(src, file_path)
    if as_photo:
        pyro_msg = await bot.client.send_photo(target, str(src))
    else:
        pyro_msg = await bot.client.send_document(target, str(src))
    logger.info(
        "Chat media sent to hr %d (tg_msg=%d, kind=%s, name=%s)",
        hr_id,
        pyro_msg.id,
        "photo" if as_photo else "document",
        src.name,
    )

    media_path = media.cache_sent_file(src, hr_id, pyro_msg.id, as_photo=as_photo)
    return await _persist_outgoing(
        bot,
        OutgoingMessage(
            hr_id=hr_id,
            text="",
            tg_message_id=pyro_msg.id,
            sent_at=tg_moment(pyro_msg.date),
            media_kind="photo" if as_photo else "document",
            media_path=media_path,
            # У фото имени нет: Telegram его не хранит, и окно показывает
            # само изображение, а не строку с названием файла.
            media_name=None if as_photo else src.name,
        ),
    )
