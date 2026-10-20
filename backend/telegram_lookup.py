"""Вопросы бэкенда к Telegram и одна лестница их бед.

Картинка собеседника, картинка с названием канала, сам собеседник по
записанному контакту, пост по ссылке. От `adapters/telegram.py` отличается
тем, что тот объявляет разговор с Telegram — клиента, отправку, запор, — а
здесь стоят ответы на вопросы бэкенда. Беда у всех разбирается одной
лестницей (`ask_telegram`), и её же зовут те, кто спрашивает канал по нику:
попутные вопросы слово беды отбрасывают и получают пустоту, прочие решают по
нему сами.

`read_channel_metadata` своего перехвата не имеет нарочно: сама она в сеть не
ходит, а решает, спрашивать ли картинку, — перехват стоит у того, кто ходит.
"""

import logging
from collections.abc import Awaitable, Callable
from typing import Literal, TypeVar

from pyrogram.errors import (
    ChannelInvalid, ChannelPrivate, FloodWait, PeerIdInvalid, UsernameInvalid, UsernameNotOccupied,
)

from backend.domain.telegram_identity import PostAddress, normalize_username

logger = logging.getLogger(__name__)

T = TypeVar("T")

TelegramTrouble = Literal["tg_invalid", "tg_private", "tg_error"]
"""Чем кончился вопрос к Telegram, если не ответом.

Три слова, потому что человеку они значат разное: опечатку чинят в адресе,
закрытый канал — подпиской, прочее — повтором попозже.
"""


async def ask_telegram(
    what: str, asking: Callable[[], Awaitable[T]]
) -> tuple[T | None, TelegramTrouble | None]:
    """Спросить Telegram; ответ и пусто — или пусто и слово беды. Беда — в журнал.

    ``asking`` — не корутина, а то, чем её заводят: рождённая доводом, она
    рождалась бы снаружи перехвата, и бросок на самом зове ушёл бы мимо.

    Запрет частоты пишется словом, а не трассировкой: это не поломка, а
    просьба подождать.
    """
    try:
        return await asking(), None
    except (UsernameNotOccupied, UsernameInvalid):
        logger.info("%s: Telegram не знает такого имени", what)
        return None, "tg_invalid"
    except (ChannelPrivate, PeerIdInvalid, ChannelInvalid):
        logger.info("%s: канал закрыт или недоступен", what)
        return None, "tg_private"
    except FloodWait as e:
        say_flood_wait(logger, what, e)
        return None, "tg_error"
    except Exception:
        logger.exception("%s: не вышло", what)
        return None, "tg_error"


async def read_post(client, address: PostAddress) -> tuple[object | None, TelegramTrouble | Literal["no_post"] | None]:
    """Пост по адресу; ответ — сообщение и пусто, или пусто и слово беды.

    Удалённого поста Telegram не отвергает, а отдаёт пустым сообщением, —
    это `no_post`, как и вовсе пустой ответ.
    """
    msg, trouble = await ask_telegram(
        f"пост {address.chat_id}/{address.msg_id}",
        lambda: client.get_messages(address.chat_id, message_ids=address.msg_id),
    )
    if trouble is not None:
        return None, trouble
    if msg is None or getattr(msg, "empty", False):
        return None, "no_post"
    return msg, None


async def read_channel_metadata(
    client, chat, *, current_avatar: bytes | None = None
) -> tuple[str | None, bytes | None]:
    """Название и картинка канала из ответа Telegram.

    Спрашивают об этом двое — заведение канала из окна и сводка обновления
    перед обходом.

    **Название отдаётся как есть,** и что с ним делать, решает зовущий: у
    заведения строка новая и перебивать нечего, сводка сравнивает с прежним.

    **Картинка берётся только в пустое место,** и это правило объявления, а не
    зовущего: однажды взятая остаётся, иначе свежую затирала бы устаревшая с
    любого запоздавшего пути. Отсюда и довод `current_avatar` — без него
    сводка качала бы картинку на каждом обходе, чтобы тут же её выбросить.
    """
    title = getattr(chat, "title", None)
    if current_avatar is not None:
        return title, None
    return title, await fetch_telegram_avatar(client, chat)


async def _quietly(what: str, asking):
    """Спросить Telegram и промолчать, если не ответил.

    Оба зова отсюда второстепенны — картинка собеседника и его розыск, — и
    ронять из-за них разбор нельзя: у зовущих на пустоту есть свои дороги.
    """
    answer, _ = await ask_telegram(what, asking)
    return answer


def say_flood_wait(log: logging.Logger, what: str, error) -> None:
    """Записать просьбу Telegram подождать: словом, а не трассировкой.

    Это не поломка, а запрет на срок. Срок Telegram называет не всегда, и в
    запись он идёт строкой — собранная числом, она упала бы на «?» и унесла бы
    с собой саму запись.
    """
    log.warning("%s: FloodWait %s, пропускаю", what, getattr(error, "value", "?"))


async def fetch_telegram_avatar(client, entity) -> bytes | None:
    """Download the small profile photo from a Pyrogram User or Chat.

    Duck-typed on ``.photo`` — both ``pyrogram.types.User`` and
    ``pyrogram.types.Chat`` carry the same ``ChatPhoto`` shape with
    ``small_file_id`` / ``big_file_id``, so the same fetch path covers
    HR contacts and Telegram channels alike.
    """
    photo = getattr(entity, "photo", None)
    if photo is None:
        return None
    file_id = getattr(photo, "small_file_id", None) or getattr(photo, "big_file_id", None)
    if not file_id:
        return None
    buf = await _quietly(
        "fetch_telegram_avatar",
        lambda: client.download_media(file_id, in_memory=True),
    )
    if buf is None:
        return None
    return buf.getvalue()


async def resolve_hr_telegram(client, hr_contact: str):
    username = normalize_username(hr_contact)
    if not username:
        return None
    user = await _quietly(
        f"resolve_hr_telegram {hr_contact!r}", lambda: client.get_users(username)
    )
    if user is None:
        return None
    if getattr(user, "is_bot", False) or getattr(user, "is_deleted", False):
        return None
    return user
