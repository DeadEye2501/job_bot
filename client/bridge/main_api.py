"""Сборка поверхности основного окна из предметов."""

from __future__ import annotations

import asyncio
import json
import logging
from concurrent.futures import CancelledError, Future
from typing import Any, Coroutine

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtWidgets import (
    QWidget,
)
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from backend.telegram_login import TelegramLogin
from backend.runtime_settings import RuntimeSettings
from client.bridge.bot_stop import stop_bot
from client.bridge.answer import _dispatch_json, _ok
from client.bridge.desktop import DesktopSlots
from client.bridge.hub import Hub
from client.bridge.journal import JournalSlots
from client.bridge.llm import LlmSlots
from client.bridge.login import TelegramLoginSlots
from client.bridge.runner import AsyncRunner
from client.bridge.settings import SettingsSlots
from client.bridge.state import (
    _HEALTHCHECK_INTERVAL_MS,
    _UNREAD_INTERVAL_MS,
    WindowStateSlots,
)
from client.bridge.wipe import WipeSlots


logger = logging.getLogger(__name__)



_CLOSING_WAIT_S = 5.0
"""Сколько закрывающееся окно ждёт остановки бота.

Меньше, чем ждут выход из учётной записи и снос (`bot_stop.STOP_TIMEOUT_S`):
там человек ждёт ответа на нажатие, а здесь смотрит на застывшее окно, которое
уже попросил закрыть. Срок уезжает доводом внутрь, а снаружи остаётся секунда
запаса — на случай, если мотор занят чужой работой.

Зависший обход переживёт оба срока: мотор гасит оболочка следом
(`shell.run_ui`), и хвост подбирает `runner.stop()`.
"""


