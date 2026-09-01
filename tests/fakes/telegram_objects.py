"""Построители объектов Telegram для проверок.

Отдельно от подделки клиента: тот отвечает на обращения, а эти собирают то,
что он отдаёт, — сообщения, собеседников, чаты, переписки. Ходят они и порознь:
объекты нужны половине проверок, которым клиент не нужен вовсе.

Поля, которые боевой код читает напрямую, заданы здесь всегда, пусть и пустые:
отсутствие любого из них он встречает `AttributeError`, а не веткой.
"""

from datetime import timezone
from types import SimpleNamespace

from pyrogram import raw
from pyrogram.enums import MessageEntityType

from tests.factories import EPOCH

# Тот же миг, что `EPOCH`, но записанный по местным часам: Pyrogram отдаёт время
# сообщения наивным и местным (`datetime.fromtimestamp`), а `EPOCH` — это наша
# шкала, наивный UTC. Отдавай подделка сразу `EPOCH`, приведение времени на
# входе стало бы холостым, и проверки перестали бы его сторожить.
TG_EPOCH = EPOCH.replace(tzinfo=timezone.utc).astimezone().replace(tzinfo=None)

# Номер нашей собственной учётной записи. У своего сообщения Telegram ставит
# отправителем нас, а не собеседника, и `FakeTelegramClient.me` отвечает тем же
# номером: разойдись они, «кто я» и «от кого письмо» указывали бы на разных.
OUR_USER_ID = 1


def message(*, text=None, caption=None, **extra) -> SimpleNamespace:
    """Сообщение. `text` и `caption` задаются всегда: код читает их напрямую.

    Разметка задаётся вместе с ними по той же причине: у настоящего сообщения
    поля разметки есть всегда, пустые они или нет, и код читает их без оглядки.
    """
    fields = {"entities": None, "caption_entities": None}
    fields.update(extra)
    return SimpleNamespace(text=text, caption=caption, **fields)


def link_entity(*, offset: int, length: int, url: str) -> SimpleNamespace:
    """Ссылка, спрятанная под словами: адрес лежит не в тексте, а в разметке.

    Отсчёт у Telegram свой — в единицах UTF-16, — и подделка повторяет его, а
    не удобный python'у отсчёт по знакам: на смайлах они расходятся, и
    подделка с удобным отсчётом молча прощала бы промах по месту вставки.
    """
    return SimpleNamespace(
        type=MessageEntityType.TEXT_LINK,
        offset=offset,
        length=length,
        url=url,
        user=None,
    )


def url_entity(*, offset: int, length: int) -> SimpleNamespace:
    """Адрес, набранный в тексте словами. Своего поля с адресом у него нет."""
    return SimpleNamespace(
        type=MessageEntityType.URL,
        offset=offset,
        length=length,
        url=None,
        user=None,
    )


def incoming(*, user_id=777, username=None, text="здравствуйте", **extra):
    """Входящее личное сообщение от собеседника.

    Поля, которые боевой код читает напрямую, заданы всегда: отсутствие
    любого из них он встречает `AttributeError`, а не веткой.

    С чатом иначе: его отсутствие — настоящий случай, и код на него
    ветвится (в оповещении об удалении Pyrogram кладёт `None`). Задан он
    здесь потому, что в личной переписке чат и есть собеседник, и собран
    из того же отправителя: иначе подменённый отправитель разъезжался бы
    с чатом по номеру. Проверки про «чата нет» сообщение собирают сами.
    """
    fields = {
        "id": 10,
        "text": text,
        "date": TG_EPOCH,
        "photo": None,
        "document": None,
        "reply_to_message_id": None,
    }
    fields.update(extra)
    sender = fields.pop("from_user", None)
    if sender is None:
        sender = user(id=user_id, username=username)
    fields.setdefault("chat", chat(id=sender.id, username=sender.username))
    return message(from_user=sender, **fields)


