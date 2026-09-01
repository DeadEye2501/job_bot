"""Подделка клиента Pyrogram и построители его объектов.

Реализованы только те методы, которые проект действительно зовёт. Неизвестный
метод даёт `AttributeError` сам собой — объекта-заглушки здесь нет намеренно:
заглушка превращает «код зовёт не то» в зелёный тест.

Расхождение подделки с настоящим клиентом опаснее её отсутствия: боевой код
почти везде обёрнут широким `except`, и неверная подпись метода приходит туда
же, куда пришла бы сетевая ошибка. Проверка «не качали» после этого зелена
при любом исходе. Поэтому подписи здесь повторяют настоящие, а не удобные.
"""

import asyncio
import io
from datetime import timezone
from pathlib import Path
from types import SimpleNamespace

from pyrogram import raw
from pyrogram.enums import MessageEntityType
from pyrogram.errors import PeerIdInvalid, UsernameNotOccupied

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


def _dialog(peer_id: int):
    """Переписка в том виде, в каком её отдаёт сырой `messages.GetDialogs`.

    Верхнего письма к ней подделка не прикладывает — и это настоящий случай,
    а не упрощение: у стёртого письма Telegram кладёт `messageEmpty`, у пустой
    переписки номер верхнего письма нулевой. Прогрев обязан кончаться и тогда.
    """
    return raw.types.Dialog(
        peer=raw.types.PeerUser(user_id=peer_id),
        top_message=peer_id,
        read_inbox_max_id=0,
        read_outbox_max_id=0,
        unread_count=0,
        unread_mentions_count=0,
        unread_reactions_count=0,
        notify_settings=raw.types.PeerNotifySettings(),
    )


