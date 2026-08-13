"""Снос всех данных приложения по просьбе из окна."""

from __future__ import annotations

import asyncio
import logging
from concurrent.futures import Future

from PySide6.QtCore import Signal, Slot

from client.bridge.answer import _err, _ok


logger = logging.getLogger(__name__)


class WipeSlots:
    """Одна кнопка, после которой приложение начинает с чистого листа.

    Подмешивающий обязан держать `_bot`, `_bot_task`, `_engine`, `_runner` и
    оба таймера общего состояния — их приходится остановить до сноса. Ответ
    идёт не через `_dispatch`: работа отправляется на мотор напрямую, потому
    что после неё приложение себя убивает.
    """

    delete_all_data_done = Signal(str)

    @Slot()
    def request_delete_all_data(self) -> None:
        """Опасная зона → «Удалить всё». Останавливает бота, закрывает
        DB-engine, удаляет файлы (jobbot.db + sidecars, sessions/, media/),
        и завершает приложение через QApplication.quit() (юзер сам
        перезапустит — следующий старт уйдёт в визард, т.к. все настройки
        стерты вместе с БД).
        """
        bot = self._bot
        bot_task = self._bot_task
        # Захватываем сразу, потом null'им — чтобы health-timer не дёрнулся
        # на полу-удалённой БД. И, главное, тут же тушим сами таймеры
        # (health/unread) — иначе после engine.dispose() их следующий тик
        # откроет fresh connection из пула и Windows откажется удалять
        # jobbot.db с открытым handle'ом.
        self._bot = None
        self._bot_task = None
        self._health_timer.stop()
        self._unread_timer.stop()

        async def run() -> str:
            import shutil
            from config import get_data_dir
            errors: list[str] = []

            # 1) Стопаем бота — Pyrogram-сессия закроется, файлы освободятся.
            if bot is not None:
                try:
                    bot.cancel_current_poll()
                except Exception:
                    logger.debug("delete_all: cancel_current_poll failed", exc_info=True)
                try:
                    bot.request_stop()
                except Exception:
                    logger.debug("delete_all: request_stop failed", exc_info=True)
            if bot_task is not None:
                try:
                    await asyncio.wait_for(asyncio.wrap_future(bot_task), timeout=10)
                except asyncio.TimeoutError:
                    logger.warning("delete_all: bot did not stop within 10s")
                except Exception:
                    logger.exception("delete_all: bot task raised")

            # 2) Закрываем engine — иначе Windows не даст удалить jobbot.db.
            if self._engine is not None:
                try:
                    await self._engine.dispose()
                except Exception as e:
                    errors.append(f"engine.dispose: {e}")
                    logger.exception("delete_all: engine.dispose failed")

            # 3) Удаляем файлы.
            data_dir = get_data_dir()
            for name in ("jobbot.db", "jobbot.db-shm", "jobbot.db-wal"):
                p = data_dir / name
                if p.exists():
                    try:
                        p.unlink()
                    except Exception as e:
                        errors.append(f"{name}: {e}")
                        logger.exception("delete_all: failed to remove %s", p)
            for sub in ("sessions", "media"):
                d = data_dir / sub
                if d.exists():
                    try:
                        shutil.rmtree(d)
                    except Exception as e:
                        errors.append(f"{sub}/: {e}")
                        logger.exception("delete_all: failed to remove %s", d)

            # 4) Удаляем Fernet master key из OS-keychain'а. Без этого
            # после reinstall'а у юзера висит мёртвая запись в Windows
            # Credential Manager / macOS Keychain — некритично (новый
            # ключ перегенерится), но «delete all» должно быть «delete
            # all», а не «delete most».
            try:
                import keyring as _keyring
                from backend.crypto import (
                    _KEYRING_SERVICE,
                    _KEYRING_KEY,
                )
                _keyring.delete_password(_KEYRING_SERVICE, _KEYRING_KEY)
            except Exception as e:
                # delete_password может бросить если записи нет — это OK.
                logger.debug("delete_all: keyring entry already absent (%s)", e)

            if errors:
                return _err("Не все файлы удалось удалить: " + "; ".join(errors))
            return _ok({})

        # После завершения корутины (успех/ошибка) — эмитим результат и
        # сразу убиваем процесс через os._exit(0). Штатный QApplication.quit()
        # здесь приводит к зависанию: aboutToQuit → api.cleanup() →
        # runner.stop() → gather отменяемых тасков, и какой-то из них
        # натыкается на удалённую sessions/jobbot.db и блокирует unwind.
        # Для «wipe everything» все нужные действия (бот остановлен,
        # engine disposed, файлы удалены) уже сделаны выше — штатный
        # cleanup нам не нужен.
        future = self._runner.submit(run())

        def _on_done(f: Future) -> None:
            try:
                payload = f.result()
            except Exception as e:
                payload = _err(f"{type(e).__name__}: {e}")
            self.delete_all_data_done.emit(payload)
            import os
            os._exit(0)

        future.add_done_callback(_on_done)
