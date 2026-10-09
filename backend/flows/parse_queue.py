"""Очередь разбора вакансий, найденных агентом: разбор идёт рядом с поиском."""

import asyncio
import logging

from backend.flows import parse
from backend.task_stop import put_out

logger = logging.getLogger(__name__)


class ParseQueue:
    """Разбирает по одной в порядке поступления; одна сломанная не держит остальных.

    Разбор — без канала, как у вставленного текста: у найденной страницы его нет.
    """

    def __init__(self, pipeline) -> None:
        self._pipeline = pipeline
        self._items: asyncio.Queue[tuple[int, str]] = asyncio.Queue()
        self._worker = asyncio.create_task(self._work())

    def put(self, vacancy_id: int, text: str) -> None:
        self._items.put_nowait((vacancy_id, text))

    async def drain(self) -> None:
        """Дождаться, пока всё поставленное разобрано."""
        await self._items.join()
        await self.stop()

    async def stop(self) -> None:
        """Бросить недоразобранное."""
        await put_out(self._worker)

    async def _work(self) -> None:
        while True:
            vacancy_id, text = await self._items.get()
            try:
                await parse.parse_and_update_vacancy(self._pipeline, vacancy_id, text, None)
            except Exception:
                logger.exception("разбор найденной вакансии %d не удался", vacancy_id)
            finally:
                self._items.task_done()
