"""Сборка поверхности основного окна из предметов."""

from __future__ import annotations

import logging
from concurrent.futures import Future

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtWidgets import (
    QWidget,
)
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from backend.telegram_login import TelegramLogin
from backend.runtime_settings import RuntimeSettings
from client.bridge.bot_stop import stop_bot
from client.bridge.answer import _ok
from client.bridge.hub import Hub
from client.bridge.runner import AsyncRunner
from client.bridge.state import System


logger = logging.getLogger(__name__)


_HEALTHCHECK_INTERVAL_MS = 5_000
_UNREAD_INTERVAL_MS = 15_000
"""Часы окна: как часто оно само спрашивало здоровье и непрочитанное.

Живут здесь, а не у домена, потому что уходят вместе с окном: страница
спрашивает и то и другое своим чередом, а не ждёт толчка по чужим часам.
"""

_CLOSING_WAIT_S = 5.0
"""Сколько закрывающееся окно ждёт остановки бота.

Меньше, чем ждут выход из учётной записи и снос (`bot_stop.STOP_TIMEOUT_S`):
там человек ждёт ответа на нажатие, а здесь смотрит на застывшее окно, которое
уже попросил закрыть. Срок уезжает доводом внутрь, а снаружи остаётся секунда
запаса — на случай, если мотор занят чужой работой.

Зависший обход переживёт оба срока: мотор гасит оболочка следом
(`shell.run_ui`), и хвост подбирает `runner.stop()`.
"""


class MainApi(QObject):
    """Один объект «api», который канал отдаёт основному окну.

    Слотов у него больше нет вовсе: домены переехали на поверхность возврата
    (`api.Api`), и здесь остались бот, часы окна, отправка работы на мотор и
    уборка. Уходит это второй половиной слайса А2.9, вместе с самим каналом.

    Пять сигналов объявлены тут же, потому что испускает их бот, а не предмет:
    списки контактов, каналов и вакансий меняются сами по себе, когда сбор
    находит новое, а письмо от человека и его отметка о прочтении приходят от
    собеседника.
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
        self._hub = Hub(runner, session_factory, rs)
        # Доводом от оболочки; сносу без него не удалить базу.
        self._hub.engine = engine
        self._bot_task = None
        # Рука для часов и для обратных вызовов бота: считать здоровье и
        # непрочитанное умеет домен, а окно только бьёт по нему своим ритмом.
        # Уходит вместе с часами, второй половиной слайса.
        self._system = System(self._hub)

        self._health_timer = QTimer(self)
        self._health_timer.timeout.connect(
            lambda: self._tick(self._system.push_health())
        )
        self._health_timer.start(_HEALTHCHECK_INTERVAL_MS)

        self._unread_timer = QTimer(self)
        self._unread_timer.timeout.connect(
            lambda: self._tick(self._system.push_unread())
        )
        self._unread_timer.start(_UNREAD_INTERVAL_MS)

        # Вход кладётся в хозяйство, как до него бот: заводит его окно, а
        # спрашивает переехавший домен настроек.
        #
        # Клиент у него свой, временный — отдельный от того, что поднимает бот
        # позже. Имя сеанса тоже своё: под общим они делили бы один файл.
        self._hub.login = TelegramLogin(
            "job_bot_relogin", rs, on_saved=self._after_login_saved
        )
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

    @property
    def _bot_task(self) -> Future | None:
        """Работа бота лежит там же, где он сам, и по той же причине.

        Останавливают его три дороги, и одна из них — выход из учётной записи —
        уже переехала в домен настроек. Разъедься эти две ссылки, выход дождался
        бы не той работы, а то и вовсе никакой.
        """
        return self._hub.bot_task

    @_bot_task.setter
    def _bot_task(self, task: Future | None) -> None:
        self._hub.bot_task = task

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
                self._hub.events.add("ingestion_started")

            def _on_cycle_end() -> None:
                self._hub.events.add("ingestion_finished")
                self._tick(self._system.push_unread())

            self._bot.on_cycle_start = _on_cycle_start
            self._bot.on_cycle_end = _on_cycle_end
            self._bot.on_progress = lambda stage, label, cur, tot: (
                self._hub.events.add(
                    "progress_update",
                    {"stage": stage, "label": label, "current": cur, "total": tot},
                )
            )
            def _on_new_msg(hr_id: int) -> None:
                self.contacts_hr_messages_arrived.emit(_ok({"hr_id": hr_id}))
                self._tick(self._system.push_unread())
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

    def _tick(self, coro) -> None:
        """Отправить на мотор работу, у которой нет ответа окну.

        Своё она кладёт в очередь событий, а вот поломка без этой строки
        осталась бы лежать в `Future`, которую никто не читает: часы били бы
        впустую, и ни лампочка, ни счётчик об этом не сказали бы.
        """
        if self._hub.wiping:
            # Снос идёт: базы, к которой они ходят, вот-вот не станет.
            coro.close()
            return
        self._runner.submit(coro).add_done_callback(_log_if_broken)

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

    def _after_login_saved(self, username: str | None) -> None:
        """Новая сессия сохранена: запомнить ник и поднять бота, если он лежит.

        Не спросившийся ник (`None`) прежний в кэше не трогает: показать
        старый вернее, чем стереть его до первого удачного `get_me` у бота.
        """
        if username is not None:
            self._hub.username_cache = username
        if self._bot is None:
            self._start_bot()


def _log_if_broken(future: Future) -> None:
    """Сказать в журнал о работе часов, которая сорвалась.

    Отмену пропускаем: её приносит остановка мотора при закрытии окна, и
    жаловаться на неё значит писать беду о штатном выходе.
    """
    if future.cancelled():
        return
    error = future.exception()
    if error is not None:
        logger.error("часы окна: работа сорвалась", exc_info=error)
