"""Ожидание человека: капча или слетевший вход. Срок — час на каждое ожидание."""

import asyncio
import time
from collections.abc import Callable

LIMIT_SEC = 3600.0
_STOPPED = "обход остановлен; заверши работу"


class HumanGate:
    """Пауза агента, пока человек не нажмёт «Готово», не выйдет срок или обход не остановят."""

    def __init__(self, on_needed: Callable[[str, str], None], on_resolved: Callable[[], None],
                 limit_sec: float = LIMIT_SEC) -> None:
        self._on_needed, self._on_resolved = on_needed, on_resolved
        self._limit = limit_sec
        self._done = asyncio.Event()
        self._deadline: float | None = None
        self._answer: str | None = None
        self._stopped = False
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
        try:
            await asyncio.wait_for(self._done.wait(), max(self._deadline - time.monotonic(), 0))
        except TimeoutError:
            self.expired.set()
            return "срок вышел; заверши работу"
        return await self._take(browser)

    def resolve(self) -> None:
        """«Готово» из окна. Зовётся на цикле бота, а не из потока окна."""
        if self._deadline is not None:
            self._answer = "готово"
            self._done.set()
            self._on_resolved()

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
            return "готово"
        if answer == "готово":
            await browser.hide_back()
        return answer
