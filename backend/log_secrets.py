"""Вымарывание секретов из журнала — включая тот случай, когда запись сломалась.

Дела два, и вместе они не по родству, а потому, что порознь ходят по кругу:
жалоба на сорванную запись обязана быть вымаранной — в сломавшейся записи лежит
ровно то, что вымарывают, — а вымарыванию, когда оно само сломается, надо
пожаловаться. Разведи по модулям, и каждый звал бы соседа. Той же жалобой
пользуется файл журнала на неудавшемся повороте, и там секрета нет вовсе:
переиспользуется способ пожаловаться, а не правило вымарывания.

`report_own_failure` — единственный способ пожаловаться, доступный тому, кто
сам обслуживает жалобы: обычная запись ушла бы по кругу.
"""

from __future__ import annotations

import logging
import re
import sys
import traceback
from contextlib import suppress
from datetime import datetime

from config import get_log_path


# В коде ни один logger.* специально секреты не пишет (audited). Но третьи
# либы (httpx debug-mode, pyrogram, sqlalchemy echo) могут засветить
# Authorization-header или строку коннекта; SecretRedactionFilter ловит
# это до того как record уезжает в stdout и в UI-buffer.
_SECRET_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"Bearer\s+[A-Za-z0-9_\-\.]+", re.IGNORECASE),
    re.compile(r"sk-[A-Za-z0-9_\-]{16,}"),
    re.compile(
        r"(api_hash[\"']?\s*[:=]\s*[\"']?)[a-f0-9]{32}",
        re.IGNORECASE,
    ),
    # Строка сеанса Telegram. Складывает её Pyrogram безопасным для адреса
    # написанием base64, то есть с `-` и `_` внутри: без них в классе образец
    # рвался бы о первый же такой знак и настоящую строку не ловил вовсе.
    # Порог 50 знаков — короче маскировать опасно, там начинаются обычные
    # слова и пути.
    re.compile(r"\b[A-Za-z0-9+/=:_-]{50,}\b"),
    # Номер телефона и одноразовый код входа. Пишет их не наш код — свой номер
    # он прячет сам (`tg_credentials.mask_phone`), — а Pyrogram: он
    # выкладывает в отладку каждое исходящее обращение целиком, и на входе в
    # Telegram это `auth.SendCode` и `auth.SignIn` с номером и кодом открытым
    # текстом. Уровень отладки поднимает кольцо записей (`log_buffer.install`),
    # и человек видит их экраном «Логи» — вместе с тем, кому этот экран покажет.
    #
    # Прочие образцы их не берут: номер короче пятидесяти знаков, код
    # пятизначный, и ни `Bearer`, ни `sk-`, ни `api_hash` тут ни при чём.
    re.compile(
        r"phone_number[\"']?\s*[:=]\s*[\"']?\+?[\d ()-]{5,}",
        re.IGNORECASE,
    ),
    re.compile(
        r"phone_code(?:_hash)?[\"']?\s*[:=]\s*[\"']?[A-Za-z0-9_-]+",
        re.IGNORECASE,
    ),
)
_REDACTED = "***"