def my_dm(*, chat_id=777, username=None, msg_id=10, text="ответ с телефона", photo=None):
    """Своё письмо в личной переписке — написанное из другого клиента Telegram.

    Отправитель и собеседник здесь разные лица, и это не мелочь оформления:
    у настоящего своего сообщения `from_user` — мы сами, а `chat` — тот, кому
    пишут. Обработчик эха и обработчик правки опознают HR **по чату**, и
    слитые в один номер лица сделали бы подмену `msg.chat` на `msg.from_user`
    незаметной: HR нашёлся бы тот же самый, а в бою написанное с телефона
    перестало бы попадать в переписку окна вовсе.

    Номер и имя собеседника названы так же, как у входящего: проверки личной
    переписки держат их под одними именами для обеих сторон разговора, иначе
    один и тот же случай писался бы по-разному для своего письма и для чужого,
    и пара «своё — чужое» перестала бы читаться рядом.

    Картинка гасит текст: у сообщения с картинкой Telegram кладёт подпись, а
    не текст, и своё письмо с обоими сразу в бою не приходит. Проставленное
    руками, это правило разъезжалось по местам применения.
    """
    return incoming(
        id=msg_id,
        user_id=OUR_USER_ID,
        chat=chat(id=chat_id, username=username),
        outgoing=True,
        text=None if photo is not None else text,
        photo=photo,
    )


# Отличает «текста не задали» от «текста нет»: второе — настоящий случай,
# объявление из одной картинки, и `None` должен доходить до кода как есть.
_UNSET = object()


def post(msg_id: int, *, text=_UNSET, **extra):
    """Объявление из канала. Текст по умолчанию несёт свой номер.

    Номер в тексте нужен проверкам порядка: по нему видно, какое именно
    объявление разобрано, когда их несколько.
    """
    fields = {"service": None, "poll": None}
    fields.update(extra)
    return message(
        id=msg_id,
        text=f"объявление {msg_id}" if text is _UNSET else text,
        date=TG_EPOCH,
        **fields,
    )


def photo(*, small_file_id=None, big_file_id=None) -> SimpleNamespace:
    """Фотография профиля с идентификаторами файлов."""
    return SimpleNamespace(small_file_id=small_file_id, big_file_id=big_file_id)


def document(name: str | None) -> SimpleNamespace:
    """Вложенный документ. Имя бывает и пустым, и отсутствующим."""
    return SimpleNamespace(file_name=name)


def chat(*, title=None, photo=None, **extra) -> SimpleNamespace:
    """Канал или чат в том виде, в каком его отдаёт `get_chat`."""
    return SimpleNamespace(title=title, photo=photo, **extra)


def user(*, username=None, photo=None, **extra) -> SimpleNamespace:
    """Собеседник Telegram.

    Имя, фамилия, ник и признак бота заданы всегда, пусть и пустые: у
    настоящего собеседника эти поля есть, и боевой код читает их напрямую.
    Без них подделка роняет `AttributeError` там, где код работает.
    """
    fields = {
        "is_bot": False,
        "is_deleted": False,
        "first_name": None,
        "last_name": None,
    }
    fields.update(extra)
    return SimpleNamespace(username=username, photo=photo, **fields)


def dialog(peer_id: int, top_message: int | None = None):
    """Переписка в том виде, в каком её отдаёт сырой `messages.GetDialogs`.

    Верхнего письма к ней подделка не прикладывает — и это настоящий случай,
    а не упрощение: у стёртого письма Telegram кладёт `messageEmpty`, у пустой
    переписки номер верхнего письма нулевой. Прогрев обязан кончаться и тогда.
    """
    return raw.types.Dialog(
        peer=raw.types.PeerUser(user_id=peer_id),
        top_message=peer_id if top_message is None else top_message,
        read_inbox_max_id=0,
        read_outbox_max_id=0,
        unread_count=0,
        unread_mentions_count=0,
        unread_reactions_count=0,
        notify_settings=raw.types.PeerNotifySettings(),
    )
