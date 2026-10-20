"""Правила Telegram по написанному: чей это ник, куда ведёт адрес.

Чистое правило, как соседи по `backend/domain/`: ни базы, ни сети, ни
Pyrogram. От `adapters/telegram.py` отличается тем, что тот разговаривает с
Telegram, а здесь только решают, годится ли написанное в ник, чем из двух
опознаний адресовать письмо и что за адрес перед глазами. Пока эти правила
лежали рядом с походами за собеседником, `pyrogram` попадал в замыкание
ввозов всякого, кто спрашивал «ник ли это», — включая разбор объявления,
которому Telegram не нужен вовсе.

Хосты Telegram записаны здесь один раз на всё приложение: переписанный в
каждом месте своими словами, перечень расходился бы так же, как расходились
перечни площадок.
"""

import re
from dataclasses import dataclass

from backend.domain.company_names import without_scheme

TELEGRAM_LINK_HOSTS = frozenset({"t.me", "telegram.me"})
"""Хосты ссылок на канал, пост и собеседника."""

TELEGRAPH_HOSTS = frozenset({"telegra.ph"})
"""Хосты статей, в которые каналы выносят текст объявления."""

TELEGRAM_HOSTS = TELEGRAM_LINK_HOSTS | TELEGRAPH_HOSTS
"""Всё, что читает приём постов, а не «Поиск по сети»."""

# Адрес статьи: «https://telegra.ph/ключ». Ключ обязателен: без него это
# корень сайта, статьи за ним нет никогда.
#
# Хвост адреса кончается не на чём попало. Закрывающая скобка в него не
# входит — за подписью ссылки адрес дописывают именно в скобках
# (см. `extract_post_text`). Точка и запятая — тоже: адрес, набранный в тексте
# словами, кончается точкой конца предложения, и утащенная в адрес точка ведёт
# в никуда.
#
# Адреса залитых на Telegraph картинок («telegra.ph/file/…») отсюда не
# вычитаются, хотя статьями и не являются: тега статьи в ответе нет, и такой
# адрес честно отдаёт пустоту, ничего не портя. Ловить их отдельным правилом
# значило бы завести ветку под случай, которого в постах ещё не встречалось.
ARTICLE_URL_RE = re.compile(
    r"https?://(?:" + "|".join(map(re.escape, sorted(TELEGRAPH_HOSTS)))
    + r")/[^\s)\]]*[^\s)\].,;:!?…»\"']"
)

_LINK_PREFIXES = tuple(
    f"{www}{host}/" for host in sorted(TELEGRAM_LINK_HOSTS) for www in ("", "www.")
)

_TG_USERNAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{4,31}$")
# Ник, набранный человеком, принимается и от четырёх символов: новым такие
# Telegram не выдаёт, но выданные до ужесточения работают, и собеседник с
# таким ником обычен. В объявлении о работе та же поблажка опасна — «Anna»
# там имя, а не ник, и разыскав по нему живую чужую учётную запись, отклик
# ушёл бы постороннему. Разница не в строгости, а в том, кто отвечает за
# написанное: за формой стоит человек, за объявлением никто.
_TG_TYPED_USERNAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{3,31}$")
_TG_RESERVED_PATHS = {"joinchat", "c", "s", "bot", "dl", "addstickers"}


def _strip_link_prefixes(s: str) -> str:
    """Снять с записи всё, что стоит перед самим ником.

    Порядок обязателен: домен ищут в том, что осталось от схемы, а путь
    веб-просмотра — в том, что осталось от домена.

    Сравнивается всё это без оглядки на регистр, а отрезается по длине: схему
    и домен пишут и заглавными — так их оставляют автоподстановка и сами
    объявления, — а вот ник дальше идёт как написан, и складывать его регистр
    нельзя, он попадёт в карточку.

    `www.` снимается вместе с доменом, а не отдельной строкой до него: сам по
    себе он ничего не говорит, и снятый заранее превращал бы `www.jobsboard`
    в ник `jobsboard` — запись, которая ником не является вовсе.

    `s/` разбирается здесь, а не общим правилом хвоста: сам `s` числится
    служебным путём, и без этой строки `t.me/s/канал` отсеивался бы наравне
    с `t.me/c/12345`, то есть ссылка на канал считалась бы негодной.
    """
    s = without_scheme(s)
    path = _link_path(s)
    return s if path is None else path


def _link_path(s: str) -> str | None:
    """Путь ссылки Telegram без домена и веб-просмотра; пусто — ссылка не на Telegram."""
    for host in _LINK_PREFIXES:
        if s.lower().startswith(host):
            s = s[len(host):]
            if s.lower().startswith("s/"):
                s = s[len("s/"):]
            return s
    return None


@dataclass(frozen=True, slots=True)
class PostAddress:
    """Пост Telegram по ссылке: канал — ник в нижнем регистре или номер
    закрытого канала, у которого ника нет, — и номер поста."""

    channel: str | None
    private_id: int | None
    msg_id: int

    @property
    def chat_id(self) -> str | int:
        """Чем спросить канал у Telegram: ником или номером закрытого канала.

        Номер — числом и с приставкой `-100`, как Telegram называет каналы:
        строкой Pyrogram принял бы его за телефон.
        """
        return self.channel if self.channel is not None else int(f"-100{self.private_id}")


