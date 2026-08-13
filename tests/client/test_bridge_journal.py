"""Следствия слотов журнала: что человек видит на экране записей.

Предмет — кольцо записей и дорога от него до окна. Само кольцо сторожит
`tests/backend/test_log_buffer.py`; здесь смотрят на то, чего там нет: отбор
по просьбе окна, заминка между запросами и подписка на живой поток.
"""

import json
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


async def test_the_journal_shows_what_was_written(main_api, watch, journal):
    """Записанное сборщиком видно на экране журнала.

    Журнал — единственное место, где человек видит, чем занят бот. Порвись
    дорога от сборщика до окна, экран показывал бы пустоту при работающем
    приложении.
    """
    caught = watch(main_api.system_logs_loaded)
    logging.getLogger("проверка").warning("канал не отвечает")

    main_api.request_system_logs(json.dumps({}))

    answer = await caught.next()
    assert answer["records"][0]["msg"] == "канал не отвечает"


async def test_a_request_too_soon_after_the_last_one_stays_silent(
    main_api, watch, journal
):
    """Запрос, пришедший сразу за прошлым, остаётся без ответа.

    Экран журнала обновляется сам, и без этой заминки мост собирал бы снимок
    кольца по нескольку раз в секунду. Тишина здесь — решение, а не потеря:
    окно рисует по прошлому ответу.

    Отметку прошлого запроса ставим сами, а не полагаемся на то, что два
    вызова подряд уложатся в секунду: на занятой машине они бы не уложились,
    и тест падал бы от чужой нагрузки, а не от поломки. Часы те же, что у
    заслона: разойдись они, отметка стала бы бессмысленной, а проверка —
    зелёной при любом сроке.
    """
    caught = watch(main_api.system_logs_loaded)
    logging.getLogger("проверка").info("раз")
    main_api._logs_request_last_ts = time.monotonic()

    main_api.request_system_logs(json.dumps({}))

    assert await caught.silent()


async def test_a_cleared_journal_comes_back_empty(main_api, watch, journal):
    """После очистки экран журнала пуст.

    Чистят его, чтобы поймать поломку с чистого листа: прогнать заново и
    увидеть только новые записи. Останься старые — вся затея теряет смысл.
    """
    cleared = watch(main_api.system_logs_cleared)
    listed = watch(main_api.system_logs_loaded)
    logging.getLogger("проверка").warning("было")

    main_api.request_system_logs_clear()
    assert (await cleared.next())["ok"] is True

    main_api.request_system_logs(json.dumps({}))
    assert (await listed.next())["records"] == []


async def test_new_records_reach_the_window_only_after_subscribing(
    main_api, watch, journal
):
    """Живой поток записей идёт в окно, только пока экран журнала открыт.

    Каждая запись иначе превращалась бы в сборку строки и отправку через
    канал — на чужих экранах эта работа не нужна никому, а сборщик пишет
    сотнями строк за цикл.
    """
    pushed = watch(main_api.system_log_record_pushed)

    logging.getLogger("проверка").warning("до подписки")
    assert await pushed.silent()

    main_api.set_logs_subscribed(True)
    logging.getLogger("проверка").warning("после подписки")

    assert (await pushed.next())["msg"] == "после подписки"