class FakeTelegramClient:
    """Отдаёт заранее положенное и записывает, о чём его спрашивали."""

    def __init__(
        self, *, users=None, avatar=None, chats=None, media=b"file", fails=None
    ) -> None:
        """`fails` — что бросить вместо ответа, по имени метода.

        Значением там может стоять список: тогда обращения обслуживаются по
        очереди, и `None` в списке означает «на этот раз без ошибки». Так
        проверяется повтор после отказа.
        """
        self._users = users or {}
        self._avatar = avatar
        self._chats = chats or {}
        self._media = media
        self._fails = fails or {}
        self.get_users_calls: list[str] = []
        self.get_chat_calls: list[str] = []
        self.history_calls: list[tuple] = []
        self.download_calls: list = []
        self.download_paths: list[str] = []
        self.read_calls: list = []
        self.outgoing: list[tuple] = []
        self.handlers: list = []
        self.lifecycle: list[str] = []
        self.last_message_id = 500
        self.session_string = "шифр"
        # Переписка, которую отдаёт `get_chat_history`. Ставится после
        # сборки: пятый именованный довод конструктора упирается в предел.
        self.history: list = []
        self.cold_peers: set = set()
        self.dialog_page: list[int] = []
        self.logged_out = False
        # Вход по коду: чем отвечает Telegram и о чём его спрашивали.
        self.phone_code_hash = "отпечаток"
        self.me = user(id=OUR_USER_ID, username="я")
        self.code_requests: list[str] = []
        self.sign_in_calls: list[tuple] = []
        self.passwords: list[str] = []
        # Вклиниться в середину вызова: так проверяется гонка со встречным
        # обработчиком, который успевает записать строку, пока идёт обращение.
        self.on_send = None
        self.on_download = None

    @property
    def loop(self):
        """Цикл событий. Есть и у настоящего клиента: в паре с `executor`
        через него Pyrogram уводит несопрограммные отборы в отдельный поток."""
        return asyncio.get_running_loop()

    # Отдельного пула нет нарочно: `None` означает «пул по умолчанию», и
    # отбор всё равно исполнится — а свой пришлось бы закрывать руками.
    executor = None

    def add_handler(self, handler) -> None:
        self.handlers.append(handler)

    def _refuse_cold(self, target) -> None:
        """Отказать, если пира нет в кэше.

        Настоящий клиент разрешает адрес перед каждым обращением, и холодный
        номер роняет их все одинаково — и чтение переписки, и отправку письма,
        и отметку о прочтении. Знай подделка об этом одно чтение, две другие
        дороги оставались бы зелёными на кэше, которого нет.
        """
        if target in self.cold_peers:
            raise PeerIdInvalid

    def _fail_if_asked(self, method: str) -> None:
        error = self._fails.get(method)
        if isinstance(error, list):
            error = error.pop(0) if error else None
        if error is not None:
            raise error

    async def get_chat(self, chat_id):
        """Незнакомое имя — бросок, как у настоящего клиента, а не пустота.

        Пустотой подделка водила бы за нос дважды: сторожила бы ветку
        `chat is None`, в которую Telegram не заводит никогда, и оставляла бы
        без сторожа перехват `UsernameNotOccupied`, через который в бою и
        проходит каждая опечатка в имени.
        """
        self.get_chat_calls.append(chat_id)
        self._fail_if_asked("get_chat")
        chat = self._chats.get(chat_id)
        if chat is None:
            raise UsernameNotOccupied
        return chat

    async def get_chat_history(self, target, limit=100):
        """Холодный номер — `PeerIdInvalid`, как у настоящего клиента.

        Пустотой подделка водила бы за нос: код отличает «переписки нет» от
        «прочитать не удалось», и на первом он идёт дальше, а на втором
        разыскивает пира заново.
        """
        self.history_calls.append((target, limit))
        self._fail_if_asked("get_chat_history")
        self._refuse_cold(target)
        for msg in self.history[:limit]:
            yield msg

    async def invoke(self, query, **_options):
        """Сырое обращение. Знает одно — список переписок для прогрева кэша.

        Незнакомое обращение — отказ, а не пустой ответ: пустотой подделка
        сказала бы «Telegram ничего не отдал» о том, чего у неё попросту нет.

        Участники ложатся в кэш до всякого разбора ответа — у настоящего
        клиента это делает `invoke`, здесь то же выражено тем, что холодные
        номера перестают быть холодными.

        `dialog_page`, если задана, отдаётся на **каждое** обращение одна и та
        же. Так ведёт себя Telegram, когда закладка следующей страницы не
        сдвинулась — а не сдвинуться ей есть от чего, — и прогрев обязан на
        этом кончаться. Не задана — переписками считаются все холодные номера,
        и второго обращения не будет: набор опустеет.
        """
        # Уступка управления, которой у настоящего обращения не бывает иначе:
        # без неё зациклившийся прогрев не прервать даже отменой, и проверка
        # такой поломки не покраснела бы, а повисла бы вместе со всем набором.
        await asyncio.sleep(0)
        self._fail_if_asked("invoke")
        if not isinstance(query, raw.functions.messages.GetDialogs):
            raise AttributeError(f"подделка не знает обращения {query!r}")
        page = self.dialog_page or sorted(self.cold_peers)
        # Греются ровно те, кто пришёл в ответе, а не все холодные разом: у
        # настоящего клиента кэш наполняют участники ответа, и подделка,
        # чистящая набор вслепую, прощала бы разбор ответа любой.
        self.cold_peers.difference_update(page)
        return SimpleNamespace(
            dialogs=[_dialog(peer) for peer in page],
            messages=[],
            users=[],
            chats=[],
        )

    async def resolve_peer(self, peer_id):
        """Адрес пира по номеру. У прогретого кэша это чтение без сети."""
        self._fail_if_asked("resolve_peer")
        self._refuse_cold(peer_id)
        return raw.types.InputPeerUser(user_id=peer_id, access_hash=0)

    async def get_users(self, username):
        """Незанятое имя — бросок, по той же причине, что и у `get_chat`.

        Именно `UsernameNotOccupied`: спрашивают здесь всегда ником, и на незанятый
        ник Telegram отвечает именно этим отказом. `PeerIdInvalid` — его ответ на
        незнакомый номер, и подделка, отвечающая им на ник, расходится с настоящим
        клиентом ровно там, где обещала с ним совпадать.
        """
        self.get_users_calls.append(username)
        self._fail_if_asked("get_users")
        user = self._users.get(username)
        if user is None:
            raise UsernameNotOccupied
        # Розыск по нику кладёт пира в кэш и под номером — на этом побочном
        # действии держится запасной путь догона. Номера у ответа может и не
        # быть: проверки розыска контакта кладут сюда объекты без него.
        self.cold_peers.discard(getattr(user, "id", None))
        return user

    async def download_media(self, target, file_name=None, in_memory=False):
        """Скачивание в память по идентификатору файла или на диск по сообщению.

        У Pyrogram это один метод: первым доводом он берёт и идентификатор
        файла, и само сообщение, а куда положить — решают `in_memory` и
        `file_name`. Двумя подделками эти формы разводить нельзя. Боевой
        `download_media` зовёт вторую, и подделка, знающая только первую,
        отвечает `TypeError`; его глотает `except Exception` вокруг вызова,
        и проверка «не качали» зеленеет независимо от того, качали или нет.
        """
        self.download_calls.append(target)
        if self.on_download is not None:
            await self.on_download(file_name)
        self._fail_if_asked("download_media")
        if in_memory:
            return io.BytesIO(self._avatar) if self._avatar is not None else None
        self.download_paths.append(file_name)
        if self._media is None:
            return None
        Path(file_name).write_bytes(self._media)
        return file_name

    async def _accept(self, kind: str, target, payload, caption=None):
        """Принимает исходящее и отдаёт то, что вернул бы Telegram.

        Запись у всех родов одной формы, и подпись в ней есть даже там, где
        её не бывает: разбирать записи по длине зовущему пришлось бы иначе, а
        у документа без подписи «ушёл файл» не отличить от «ушёл файл без
        единого слова».
        """
        self.outgoing.append((kind, target, payload, caption))
        self._fail_if_asked(kind)
        self._refuse_cold(target)
        self.last_message_id += 1
        answer = SimpleNamespace(id=self.last_message_id, date=TG_EPOCH)
        if self.on_send is not None:
            await self.on_send(answer)
        return answer

    async def send_message(self, target, text):
        return await self._accept("send_message", target, text)

    async def send_photo(self, target, path):
        return await self._accept("send_photo", target, path)

    async def send_document(self, target, path, caption=None):
        # Подпись — это текст письма: отправка отклика с резюме шлёт файл и
        # письмо одним вызовом, чтобы HR не получил их порознь.
        return await self._accept("send_document", target, path, caption)

    async def read_chat_history(self, target):
        self.read_calls.append(target)
        self._fail_if_asked("read_chat_history")
        self._refuse_cold(target)

    async def connect(self):
        self.lifecycle.append("подключение")
        self._fail_if_asked("connect")

    async def disconnect(self):
        self.lifecycle.append("отключение")
        self._fail_if_asked("disconnect")

    async def send_code(self, phone):
        self.code_requests.append(phone)
        self._fail_if_asked("send_code")
        return SimpleNamespace(phone_code_hash=self.phone_code_hash)

    async def sign_in(self, phone_number=None, phone_code_hash=None, phone_code=None):
        self.sign_in_calls.append((phone_number, phone_code_hash, phone_code))
        self._fail_if_asked("sign_in")

    async def check_password(self, password):
        self.passwords.append(password)
        self._fail_if_asked("check_password")

    async def get_me(self):
        # В журнал жизни, а не в свой список: у вопроса о себе важно не
        # только то, задали ли его, но и то, что задали до отключения.
        self.lifecycle.append("кто я")
        self._fail_if_asked("get_me")
        return self.me

    async def start(self):
        self.lifecycle.append("запуск")
        self._fail_if_asked("start")

    async def stop(self):
        self.lifecycle.append("остановка")
        self._fail_if_asked("stop")

    async def log_out(self):
        self.logged_out = True
        self._fail_if_asked("log_out")

    async def export_session_string(self):
        self._fail_if_asked("export_session_string")
        return self.session_string
