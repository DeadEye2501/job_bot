"""Фикстуры слоя `backend`, собранные из модулей по предметам.

Своих объявлений здесь нет нарочно: файл дошёл до предела строк, и общему
стенду некуда было ложиться. Pytest ищет фикстуры в пространстве имён
`conftest`, поэтому сборка и состоит из ввозов — предмет каждой группы
назван именем модуля, из которого она приехала.
"""

from tests.backend.fixtures.backfill import known_hr
from tests.backend.fixtures.entry import entry, lock_of_its_own
from tests.backend.fixtures.bot import (
    busy_slot,
    chatting,
    chatting_on_fakes,
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
from tests.backend.fixtures.logs import clean_log_file, clean_root_logger
from tests.backend.fixtures.rerun import rerunning
from tests.backend.fixtures.stats import applied

__all__ = [
    "applied",
    "busy_slot",
    "channel_titles",
    "chatting",
    "chatting_on_fakes",
    "clean_log_file",
    "clean_root_logger",
    "deliver",
    "dm_pipeline",
    "empty_media_dir",
    "entry",
    "hr_names",
    "known_hr",
    "lock_of_its_own",
    "make_bot",
    "make_pipeline",
    "outbox",
    "parsing",
    "ready_to_send",
    "rerunning",
    "sending_unlocked",
    "titles",
    "unparsed_vacancy",
]