# Номер темы форума стоит между каналом и номером поста и поста не меняет:
# номер сообщения в канале один на все темы.
_POST_PATH_RE = re.compile(r"(?:c/(?P<private>\d+)|(?P<nick>[^/]+))/(?:\d+/)?(?P<msg>\d+)/?")


def post_address(url: str) -> PostAddress | None:
    """Канал и номер поста из ссылки; пусто — ссылка не на пост.

    Разбирается тем же снятием домена, что и ник собеседника: одна ссылка не
    должна читаться двумя правилами. Хвост после номера — `?single`,
    `?comment=` — поста не меняет.
    """
    path = _link_path(without_scheme(url))
    if path is None:
        return None
    match = _POST_PATH_RE.fullmatch(path.split("?", 1)[0].split("#", 1)[0])
    if match is None:
        return None
    msg_id = int(match["msg"])
    if match["private"] is not None:
        return PostAddress(None, int(match["private"]), msg_id)
    nick = normalize_username(match["nick"])
    return None if nick is None else PostAddress(nick.lower(), None, msg_id)


def normalize_username(hr_contact: str | None, *, typed_by_a_person: bool = False) -> str | None:
    """Ник из записи контакта: голое написание или отсутствие.

    ``typed_by_a_person`` опускает нижнюю границу длины до четырёх — см.
    `_TG_TYPED_USERNAME_RE`. Своим доводом, а не отдельным объявлением,
    потому что различается только эта граница, а разбор ссылки, собачки и
    хвоста у обоих один.
    """
    if not hr_contact:
        return None
    s = _strip_link_prefixes(hr_contact.strip())
    s = s.lstrip("@").strip().rstrip("/")
    if "/" in s:
        s = s.split("/", 1)[0]
    if not s or s.startswith("+"):
        return None
    if s.lower() in _TG_RESERVED_PATHS:
        return None
    allowed = _TG_TYPED_USERNAME_RE if typed_by_a_person else _TG_USERNAME_RE
    if not allowed.match(s):
        return None
    return s


def typed_username(value) -> str | None:
    """Ник, введённый человеком в поле формы: пусто — отсутствие, негодное —
    отказ.

    Отличается от `normalize_username` тем, что различает «поле пустое» и
    «поле заполнено чем-то не тем». Первое законно — ник знают не про
    каждого HR; второе молча превратилось бы в отсутствие, и человек узнал
    бы об этом, только когда отправка перестала находить собеседника.

    Одна собачка считается пустым полем: её набирают первой и стирают
    вместе со всем остальным.

    Четырёхбуквенные ники здесь проходят, а в разборе объявления нет: за
    формой стоит человек, который написанное подтверждает.
    """
    if value is None:
        return None
    typed = str(value).strip().lstrip("@").strip()
    if not typed:
        return None
    handle = normalize_username(typed, typed_by_a_person=True)
    if handle is None:
        raise ValueError("ник не похож на телеграмовский")
    return handle


def telegram_peer(hr) -> int | str | None:
    """Адресат HR в Telegram: учётная запись, иначе ник, иначе ничего.

    Порядок важен: номер учётной записи не меняется, а ник человек
    меняет когда угодно — по старому письмо уйдёт чужому человеку или не
    уйдёт вовсе. Ничего — значит писать некуда; что делать дальше, решает
    зовущий.
    """
    return hr.telegram_user_id or hr.telegram_username


@dataclass(frozen=True, slots=True)
class DialogPeer:
    """Собеседник из списка переписок Telegram: номер учётной записи и ник.

    Ник приходит вместе с номером и нужен целиком ради одного случая: наш
    собеседник, заведённый разбором объявления, известен одним ником — номера
    в посте нет вовсе.
    """

    peer_id: int
    username: str | None = None


def hrs_to_catch_up(hrs, dialogs) -> list:
    """Собеседники, чью переписку догонять, — у кого она свежее, впереди.

    Догон читает их подряд, тратя на каждого обращение к Telegram, а человек
    закрывает окно раньше, чем очередь дойдёт до конца. Порядок поэтому берётся
    из списка переписок — Telegram отдаёт его свежими вперёд, — а не из порядка
    строк в базе.

    Кого в списке нет, того не читают: переписки с ним не существует, а
    попытка стоит дорого — его номера нет в кэше пиров, и чтение уходит в
    розыск по нику, за который Telegram запрещает такой розыск часами, на весь
    аккаунт. Список неизвестен (`None`: чтение сорвалось или не дошло до
    конца) — читаются все в порядке строк базы: отбор по нему молча потерял бы
    живую переписку.

    Опознание повторяет `find_known_hr`: сперва номер, потом ник и только у
    того, у кого номера нет. Ник свободно достаётся другому человеку, и запись
    со своим номером под чужим ником принадлежит не тому, с кем идёт разговор.
    """
    if dialogs is None:
        return list(hrs)
    by_id = {hr.telegram_user_id: hr for hr in hrs if hr.telegram_user_id}
    by_name = {
        hr.telegram_username.lower(): hr
        for hr in hrs
        if hr.telegram_username and not hr.telegram_user_id
    }
    talking, taken = [], set()
    for dialog in dialogs:
        hr = by_id.get(dialog.peer_id)
        if hr is None and dialog.username:
            hr = by_name.get(dialog.username.lower())
        if hr is not None and hr.id not in taken:
            taken.add(hr.id)
            talking.append(hr)
    return talking

