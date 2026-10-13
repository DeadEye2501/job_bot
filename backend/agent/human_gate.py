"""Ожидание человека: капча, слетевший вход или подтверждение отправки. Срок — час
на каждое ожидание."""

import asyncio
import logging
import time
from collections.abc import Callable

from backend.agent.stops import HumanTimeout

logger = logging.getLogger(__name__)

LIMIT_SEC = 3600.0
_DONE = "готово"
_STOPPED = "обход остановлен; заверши работу"


class _NoBrowser:
    """Место браузера у ожидания в окне приложения: выводить и убирать нечего."""

    async def show(self) -> None:
        """Окно подтверждения разворачивает само приложение."""

    async def hide_back(self) -> None:
        """Убирать нечего: вперёд ничего не выводилось."""


_NO_BROWSER = _NoBrowser()


class HumanGate:
    """Пауза откликателя, пока человек не ответит окну, не выйдет срок или обход
    не остановят.

    Капча и вход — ожидание без данных: человек работает в браузере, ответ —
    «готово». Подтверждение — ожидание с данными: человек работает в окне
    приложения, браузер не нужен, ответ — то, что окно вернуло.
    """

    def __init__(self, on_needed: Callable[[str, str, object], None],
                 on_resolved: Callable[[], None], limit_sec: float = LIMIT_SEC) -> None:
        self._on_needed, self._on_resolved = on_needed, on_resolved
        self._limit = limit_sec
        self._done = asyncio.Event()
        self._deadline: float | None = None
        self._answer: object = None
        self._asked: tuple[str, object] | None = None
        self._stopped = False
        self._browser = None
        self._waiting = 0
        # Задачи вывода браузера по нажатию держатся здесь: цикл хранит на задачу
        # только слабую ссылку, и неудержанную сборщик мусора снял бы посреди работы.
        self._showing: set[asyncio.Task] = set()
        self.expired = asyncio.Event()

    async def wait(self, kind: str, host: str, browser=None, payload=None) -> str | dict:
        """Ждать человека. Повторный зов во время ожидания ждёт того же срока.

        Остановка и срок отвечают строкой при любом виде ожидания; ответ окна на
        ожидание с данными возвращается как пришёл.
        """
        if self._stopped:
            return _STOPPED
        browser = _NO_BROWSER if browser is None else browser
        # Взведённое ожидание отвечает только тому же зову: оборванная капча не
        # ответит подтверждению, а прежние пункты — новым.
        if self._deadline is None or self._asked != (kind, payload):
            if not await self._arm(kind, host, browser, payload):
                return _STOPPED
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

    async def ask(self, kind: str, host: str, payload: dict) -> dict | None:
        """Спросить окно приложения: его ответ или пусто, если обход остановили.

        Срок поднимает `HumanTimeout` здесь же: у того, кто ждёт окна без сессии
        агента, некому поднять его выше.
        """
        answer = await self.wait(kind, host, payload=payload)
        if self.expired.is_set():
            raise HumanTimeout
        # Окно отвечает словарём; строкой — только остановка.
        return answer if isinstance(answer, dict) else None

    async def _arm(self, kind: str, host: str, browser, payload) -> bool:
        """Начать ожидание: вывести браузер, взвести срок, позвать человека.
        Ложь — обход остановили, пока браузер поднимался."""
        self._done.clear()
        self._answer = None
        # Срок взводится после показа: не поднявшийся браузер — не начатое
        # ожидание, и повтор должен показать его и позвать человека заново.
        await browser.show()
        # Остановили, пока браузер поднимался: `abort` не застал срока и не
        # разбудил бы это ожидание — оно ждало бы час уже без обхода.
        if self._stopped:
            return False
        self._deadline = time.monotonic() + self._limit
        self._asked = (kind, payload)
        self._on_needed(kind, host, payload)
        return True

    def resolve(self, answer=None) -> None:
        """Ответ окна: галочка на плашке или ответ окна подтверждения. Зовётся
        на цикле бота, а не из потока окна."""
        if self._deadline is not None:
            self._answer = _DONE if answer is None else answer
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

    async def _take(self, browser) -> str | dict:
        """Ответ получает каждый, кого он разбудил, — и вызов, и повтор оборванного:
        ответ лежит до следующего взвода. Браузер прячет первый, второй переноса
        окна не повторяет."""
        first, self._deadline = self._deadline is not None, None
        answer = self._answer
        if first and answer == _DONE:
            # Вывод по нажатию, начатый перед галочкой, кончился бы уже после
            # ухода назад и оставил бы браузер поверх приложения.
            if self._showing:
                await asyncio.wait(set(self._showing))
            await browser.hide_back()
        return answer
