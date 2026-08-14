"""Следствия домена журнала: что человек видит на экране записей.

Предмет — кольцо записей и дорога от него до страницы. Само кольцо сторожит
`tests/backend/test_log_buffer.py`; здесь смотрят на то, чего там нет: страницу
по просьбе, заминку между запросами и подписку на живой поток.
"""

import logging
import time

import pytest

from backend.log_buffer import get_handler


@pytest.fixture
def journal():
    """Ставит кольцо журнала на корневой сборщик, как это делает запуск.

    В боевом коде связку собирает точка входа; стенд её не поднимает, и без
    подмены в кольцо не попало бы ни одной записи. Кольцо общее на процесс,
    поэтому снимается и чистится через `finally` — упади тест посередине, оно
    осталось бы висеть на сборщике и ловить чужие записи до конца прогона.
    """
    handler = get_handler()
    root = logging.getLogger()
    previous = root.level
    handler.clear()
    root.addHandler(handler)
    root.setLevel(logging.DEBUG)
    try:
        yield handler
    finally:
        root.removeHandler(handler)
        root.setLevel(previous)
        handler.clear()


async def test_the_journal_shows_what_was_written(api, ask, journal):
    """Записанное сборщиком видно на экране журнала.

    Журнал — единственное место, где человек видит, чем занят бот. Порвись
    дорога от сборщика до страницы, экран показывал бы пустоту при работающем
    приложении.
    """
    logging.getLogger("проверка").warning("канал не отвечает")

    answer = await ask(api.system.logs, {})

    assert answer["ok"]["records"][0]["msg"] == "канал не отвечает"


async def test_a_request_too_soon_after_the_last_one_is_refused(api, ask, journal):
    """Запрос, пришедший сразу за прошлым, отбивают.

    Экран журнала обновляется сам, и без этой заминки мост собирал бы снимок
    кольца по нескольку раз в секунду. Отказ здесь — решение, а не потеря:
    страница рисует по прошлому ответу.

    Отметку прошлого запроса ставим сами, а не полагаемся на то, что два
    вызова подряд уложатся в секунду: на занятой машине они бы не уложились,
    и тест падал бы от чужой нагрузки, а не от поломки. Часы те же, что у
    заслона: разойдись они, отметка стала бы бессмысленной, а проверка —
    зелёной при любом сроке.
    """
    logging.getLogger("проверка").info("раз")
    api.system._logs_asked_at = time.monotonic()

    answer = await ask(api.system.logs, {})

    assert answer["fail"] == "denied"


async def test_a_cleared_journal_comes_back_empty(api, ask, journal):
    """После очистки экран журнала пуст.

    Чистят его, чтобы поймать поломку с чистого листа: прогнать заново и
    увидеть только новые записи. Останься старые — вся затея теряет смысл.
    """
    logging.getLogger("проверка").warning("было")

    cleared = await ask(api.system.clear_logs)
    assert cleared["ok"]["cleared"] >= 1

    listed = await ask(api.system.logs, {})
    assert listed["ok"]["records"] == []


async def test_new_records_reach_the_queue_only_after_subscribing(
    api, ask, hub, journal
):
    """Живой поток записей идёт в очередь, только пока экран журнала открыт.

    Каждая запись иначе превращалась бы в событие — на чужих экранах эта
    работа не нужна никому, а сборщик пишет сотнями строк за обход.
    """
    logging.getLogger("проверка").warning("до подписки")
    assert (await hub.events.take(after=0, timeout=0.01))["events"] == []

    await ask(api.system.watch_logs, True)
    logging.getLogger("проверка").warning("после подписки")

    news = await hub.events.take(after=0, timeout=0.01)
    assert [one["payload"]["msg"] for one in news["events"]] == ["после подписки"]
