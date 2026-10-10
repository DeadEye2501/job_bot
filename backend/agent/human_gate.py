"""Ожидание человека: капча или слетевший вход. Срок — час на каждое ожидание."""

import asyncio
import logging
import time
from collections.abc import Callable

logger = logging.getLogger(__name__)

LIMIT_SEC = 3600.0
_DONE = "готово"
_STOPPED = "обход остановлен; заверши работу"


class HumanGate:
    """Пауза агента, пока человек не отметит галочкой на плашке окна, что справился,
    не выйдет срок или обход не остановят."""

    def __init__(self, on_needed: Callable[[str, str], None], on_resolved: Callable[[], None],
                 limit_sec: float = LIMIT_SEC) -> None:
        self._on_needed, self._on_resolved = on_needed, on_resolved
        self._limit = limit_sec
        self._done = asyncio.Event()
        self._deadline: float | None = None
        self._answer: str | None = None
        self._stopped = False
        self._browser = None
        self._waiting = 0
        # Задачи вывода браузера по нажатию держатся здесь: цикл хранит на задачу
        # только слабую ссылку, и неудержанную сборщик мусора снял бы посреди работы.
        self._showing: set[asyncio.Task] = set()
        self.expired = asyncio.Event()

    async def wait(self, kind: str, host: str, browser) -> str:
        """Ждать человека. Повторный зов во время ожидания ждёт того же срока."""
        if self._stopped:
            return _STOPPED
        if self._deadline is None:
            # Срок взводится после показа: не поднявшийся браузер — не начатое
            # ожидание, и повтор должен показать его и позвать человека заново.
            self._done.clear()
            await browser.show()
            # Остановили, пока браузер поднимался: `abort` не застал срока и не
            # разбудил бы это ожидание — оно ждало бы час уже без обхода.
            if self._stopped:
                return _STOPPED
            self._deadline = time.monotonic() + self._limit
            self._on_needed(kind, host)
        # Ждут ли сейчас, считается по живым вызовам, а не по сроку: срок
        # переживает оборванный вызов ради повтора, а браузер к этому мигу работа
        # агента уже могла закрыть — нажатие подняло бы его заново.
        self._waiting += 1
        self._browser = browser
        try:
            await asyncio.wait_for(self._done.wait(), max(self._deadline - time.monotonic(), 0))
        except TimeoutError:
            self.expired.set()
            return "срок вышел; заверши работу"
        finally:
            self._waiting -= 1
        return await self._take(browser)

    def resolve(self) -> None:
        """Галочка на плашке окна. Зовётся на цикле бота, а не из потока окна."""
        if self._deadline is not None:
            self._answer = _DONE
            self._done.set()
            self._on_resolved()

    def reveal(self) -> None:
        """Нажатие на плашку: снова вывести вперёд браузер, на котором ждут человека.

        Зовётся на цикле бота. Никто не ждёт — браузер уже у следующего шага агента
        или закрыт, и трогать его незачем.
        """
        if self._waiting:
            task = asyncio.create_task(self._show(self._browser))
            self._showing.add(task)
            task.add_done_callback(self._showing.discard)

    async def _show(self, browser) -> None:
        # Зов пришёл из окна, ответа никто не ждёт: неподнявшийся браузер иначе
        # пропал бы молча вместе с задачей.
        try:
            await browser.show()
        except Exception:
            logger.exception("браузер не вышел вперёд по нажатию на плашку")

    def abort(self) -> None:
        """Обход остановлен: ждущий вызов возвращается сразу, а не через час.

        Остановка держится до `reset`: остановили, пока агент ничего не ждал, —
        его следующий зов вернётся сразу, а не займёт место прогона на срок.
        """
        self._stopped = True
        if self._deadline is not None:
            self._answer = _STOPPED
            self._done.set()

    def reset(self) -> None:
        """К новой работе агента: прежние срок и остановка касались прошлой."""
        self._deadline, self._answer = None, None
        self._stopped = False
        self._done.clear()
        self.expired.clear()

    async def _take(self, browser) -> str:
        """Ответ забирает один вызов; он же прячет браузер — второй ожидавший
        повтор оборванного вызова получает «готово» без второго переноса окна."""
        answer, self._answer = self._answer, None
        self._deadline = None
        if answer is None:
            return _DONE
        if answer == _DONE:
            # Вывод по нажатию, начатый перед галочкой, кончился бы уже после
            # ухода назад и оставил бы браузер поверх приложения.
            if self._showing:
                await asyncio.wait(set(self._showing))
            await browser.hide_back()
        return answer
