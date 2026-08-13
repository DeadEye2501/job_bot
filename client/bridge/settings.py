"""Экран «Настройки»: всё, что окно спрашивает и правит на нём."""

from __future__ import annotations

import asyncio
import json
import logging

from PySide6.QtCore import Signal, Slot

from backend.telegram_login import username_of
from adapters.lm_studio import LlmProviderConfig
from client.bridge.answer import _err, _ok
from client.bridge.bot_stop import stop_bot
from client.bridge.llm import read_llm_creds
from client.bridge.payload import _log_invalid_payload
from client.bridge.wire import _llm_provider_to_dict


logger = logging.getLogger(__name__)


class SettingsSlots:
    """Настройки времени выполнения, какими их правит окно.

    Подмешивающий обязан держать `_rs`, `_bot`, `_bot_task`, `_login`,
    `_username_cache`, `_dispatch` и `_dispatch_noop`.

    SECURITY: `request_system_settings` отдаёт во фронт ключи доступа к
    моделям и `api_hash` Telegram как есть — окно умеет показать их по
    нажатию, а канал живёт только внутри приложения и в сеть не выходит.
    """

    system_settings_loaded = Signal(str)
    settings_save_done = Signal(str)
    system_telegram_logout_done = Signal(str)

    @Slot()
    def request_system_settings(self) -> None:
        """Snapshot of current runtime settings for the Settings screen.

        api_hash отправляем — eye-toggle в UI должен уметь показать значение.
        QWebChannel живёт только в локальном Qt-окне, не уезжает в сеть.
        """
        tg = self._rs.tg
        chat = self._rs.chat
        embed = self._rs.embed
        bot = self._bot

        async def run() -> str:
            client = getattr(bot, "_client", None) if bot is not None else None
            # На холодном старте Pyrogram session-load + connect занимает
            # пару секунд; UI запросит settings раньше. Ждём короткий
            # connect-window (до 3 сек).
            if client is not None and not getattr(client, "is_connected", False):
                for _ in range(15):
                    await asyncio.sleep(0.2)
                    if getattr(client, "is_connected", False):
                        break
            asked = None
            connected = client is not None and getattr(client, "is_connected", False)
            if connected:
                asked = await username_of(client)
                if asked is None:
                    logger.warning("get_me() failed for settings", exc_info=True)
            if asked is None:
                # Спросить не вышло или бот ещё не подключился — отдаём кэш.
                username = self._username_cache
            else:
                # Пустая строка — это ответ «ника нет», и он перебивает кэш:
                # снятый ник иначе остался бы на экране прежним.
                username = asked
                self._username_cache = asked
            return _ok({
                "tg": {
                    "api_id": str(tg.api_id) if tg else "",
                    "api_hash": tg.api_hash if tg else "",
                    "phone": tg.phone if tg else "",
                    "has_password": bool(tg and tg.password),
                    "has_session": bool(tg and tg.session_string),
                    "username": username,
                },
                "chat": _llm_provider_to_dict(chat),
                "embed": _llm_provider_to_dict(embed),
                "pipeline": {
                    "scoring_threshold": self._rs.scoring_threshold,
                    "poll_interval_sec": self._rs.poll_interval_sec,
                    "backfill_limit": self._rs.backfill_limit,
                    "dm_backfill_limit": self._rs.dm_backfill_limit,
                    "send_locked": self._rs.send_locked,
                },
            })

        self._dispatch(self.system_settings_loaded, run())

    @Slot(str)
    def save_settings(self, payload_json: str) -> None:
        """Apply a partial settings patch — autosave из UI на blur/change.

        Payload — словарь с любыми из ключей:
        - chat: {base_url, api_key, model}
        - embed: {base_url, api_key, model}
        - app: {scoring_threshold, poll_interval_sec, backfill_limit,
          dm_backfill_limit, ...}
        Применяем через rs.set_chat / rs.set_embed / rs.set_app. Ошибки
        возвращаем в payload, UI показывает toast.
        """
        try:
            payload = json.loads(payload_json) if payload_json else {}
        except (ValueError, TypeError) as e:
            _log_invalid_payload("save_settings", e)
            self.settings_save_done.emit(_err(f"Неверные поля: {e}"))
            return

        chat = payload.get("chat") if isinstance(payload.get("chat"), dict) else None
        embed = payload.get("embed") if isinstance(payload.get("embed"), dict) else None
        app = payload.get("app") if isinstance(payload.get("app"), dict) else None

        # Читаем до записи и тем же правилом, что проба и мастер: пустое поле
        # почти всегда стёрлось последним переводом фокуса (см. заслоны в
        # main.html). Уйди оно в запись, поставщик пропал бы с экрана целиком —
        # `_from_llm_row` отдаёт `None` на пустоте, — и человек считал бы, что
        # починилось, пока не упал первый разбор вакансии.
        creds: dict[str, LlmProviderConfig] = {}
        for kind_name, payload in (("chat", chat), ("embed", embed)):
            if payload is None:
                continue
            try:
                creds[kind_name] = read_llm_creds(payload)
            except (AttributeError, ValueError, TypeError) as e:
                logger.warning("save_settings: %s refused: %s", kind_name, e)
                self.settings_save_done.emit(_err(f"{kind_name}: {e}"))
                return

        async def run() -> str:
            applied: list[str] = []
            try:
                for kind_name, setter in (
                    ("chat", self._rs.set_chat), ("embed", self._rs.set_embed)
                ):
                    cfg = creds.get(kind_name)
                    if cfg is None:
                        continue
                    await setter(
                        base_url=cfg.base_url, api_key=cfg.api_key, model=cfg.model
                    )
                    applied.append(kind_name)
                if app is not None:
                    # Whitelist: чтобы UI не мог по ошибке/опечатке писать
                    # произвольные ключи в app_settings.
                    allowed = {
                        "scoring_threshold", "poll_interval_sec",
                        "backfill_limit", "dm_backfill_limit",
                        "send_locked",
                    }
                    for key, value in app.items():
                        if key not in allowed:
                            logger.warning("save_settings: unknown app key %r ignored", key)
                            continue
                        # Bool → "true"/"false": app_settings хранит строки,
                        # rs.send_locked парсит обратно в lower-case bool
                        # (см. RuntimeSettings.send_locked). True/False через
                        # str() дали бы "True"/"False" — не пройдут .lower()
                        # сравнение с "true".
                        if isinstance(value, bool):
                            value = "true" if value else "false"
                        await self._rs.set_app(str(key), str(value))
                        applied.append(f"app.{key}")
                    # Sync send_locked в adapters.telegram чтобы новое значение
                    # начало действовать без рестарта бота. Авторитет —
                    # rs.send_locked; константа — кеш для горячего пути отправки.
                    if "send_locked" in app:
                        from adapters import telegram as _tg
                        _tg.SEND_LOCKED = self._rs.send_locked
            except Exception as e:
                logger.exception("save_settings failed")
                return _err(f"{type(e).__name__}: {e}", applied=applied)
            return _ok({"applied": applied})

        self._dispatch(self.settings_save_done, run())

    @Slot()
    def request_telegram_logout(self) -> None:
        """Stop the bot, revoke server-side TG session, clear creds in DB.

        Sequence:
          1. cancel current poll + ask bot to stop (via log_out_session, which
             sends DROP_AUTH then sets stop_event)
          2. wait for the bot run-task to finish (its finally calls
             client.stop() — already disconnected after log_out, no-op)
          3. clear session_string + password in DB so health/UI flip to
             "Нет сессии"
          4. null out _bot/_bot_task — re-login starts a fresh bot
        """
        bot = self._bot
        bot_task = self._bot_task

        async def run() -> str:
            # Если в момент logout открыта модалка re-auth, закрываем её
            # бэкенд-state тоже — иначе при следующем «Войти» налетим на
            # «уже отправили код».
            await self._login.forget()
            await stop_bot(
                bot, bot_task, bot.log_out_session if bot is not None else None
            )
            await self._rs.clear_tg()
            self._username_cache = ""
            return _ok({})

        # Null out before dispatch so concurrent slots don't try to use a
        # half-stopped bot.
        self._bot = None
        self._bot_task = None
        self._dispatch(self.system_telegram_logout_done, run())

    @Slot()
    def cancel_telegram_login(self) -> None:
        """Юзер закрыл модалку re-auth до завершения. Чистим временный
        Pyrogram-клиент и обнуляем OTP-state, чтобы не оставлять открытый
        сокет и не уйти в «уже отправили код» при следующей попытке.
        """
        self._dispatch_noop(self._login.forget())
