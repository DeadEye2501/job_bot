"""Фикстуры слоя `backend`, собранные из модулей по предметам.

Своих объявлений здесь нет нарочно: файл дошёл до предела строк, и общему
стенду некуда было ложиться. Pytest ищет фикстуры в пространстве имён
`conftest`, поэтому сборка и состоит из ввозов — предмет каждой группы
назван именем модуля, из которого она приехала.
"""

from tests.backend.fixtures.aggregators import web_search
from tests.backend.fixtures.applying import (
    board,
    kit,
    kit_with,
    mail_case,
    manual_case,
    telegram_case,
    two_vacancies,
)
from tests.backend.fixtures.backfill import known_hr
from tests.backend.fixtures.entry import entry, lock_of_its_own
from tests.backend.fixtures.bot import (
    busy_slot,
    caught_up,
    chatting,
    chatting_on_fakes,
    empty_media_dir,
    make_bot,
    outbox,
    ready_to_send,
    sending_unlocked,
    turn_and_settle,
)
from tests.backend.fixtures.flows import (
    deliver,
    dm_pipeline,
    make_pipeline,
    one_vector,
    parsing,
    silent_embedder,
    unparsed_vacancy,
)
from tests.backend.fixtures.listing import channel_titles, hr_names, titles
from tests.backend.fixtures.logs import clean_log_file, clean_root_logger
from tests.backend.fixtures.rerun import rerunning
from tests.backend.fixtures.stats import applied

__all__ = [
    "applied",
    "board",
    "busy_slot",
    "caught_up",
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
    "kit",
    "kit_with",
    "known_hr",
    "lock_of_its_own",
    "make_bot",
    "mail_case",
    "make_pipeline",
    "manual_case",
    "one_vector",
    "outbox",
    "parsing",
    "ready_to_send",
    "rerunning",
    "sending_unlocked",
    "silent_embedder",
    "telegram_case",
    "titles",
    "turn_and_settle",
    "two_vacancies",
    "unparsed_vacancy",
    "web_search",
]