def report_own_failure(what: str, record: logging.LogRecord | None) -> None:
    """Сказать о беде внутри самого журналирования, минуя логирование.

    `record` — запись, на которой сломалось; `None` там, где беда не
    привязана ни к одной, — переход на новый файл случается между записями.

    Обычная запись ушла бы по кругу: беда случилась в обработчике логов.
    Штатный для такого `handleError` печатает в поток ошибок, а в оконной
    сборке (`console=False`) потока нет вовсе — остаётся тот же файл, куда
    идёт журнал. Довод записан здесь один раз; остальные места на него
    ссылаются.

    Файл открывается на одну запись и сразу закрывается: им владеет
    `RotatingFileHandler`, и держать второй описатель открытым значит
    однажды сорвать ему переход на новый файл.
    """
    try:
        stamp = f"{datetime.now():%Y-%m-%d %H:%M:%S,%f}"[:-3]
        # Шаблон читается и вымарывается здесь, а не у зовущего: `__repr__`
        # у него бывает сломан, и тогда жалоба превратилась бы в падение
        # того, кто просто позвал `logger.*`. Вымарывание обязательно —
        # собрать сообщение не удалось, значит обычный путь секрет не убрал.
        said = "" if record is None else f": {_redact(repr(record.msg))}"
        line = f"{stamp} [ERROR] backend.log_secrets: {what}{said}\n"
        with open(get_log_path(), "a", encoding="utf-8", errors="replace") as out:
            out.write(line + traceback.format_exc())
    except Exception:
        # Файла нет или он недоступен — остаётся поток ошибок, которого в
        # оконной сборке нет. Дальше этого рубежа сказать нечем.
        if sys.stderr is not None:
            with suppress(OSError, ValueError):
                sys.stderr.write(f"backend.log_secrets: {what}\n")
                traceback.print_exc()


def report_own_failure_once(what: str, record: logging.LogRecord) -> None:
    """Пожаловаться на беду журналирования, но об одной записи — один раз.

    Отметка живёт на самой записи, потому что жалующихся несколько: фильтр
    висит на каждом обработчике своим экземпляром, и об одной сломанной
    записи сообщили бы все трое. Оттого и запись здесь обязательна: без неё
    засову негде помнить, и он перестал бы быть засовом молча. Кому надо
    пожаловаться без записи — зовёт `report_own_failure` и помнит сам.
    """
    if getattr(record, "own_failure_reported", False):
        return
    record.own_failure_reported = True
    report_own_failure(what, record)


def _redact(text: str) -> str:
    out = text
    for pat in _SECRET_PATTERNS:
        out = pat.sub(_REDACTED, out)
    return out


class SecretRedactionFilter(logging.Filter):
    """Применяет _redact к message и exc_text. Ставится на обработчики
    корневого logger'а через ``install_secret_filter()``."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            msg = record.getMessage()
        except Exception:
            # Сообщение не собралось — значит и вымарать секрет в нём нечем.
            # Запись пропускается дальше, но молчать о ней нельзя: именно в
            # такой секрет и уедет незамаскированным.
            report_own_failure_once("запись не собирается", record)
            return True
        scrubbed = _redact(msg)
        if scrubbed != msg:
            record.msg = scrubbed
            record.args = ()
        # Трассировку приходится собирать здесь самим. Обычно её собирает
        # форматтер, но он работает уже внутри обработчика, то есть после
        # фильтров: первый обработчик по списку — в бою файловый — записал бы
        # текст исключения до всякого вымарывания. Собранное кладётся в саму
        # запись, форматтер потом берёт готовое.
        if record.exc_info and not record.exc_text:
            try:
                record.exc_text = "".join(
                    traceback.format_exception(*record.exc_info)
                ).rstrip("\n")
            except Exception:
                # Фильтр работает до защитного перехвата вокруг записи, и своё
                # падение здесь ушло бы наружу — тому, кто просто позвал
                # `logger.exception` внутри своего `except`. Трассировку в
                # этом случае соберёт форматтер: он-то как раз под защитой.
                report_own_failure_once("трассировка записи не собирается", record)
        if record.exc_text:
            record.exc_text = _redact(record.exc_text)
        return True


def install_secret_filter() -> None:
    """Идемпотентно ставит SecretRedactionFilter на каждый обработчик корня.

    На сам logger вешать нельзя, хотя и хочется: фильтр logger'а разбирает
    только записи, сделанные им самим, а до обработчиков предка запись
    доходит мимо его фильтров. Записи третьих библиотек — httpx, pyrogram,
    sqlalchemy — идут именно так, и ради них фильтр и заведён.
    """
    for handler in logging.getLogger().handlers:
        if not any(isinstance(f, SecretRedactionFilter) for f in handler.filters):
            handler.addFilter(SecretRedactionFilter())