class MainApi(
    DesktopSlots, JournalSlots, LlmSlots,
    SettingsSlots,
    TelegramLoginSlots,
    WindowStateSlots, WipeSlots,
    QObject,
):
    """Один объект «api», который канал отдаёт основному окну.

    Своих слотов не держит: предметы приходят примесями, а здесь — бот,
    часы общего состояния, отправка работы на мотор и уборка. Пять сигналов
    объявлены тут же, потому что испускает их бот, а не предмет: списки
    контактов, список каналов и список вакансий меняются сами по себе, когда
    сбор находит новое, а письмо от человека и его отметка о прочтении
    приходят от собеседника — их дом, очередь событий, ждёт слайса А2.9.
    """

    contacts_lists_changed = Signal()
    contacts_channels_changed = Signal()
    vacancies_list_changed = Signal()
    contacts_hr_messages_arrived = Signal(str)
    contacts_hr_read_receipt = Signal(str)

    def __init__(
        self,
        rs: RuntimeSettings,
        session_factory: async_sessionmaker,
        runner: AsyncRunner,
        parent_widget: QWidget | None = None,
        engine: AsyncEngine | None = None,
    ) -> None:
        super().__init__()
        self._rs = rs
        self._session_factory = session_factory
        self._runner = runner
        self._parent_widget = parent_widget
        self._engine = engine  # для dispose() в delete_all_data
        self._hub = Hub(runner, session_factory, rs)
        self._bot_task: Future | None = None

        self._health_timer = QTimer(self)
        self._health_timer.timeout.connect(self._kick_health)
        self._health_timer.start(_HEALTHCHECK_INTERVAL_MS)

        self._unread_timer = QTimer(self)
        self._unread_timer.timeout.connect(self._kick_unread)
        self._unread_timer.start(_UNREAD_INTERVAL_MS)

        # Hook log-buffer → Qt signal: each new LogRecord pushed (debounce
        # is on the JS side via existing patterns). Emit must be JSON-string
        # for Signal(str), so serialize the entry inline. Push gated на
        # `_logs_subscribed` flag — ставится из JS при заходе на logs-tab,
        # снимается при уходе/выключении auto-refresh, чтобы не сжигать
        # JSON-сериализацию + cross-thread dispatch на чужих экранах.
        # Вход через экран «Настройки» держит свой временный клиент —
        # отдельный от `self._bot._client`, который стартует позже. Имя
        # сессии тоже своё: под общим они делили бы один файл.
        self._login = TelegramLogin(
            "job_bot_relogin", rs, on_saved=self._after_login_saved
        )
        # Кэш TG-username: бот стартует медленно (Pyrogram session-load
        # + connect — секунды), а UI запрашивает settings сразу после
        # логина или открытия таба. Кэш заполняется при успешном get_me()
        # (или сразу после re-login) и переживает несколько запросов
        # пока bot._client не поднимется.
        self._username_cache: str = ""
        # Лампочка спрашивает модели реже, чем базу и Telegram: вопрос к
        # модели — настоящая генерация, см. `_MODEL_PROBE_INTERVAL_S`.
        self._models_probed_at: float = float("-inf")
        self._models_health_cache: tuple[bool, bool] = (False, False)
        self._models_in_flight = False
        self._logs_subscribed = False
        # Когда журнал спрашивали в прошлый раз — заслон от частых обращений
        # (`journal._LOGS_REQUEST_INTERVAL_S`).
        self._logs_request_last_ts: float = float("-inf")
        from backend.log_buffer import get_handler
        # Recursion-guard: если внутри _on_record логнуть warning, тот warning
        # снова попадёт в LogBufferHandler.emit → on_record → бесконечная
        # рекурсия. Флаг блокирует повторный вход.
        _on_record_in_flight = {"v": False}
        def _on_record(entry: dict) -> None:
            if not self._logs_subscribed:
                return
            try:
                self.system_log_record_pushed.emit(json.dumps(entry))
            except Exception:
                if _on_record_in_flight["v"]:
                    return
                _on_record_in_flight["v"] = True
                try:
                    logger.warning(
                        "LogBuffer on_record callback failed", exc_info=True,
                    )
                finally:
                    _on_record_in_flight["v"] = False
        get_handler().on_record = _on_record

        # Без session_string Pyrogram свалится в interactive-login на stdin
        # (запрашивает код подтверждения в терминале). Бот стартанём только
        # после того, как пользователь авторизуется через UI («Войти»).
        if rs.tg is not None and rs.tg.session_string:
            self._start_bot()
        else:
            logger.info("No TG session — bot start deferred until user logs in via Settings")

    @property
    def _bot(self):
        """Бот лежит в общем хозяйстве, а не здесь.

        Переехавшие домены берут его оттуда же: две ссылки на одного бота
        разъехались бы на первом же перезапуске, и половина поверхности отвечала
        бы «бот ещё не готов» при живом боте.
        """
        return self._hub.bot

    @_bot.setter
    def _bot(self, bot) -> None:
        self._hub.bot = bot

    def _start_bot(self) -> None:
        """Construct AND run the Bot inside the runner loop.

        Constructing on the Qt thread used to crash silently — Pyrogram's
        SQLite session storage is thread-affine, and any exception from
        a coroutine submitted via `submit()` sits in the Future without a
        callback to surface it.
        """
        async def _build_and_run() -> None:
            from backend.bot.client import Bot

            logger.info("Constructing Bot and starting run loop")
            self._bot = Bot(self._rs, self._session_factory)
            def _on_cycle_start() -> None:
                self.ingestion_started.emit()

            def _on_cycle_end() -> None:
                self.ingestion_finished.emit(_ok())
                self._kick_unread()

            self._bot.on_cycle_start = _on_cycle_start
            self._bot.on_cycle_end = _on_cycle_end
            self._bot.on_progress = lambda stage, label, cur, tot: (
                self.progress_update.emit(json.dumps(
                    {"stage": stage, "label": label, "current": cur, "total": tot}
                ))
            )
            def _on_new_msg(hr_id: int) -> None:
                self.contacts_hr_messages_arrived.emit(_ok({"hr_id": hr_id}))
                self._kick_unread()
            self._bot.on_new_message = _on_new_msg

            def _on_hr_read(hr_id: int, max_tg_id: int) -> None:
                self.contacts_hr_read_receipt.emit(_ok({
                    "hr_id": hr_id,
                    "max_tg_id": max_tg_id,
                }))
            self._bot.on_hr_read = _on_hr_read

            def _on_channels_changed() -> None:
                self.contacts_channels_changed.emit()
            self._bot.on_channels_changed = _on_channels_changed

            def _on_contacts_changed() -> None:
                self.contacts_lists_changed.emit()
            self._bot.on_contacts_changed = _on_contacts_changed

            def _on_vacancies_changed() -> None:
                self.vacancies_list_changed.emit()
            self._bot.on_vacancies_changed = _on_vacancies_changed
            await self._bot.run()

        future = self._runner.submit(_build_and_run())

        def _log_if_crashed(f: Future) -> None:
            exc = f.exception()
            if exc is not None:
                logger.critical("Bot crashed — UI is now zombie", exc_info=exc)

        future.add_done_callback(_log_if_crashed)
        self._bot_task = future

    # --- helpers ----------------------------------------------------------

    def _dispatch(self, signal: Signal, coro: Coroutine[Any, Any, Any]) -> None:
        _dispatch_json(self._runner, signal, coro)

    def cleanup(self) -> None:
        """Stop timers + the background bot. Runner shutdown is owned by shell.

        Cancels any in-flight poll cycle BEFORE waiting on the bot task so
        shutdown is fast even mid-Full-cycle (otherwise Qt's main thread
        would freeze for the rest of the channel pull).
        """
        # Ждущие запросы отпускаются сразу: без этого последний из них догорал
        # бы свой срок, держа на себе закрытие приложения.
        self._hub.events.close()
        self._health_timer.stop()
        self._unread_timer.stop()
        if self._bot is not None and self._bot_task is not None:
            # Те же шаги, что у выхода из учётной записи и у сноса данных, —
            # но ждём их отсюда, с окна: `cleanup` идёт по нажатию «закрыть»
            # на потоке Qt, и корутину ему надо отправить на мотор.
            try:
                self._runner.submit(
                    stop_bot(self._bot, self._bot_task, timeout=_CLOSING_WAIT_S)
                ).result(timeout=_CLOSING_WAIT_S + 1)
            except TimeoutError:
                logger.warning(
                    "MainApi cleanup: bot did not stop within %ss",
                    _CLOSING_WAIT_S,
                )
            except Exception:
                logger.exception("MainApi cleanup: bot stop raised on shutdown")

    def _dispatch_noop(self, coro: Coroutine[Any, Any, Any]) -> None:
        """Fire-and-forget: запускаем корутину на runner'е, ошибки в лог.
        Сигнал обратно не нужен — UI закрывает модалку оптимистично.
        """
        future = self._runner.submit(coro)

        def _on_done(f: Future) -> None:
            try:
                f.result()
            except (CancelledError, asyncio.CancelledError):
                pass
            except Exception:
                logger.warning("noop dispatch failed", exc_info=True)

        future.add_done_callback(_on_done)

    def _after_login_saved(self, username: str | None) -> None:
        """Новая сессия сохранена: запомнить ник и поднять бота, если он лежит.

        Не спросившийся ник (`None`) прежний в кэше не трогает: показать
        старый вернее, чем стереть его до первого удачного `get_me` у бота.
        """
        if username is not None:
            self._username_cache = username
        if self._bot is None:
            self._start_bot()

