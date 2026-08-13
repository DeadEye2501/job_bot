"""Снос всех данных приложения по просьбе из окна."""

from __future__ import annotations

import logging
from concurrent.futures import CancelledError, Future

from PySide6.QtCore import Signal, Slot

from client.bridge.answer import _err, _ok
from backend.crypto import forget_master_key
from backend.wipe import wipe_all
from client.bridge.bot_stop import stop_bot


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
        """Опасная зона → «Удалить всё».

        Слот только просит: останавливает бота, зовёт снос
        (`backend.wipe.wipe_all`), забывает ключ и убивает процесс. Из чего
        состоит каталог данных, он не знает — это дело `config`.

        Следующий запуск уйдёт в мастер: настройки стёрты вместе с базой.
        """
        bot = self._bot
        bot_task = self._bot_task
        # Захватываем сразу, потом null'им — чтобы health-timer не дёрнулся
        # на полу-удалённой базе. И, главное, тут же тушим сами таймеры
        # (здоровье и непрочитанное) — иначе после закрытия движка их
        # следующий удар откроет новое соединение из пула, и Windows
        # откажется удалять файл базы с открытым держателем.
        self._bot = None
        self._bot_task = None
        self._health_timer.stop()
        self._unread_timer.stop()

        async def run() -> str:
            # Беду остановки глотаем: снос обязан дойти до конца, даже если
            # бот уже не отвечает, — иначе останутся и данные, и полуудалённый
            # след.
            try:
                await stop_bot(bot, bot_task)
            except Exception:
                logger.exception("delete_all: bot stop failed")

            errors = await wipe_all(self._engine)
            forget_master_key()
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
            except CancelledError:
                # Отмена наследует BaseException и мимо перехвата ниже прошла
                # бы молча: окно не узнало бы ничего, а приложение не вышло.
                payload = _err("Снос отменён.")
            except Exception as e:
                payload = _err(f"{type(e).__name__}: {e}")
            self.delete_all_data_done.emit(payload)
            import os
            os._exit(0)

        future.add_done_callback(_on_done)
