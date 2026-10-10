"""Страница вакансий одного источника — канала или агрегатора — для его карточки.

Карточки двух источников листают свои вакансии одинаково и различаются только
колонкой ссылки и именем номера в нагрузке; потому слот один на обоих.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from backend.models import Vacancy
from backend.repository import vacancies_mini
from client.bridge.answer import BAD_PAYLOAD, bad_fields, reply
from client.bridge.hub import Hub
from client.bridge.page import Page, read_page
from client.bridge.wire import _vacancy_mini_row_to_dict


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Source:
    """Чем один источник отличается от другого: номер в нагрузке, ссылка, имя слота."""

    key: str
    link: Any
    method: str


CHANNEL = Source("channel_id", Vacancy.source_channel_id, "channels.vacancies")
AGGREGATOR = Source("aggregator_id", Vacancy.source_aggregator_id, "aggregators.vacancies")


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
    from_source = source.link == source_id
    async with hub.session_factory() as session:
        rows, has_more = await vacancies_mini.list_vacancies_from(
            session, from_source, limit=page.limit, offset=page.offset,
        )
        # Жалоба на живую беду: пусто здесь при непустом счёте в карточке.
        # По одному пустому списку не видно, где она — в запросе перечня
        # или в эхе моста; ноль против N различает эти два места.
        if not rows:
            total = await vacancies_mini.count_vacancies_from(session, from_source)
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
