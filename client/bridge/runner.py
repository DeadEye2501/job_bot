"""Цикл asyncio в своём потоке, куда поверхность окна отправляет работу."""

from __future__ import annotations

import asyncio
import logging
import sqlite3
import threading
from concurrent.futures import Future
from typing import Any, Coroutine


logger = logging.getLogger(__name__)


class AsyncRunner:
    """Owns an asyncio loop running in a background thread."""

    def __init__(self) -> None:
        self.loop = asyncio.new_event_loop()
        self._thread = threading.Thread(
            target=self._run_loop, daemon=True, name="WizardAsyncLoop"
        )
        self._thread.start()
        logger.info("AsyncRunner started (thread=%s)", self._thread.name)

    def _run_loop(self) -> None:
        asyncio.set_event_loop(self.loop)
        # Pyrogram'ский race во время shutdown / log_out: внутренний таск
        # Client.handle_updates догоняет с update'ом для уже закрытой
        # SQLite-storage / стопнутого loop'а / частично-разобранного
        # клиента. Делать тут нечего — apply'нуть уже не во что,
        # фильтруем шум, чтобы он не прыгал в stderr и не пугал юзера.
        # Помимо ProgrammingError("closed database") глушатся и
        # RuntimeError("Event loop is closed"), и AttributeError на
        # частично-разобранных Pyrogram-объектах при teardown'е.
        def _quiet_pyrogram_shutdown(loop, context):
            exc = context.get("exception")
            msg = str(exc) if exc else ""
            # WARNING (а не DEBUG): если эти исключения всплывают вне
            # shutdown'а — это значит мы где-то закрыли DB-pool / loop
            # рано, и тихий DEBUG это спрячет. WARNING шумит ровно один
            # раз на teardown — приемлемо. Если ловите эти warning'и не
            # при выходе из приложения / log_out / delete_all_data —
            # значит появился реальный bug.
            if isinstance(exc, sqlite3.ProgrammingError) and \
               "closed database" in msg:
                logger.warning("Pyrogram shutdown race swallowed: %s", exc)
                return
            if isinstance(exc, RuntimeError) and \
               "Event loop is closed" in msg:
                logger.warning("Pyrogram shutdown race swallowed: %s", exc)
                return
            if isinstance(exc, AttributeError):
                # AttributeError при teardown'е остаётся DEBUG — самый шумный
                # из трёх (pyrogram дёргает self.<attr> на уже-обнулённом
                # объекте по нескольку раз за teardown). WARNING'и от sqlite3/
                # RuntimeError выше — точечный сигнал «бд/loop закрыты вне
                # shutdown'а», AttributeError диагностически слабее.
                logger.debug("AttributeError during teardown swallowed: %s", exc)
                return
            loop.default_exception_handler(context)
        self.loop.set_exception_handler(_quiet_pyrogram_shutdown)
        self.loop.run_forever()

    def submit(self, coro: Coroutine[Any, Any, Any]) -> Future:
        return asyncio.run_coroutine_threadsafe(coro, self.loop)

    def stop(self) -> None:
        if not self.loop.is_running():
            return
        logger.info("AsyncRunner stopping")
        # Cancel pending tasks so aclose / disconnect handlers в finally
        # блоках Bot.run / IngestionPipeline получают шанс отработать
        # до смерти loop'а. Таймаут расширен с 3с до 15с — Bot.run
        # finally делает `await client.stop()` Pyrogram'а + два
        # `await lm_*.aclose()`, на flaky-сети это легко 5-10с.
        # Раньше cancel_pending уезжал по таймауту и тут же loop.stop()
        # рубил cleanup'ы посередине.
        async def _cancel_pending() -> None:
            tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
            for t in tasks:
                t.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
        try:
            asyncio.run_coroutine_threadsafe(_cancel_pending(), self.loop).result(timeout=15)
        except Exception:
            logger.exception("AsyncRunner: cancel_pending failed during stop")
        self.loop.call_soon_threadsafe(self.loop.stop)
        self._thread.join(timeout=15)
        if self._thread.is_alive():
            logger.warning("AsyncRunner thread did not exit within 15s join timeout")
