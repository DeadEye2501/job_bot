"""Фикстуры слоя `backend`, собранные из модулей по предметам.

Своих объявлений здесь нет нарочно: файл дошёл до предела строк, и общему
стенду некуда было ложиться. Pytest ищет фикстуры в пространстве имён
`conftest`, поэтому сборка и состоит из ввозов — предмет каждой группы
назван именем модуля, из которого она приехала.
"""

from tests.backend.fixtures.bot import (
    busy_slot,
    chatting,
    empty_media_dir,
    make_bot,
    outbox,
    ready_to_send,
    sending_unlocked,
)
from tests.backend.fixtures.flows import (
    deliver,
    dm_pipeline,
    make_pipeline,
    parsing,
    unparsed_vacancy,
)
from tests.backend.fixtures.listing import channel_titles, hr_names, titles
from tests.backend.fixtures.logs import clean_root_logger

__all__ = [
    "busy_slot",
    "channel_titles",
    "chatting",
    "clean_root_logger",
    "deliver",
    "dm_pipeline",
    "empty_media_dir",
    "hr_names",
    "make_bot",
    "make_pipeline",
    "outbox",
    "parsing",
    "ready_to_send",
    "sending_unlocked",
    "titles",
    "unparsed_vacancy",
]
