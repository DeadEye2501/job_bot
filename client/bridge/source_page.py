"""Страница вакансий одного источника — канала или агрегатора — для его карточки.

Карточки двух источников листают свои вакансии одинаково и различаются только
родом источника и именем номера в нагрузке; потому слот один на обоих.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from backend.models.settings import AGGREGATOR_KIND, CHANNEL_KIND
from backend.repository import vacancies_mini
from client.bridge.answer import BAD_PAYLOAD, bad_fields, reply
from client.bridge.hub import Hub
from client.bridge.page import Page, read_page
from client.bridge.wire import _vacancy_mini_row_to_dict


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Source:
    """Чем один источник отличается от другого: номер в нагрузке, род, имя слота."""

    key: str
    kind: str
    method: str


CHANNEL = Source("channel_id", CHANNEL_KIND, "channels.vacancies")
AGGREGATOR = Source("aggregator_id", AGGREGATOR_KIND, "aggregators.vacancies")


def source_vacancies(hub: Hub, source: Source, payload: dict) -> dict:
    """Страница вакансий источника по нагрузке `{<номер>, limit, offset}`.

    Дописать пришедшее или заменить показанное, окно решает само.
    """
    try:
        source_id = int(payload[source.key])
        page = read_page(payload, default_limit=50)
    except BAD_PAYLOAD as e:
        return bad_fields(source.method, e)

    return reply(hub.runner, _paged(hub, source, source_id, page))


async def _paged(hub: Hub, source: Source, source_id: int, page: Page) -> dict:
    """Страница вакансий источника и эхо того, о чём спрашивали."""
    async with hub.session_factory() as session:
        rows, has_more = await vacancies_mini.list_vacancies_from(
            session, source.kind, source_id, limit=page.limit, offset=page.offset,
        )
        # Пусто здесь при непустом счёте в карточке — беда, и по одному пустому
        # списку не видно, где она: в запросе перечня или в эхе моста. Ноль
        # против N различает эти два места.
        if not rows:
            total = await vacancies_mini.count_vacancies_from(session, source.kind, source_id)
            if total > 0:
                logger.warning(
                    "%s=%d: перечень вакансий пуст, а строк с этим "
                    "источником %d (потолок=%d сдвиг=%d) — разойтись со "
                    "счётчиком карточки он не должен",
                    source.key, source_id, total, page.limit, page.offset,
                )
    return {
        source.key: source_id,
        "has_more": has_more,
        "vacancies": [_vacancy_mini_row_to_dict(v) for v in rows],
    }
