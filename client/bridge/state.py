"""Общее состояние окна: режим бота, сбор, здоровье, непрочитанное."""

from __future__ import annotations

import logging

from PySide6.QtCore import Signal, Slot
from sqlalchemy import text as sa_text

from adapters import lm_studio
from backend.models import BotMode
from backend.repository import hr_list, messages as messages_repo
from client.bridge.answer import _err, _ok
from client.bridge.refusals import BUSY_CYCLE


logger = logging.getLogger(__name__)


_HEALTHCHECK_INTERVAL_MS = 5_000
_UNREAD_INTERVAL_MS = 15_000


class WindowStateSlots:
    """То, что окно показывает всегда, на каком бы экране ни стояло.

    Подмешивающий обязан держать `_rs`, `_bot`, `_session_factory` и
    `_dispatch`. Часы, по которым бьются `_kick_health` и `_kick_unread`,
    заводит и останавливает он же: они живут ровно столько, сколько окно. Три
    сигнала о сборе — `ingestion_started`, `ingestion_finished`,
    `progress_update` — объявлены здесь, а испускает их бот, которого поднимает
    подмешивающий: сбор идёт сам по себе, окно на него только смотрит.

    Подмешивающий у примеси один, и второго не будет: канал регистрирует
    ровно один объект «api», так что все предметы окна обязаны сойтись в нём.
    Это разрезание класса на файлы, а не абстракция под будущую замену.
    """

    health_changed = Signal(str)
    unread_changed = Signal(str)
    mode_changed = Signal(str)
    ingestion_started = Signal()
    ingestion_finished = Signal(str)
    ingestion_action_done = Signal(str)
    progress_update = Signal(str)
    unread_chats_loaded = Signal(str)

    @Slot()
    def request_initial(self) -> None:
        """Push every cached state to JS via signals — called once on UI boot."""
        self._kick_health()
        self._kick_unread()
        self._kick_mode()

    @Slot(str)
    def set_mode(self, mode_str: str) -> None:
        try:
            mode = BotMode(mode_str)
        except ValueError:
            logger.warning("set_mode: unknown mode requested: %r", mode_str)
            self.mode_changed.emit(_err(f"Неизвестный режим: {mode_str!r}"))
            return

        logger.info("Mode change requested: %s", mode.value)
        async def run() -> str:
            await self._rs.set_mode(mode)
            # Wake the bot so it picks up the new mode without waiting for
            # the next poll tick.
            if self._bot is not None:
                self._bot.kick()
            return _ok({"mode": mode.value})

        self._dispatch(self.mode_changed, run())

    @Slot()
    def trigger_ingestion(self) -> None:
        """Refresh button — force a one-shot poll regardless of bot mode.

        Если уже идёт другой цикл — показываем toast «уже идёт цикл,
        пропустил», иначе пользователь жмёт кнопку и не понимает почему
        ничего не происходит.
        """
        if self._bot is None:
            return
        logger.info("Manual ingestion triggered")

        async def run() -> str:
            status = await self._bot.force_poll_once()
            if status == "busy":
                return _err(BUSY_CYCLE, action="trigger_ingestion", status=status)
            if status == "ok":
                return _ok({"action": "trigger_ingestion", "status": status})
            messages = {
                "cancelled": "Поллинг отменён.",
                "error": "Не удалось прогнать каналы — см. логи.",
            }
            return _err(messages.get(status, "Не удалось прогнать."), action="trigger_ingestion", status=status)

        self._dispatch(self.ingestion_action_done, run())

    @Slot()
    def stop_ingestion(self) -> None:
        """Stop button — cancel the in-flight poll cycle (if any)."""
        if self._bot is None:
            return
        logger.info("Ingestion cancel requested")
        self._bot.cancel_current_poll()

    def _kick_mode(self) -> None:
        async def run() -> str:
            mode = await self._rs.get_mode()
            return _ok({"mode": mode.value})

        self._dispatch(self.mode_changed, run())

    def _kick_unread(self) -> None:
        async def run() -> str:
            async with self._session_factory() as session:
                count = await messages_repo.count_unread_incoming(session)
            return _ok({"count": count})

        self._dispatch(self.unread_changed, run())

    @Slot()
    def request_unread_chats(self) -> None:
        """List of HRs with at least one unread incoming message — feeds the
        footer pop-up (TODO #4). Ordered by most recent unread first.
        """
        async def run() -> str:
            async with self._session_factory() as session:
                rows = await hr_list.list_hrs_with_unread(session)
            return _ok({"chats": rows})

        self._dispatch(self.unread_chats_loaded, run())

    def _kick_health(self) -> None:
        async def run() -> str:
            results = {"db": False, "tg": False, "chat": False, "embed": False}

            try:
                async with self._session_factory() as session:
                    await session.execute(sa_text("SELECT 1"))
                results["db"] = True
            except Exception as e:
                logger.debug("healthcheck: db probe failed: %s", e)

            # TG: проверяем живость уже работающего Pyrogram-клиента в
            # Bot.run. ``is_connected`` отражает state MTProto-сессии и
            # отваливается, когда Pyrogram'овский heartbeat ловит timeout
            # (≈30-60с после реального отключения сети). Параллельный
            # connect отсюда устроил бы конфликт сессий, поэтому смотрим
            # только на бот'овский клиент. До старта бота (нет
            # session_string или ранний этап init'а) — false: пока сессия
            # не поднята, считать TG здоровым нечестно.
            results["tg"] = bool(
                self._bot is not None
                and self._bot.is_ready
                and getattr(self._bot._client, "is_connected", False)
            )

            if self._rs.chat is not None:
                client = lm_studio.make_client(self._rs.chat)
                try:
                    models = await lm_studio.list_models(client)
                    results["chat"] = self._rs.chat.model in models
                except Exception as e:
                    logger.debug("healthcheck: chat probe failed: %s", e)
                finally:
                    await client.aclose()

            if self._rs.embed is not None:
                client = lm_studio.make_client(self._rs.embed)
                try:
                    models = await lm_studio.list_models(client)
                    results["embed"] = self._rs.embed.model in models
                except Exception as e:
                    logger.debug("healthcheck: embed probe failed: %s", e)
                finally:
                    await client.aclose()

            return _ok(results)

        self._dispatch(self.health_changed, run())
