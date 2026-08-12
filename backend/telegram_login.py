"""Вход в Telegram по коду: четыре шага и состояние между ними.

Входов в приложении два — из мастера первого запуска и из настроек, — но
шаги у них одни и те же: запросить код, подтвердить его, при нужде ввести
облачный пароль, сохранить сессию. Различаются они именем сессии и тем, что
делать после сохранения; всё остальное здесь и объявлено один раз.

Окно про Pyrogram не знает: слот отдаёт сюда набранное и получает исход
шага, а сеть, ошибки Telegram и временный клиент живут за этой границей.
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from pyrogram.client import Client as PyrogramClient
from pyrogram.errors import (
    BadRequest,
    FloodWait,
    PhoneCodeExpired,
    PhoneCodeInvalid,
    PhoneNumberInvalid,
    SessionPasswordNeeded,
)

from backend.runtime_settings import _mask_phone

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class LoginStep:
    """Исход шага: либо что показать окну, либо чем отказать."""

    payload: dict | None = None
    error: str | None = None


async def _safe_disconnect(client) -> None:
    """Закрыть временный клиент, чем бы он ни ответил.

    Сокет стоит закрыть даже у полуоткрытого клиента, а `disconnect` у
    такого сам бросает. Пишем в отладку с трассировкой: молчать неудобно —
    `ConnectionResetError` и `OSError(EPIPE)` прилетают сюда регулярно, и в
    журнале должно быть видно, что это проглотили здесь, а не где-то ещё.
    """
    if client is None:
        return
    try:
        await client.disconnect()
    except Exception:
        logger.debug("_safe_disconnect swallowed", exc_info=True)


async def _username_of(client) -> str | None:
    """Ник вошедшего; пусто — спросить не вышло.

    Спрашивается, пока клиент входа ещё подключён: бот встанет позже, и его
    собственное соединение будет готово не сразу. Пустая строка при этом
    значит «ника у вошедшего нет», а пустота — «не спросили или не
    ответили», и это разные вещи для того, кто ник показывает.
    """
    try:
        me = await client.get_me()
        return me.username or ""
    except Exception:
        logger.debug("login get_me failed", exc_info=True)
        return None


def _flood_wait_refusal(e) -> str:
    """Отказ «Telegram попросил подождать» словами человека.

    Срок Telegram называет не всегда, и «подождите 0 сек» на экране —
    приглашение повторить прямо сейчас и получить тот же запрет.
    """
    secs = int(getattr(e, "value", 0) or 0)
    waiting = _humanize_duration(secs) if secs else "некоторое время"
    return (
        f"Telegram попросил подождать {waiting} "
        "перед следующей попыткой отправить код."
    )


def _humanize_duration(seconds: int) -> str:
    """«12418 сек» → «3 ч 26 мин». Для сообщений о запрете частых попыток."""
    if seconds < 60:
        return f"{seconds} сек"
    minutes, secs = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes} мин" + (f" {secs} сек" if secs else "")
    hours, mins = divmod(minutes, 60)
    return f"{hours} ч" + (f" {mins} мин" if mins else "")


class TelegramLogin:
    """Держатель одной попытки входа: клиент, отпечаток кода, учётные данные.

    Живёт от запроса кода до сохранения сессии. Второй запрос кода закрывает
    клиента первого: иначе «назад, другой номер» оставляет висеть сокет на
    каждый заход.
    """

    def __init__(
        self,
        session_name: str,
        settings,
        on_saved: Callable[[str | None], None] | None = None,
    ) -> None:
        """``session_name`` разводит входы по своим файлам сессии.

        ``on_saved`` зовут после сохранения и передают ник вошедшего: пустую
        строку, если ника нет, и `None`, если спросить не удалось. Без
        обработчика ник у Telegram не спрашивают вовсе — лишний вызов в сеть.
        """
        self._session_name = session_name
        self._settings = settings
        self._on_saved = on_saved
        self._client: PyrogramClient | None = None
        self._phone_code_hash: str | None = None
        self._creds: dict[str, Any] | None = None

    @property
    def awaiting_code(self) -> bool:
        """Код отправлен и ждёт подтверждения."""
        return (
            self._client is not None
            and self._phone_code_hash is not None
            and self._creds is not None
        )

    @property
    def awaiting_password(self) -> bool:
        """Попытка жива: есть кому отдать облачный пароль.

        Шаг с кодом это не проверяет — и не проверяло раньше: пароль,
        присланный до кода, отвергнет сам Telegram, а держатель о том, что
        код уже принят, не знает вовсе.
        """
        return self._client is not None and self._creds is not None

    @property
    def active(self) -> bool:
        """Есть незакрытый клиент — значит, есть что закрывать при выходе."""
        return self._client is not None

    async def forget(self) -> None:
        """Закрыть клиента и обнулить шаг.

        Зовётся и при отмене входа, и при выходе из окна: незакрытый сокет
        переживает попытку, а несброшенный отпечаток кода уводит следующую в
        «код уже отправлен».
        """
        old = self._client
        self._drop()
        await _safe_disconnect(old)

    def _new_client(self, api_id: int, api_hash: str, phone: str) -> PyrogramClient:
        """Клиент Telegram для попытки входа — в памяти, без файла сеанса.

        Файл сеанса тут не нужен: удавшийся вход отдаёт строку, а её
        сохраняет уже настройка. Полусобранный клиент к держателю не
        привязывается, поэтому и отдаётся зовущему.
        """
        return PyrogramClient(
            name=self._session_name,
            api_id=api_id,
            api_hash=api_hash,
            phone_number=phone,
            in_memory=True,
        )

    async def send_code(self, api_id: int, api_hash: str, phone: str) -> LoginStep:
        """Первый шаг: попросить Telegram прислать код на номер."""
        await self.forget()
        self._creds = {
            "api_id": api_id,
            "api_hash": api_hash,
            "phone": phone,
            # Облачный пароль приходит позже, со своего шага, если Telegram
            # его спросит.
            "password": "",
        }
        new_client: PyrogramClient | None = None
        try:
            new_client = self._new_client(api_id, api_hash, phone)
            await new_client.connect()
            sent = await new_client.send_code(phone)
            # К себе привязываем только после удачной отправки: иначе
            # полусобранный клиент висит на держателе, и `forget` при
            # выходе идёт его закрывать.
            self._client = new_client
            self._phone_code_hash = sent.phone_code_hash
            return LoginStep(
                payload={"message": f"Код отправлен в Telegram на {_mask_phone(phone)}."}
            )
        except PhoneNumberInvalid:
            return await self._failed(new_client, "Неверный номер телефона.")
        except FloodWait as e:
            return await self._failed(new_client, _flood_wait_refusal(e))
        except BadRequest as e:
            return await self._failed(new_client, f"Telegram отклонил запрос: {e}")
        except Exception as e:
            logger.exception("telegram_send_code failed")
            return await self._failed(new_client, f"{type(e).__name__}: {e}")

    async def confirm_code(self, code: str) -> LoginStep:
        """Второй шаг: отдать Telegram код из сообщения."""
        assert self._client is not None
        assert self._creds is not None
        try:
            await self._client.sign_in(
                phone_number=self._creds["phone"],
                phone_code_hash=self._phone_code_hash,
                phone_code=code,
            )
        except SessionPasswordNeeded:
            return LoginStep(payload={"need_password": True})
        except PhoneCodeInvalid:
            return LoginStep(error="Неверный код.")
        except PhoneCodeExpired:
            return LoginStep(error="Код устарел — запросите новый.")
        except Exception as e:
            logger.exception("telegram_confirm_code failed")
            return LoginStep(error=f"{type(e).__name__}: {e}")
        return await self._save()

    async def confirm_password(self, password: str) -> LoginStep:
        """Третий шаг, если Telegram спросил: облачный пароль."""
        assert self._client is not None
        assert self._creds is not None
        self._creds["password"] = password
        try:
            await self._client.check_password(password)
        except BadRequest:
            return LoginStep(error="Неверный облачный пароль.")
        except Exception as e:
            logger.exception("telegram_confirm_password failed")
            return LoginStep(error=f"{type(e).__name__}: {e}")
        return await self._save()

    def _drop(self) -> None:
        """Забыть попытку, не трогая сокет.

        Учётные данные обнуляются вместе с остальным: держатель попадает и в
        снимки состояния, и в `repr` при разборе поломок, а лежать там им
        незачем.
        """
        self._client = None
        self._phone_code_hash = None
        self._creds = None

    async def _failed(self, client, message: str) -> LoginStep:
        """Закрыть неудавшуюся попытку и ответить отказом."""
        await _safe_disconnect(client)
        self._drop()
        return LoginStep(error=message)

    async def _save(self) -> LoginStep:
        """Последний шаг: вывезти сессию и записать её в настройки."""
        assert self._client is not None
        assert self._creds is not None
        client = self._client
        creds = self._creds
        username: str | None = None
        try:
            if self._on_saved is not None:
                username = await _username_of(client)
            session_string = await client.export_session_string()
        except Exception as e:
            logger.exception("telegram session export failed")
            self._drop()
            return LoginStep(error=f"{type(e).__name__}: {e}")
        finally:
            # Отключаемся всегда, даже если вывоз сессии сорвался: иначе
            # сокет переживает попытку.
            await _safe_disconnect(client)

        await self._settings.set_tg(
            api_id=creds["api_id"],
            api_hash=creds["api_hash"],
            phone=creds["phone"],
            password=creds.get("password") or "",
            session_string=session_string,
        )
        self._drop()
        logger.info(
            "Telegram session saved (session=%s, api_id=%s, phone=%s)",
            self._session_name,
            creds["api_id"],
            _mask_phone(creds.get("phone")),
        )
        if self._on_saved is not None:
            self._on_saved(username)
        return LoginStep(payload={"done": True})
