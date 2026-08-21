"""Следствия кольца записей, которое показывает окну экран «Логи».

Кольцо держит записи в памяти по уровням, и предел у каждого уровня свой:
поток отладки не вымывает единственную ошибку, ради которой экран и открывают.

Соседи по слою — свои: вымарывание секретов смотрит `test_log_secrets.py`,
файл журнала и его поворот — `test_log_file.py`.
"""

import logging

from backend.log_buffer import LEVEL_LIMITS, LogBufferHandler, install
from tests.backend.fixtures.logs import record


def test_a_record_lands_in_the_snapshot_with_level_and_source():
    """Запись попадает в срез с уровнем и источником."""
    handler = LogBufferHandler()

    handler.emit(record("сообщение", name="backend.проверка", level=logging.WARNING))

    entry = handler.snapshot()[-1]
    assert entry["msg"] == "сообщение"
    assert entry["level"] == "WARNING"
    assert entry["source"] == "backend.проверка"


def test_records_are_numbered_consecutively():
    """Записи нумеруются подряд, номер не повторяется."""
    handler = LogBufferHandler()

    handler.emit(record("первая"))
    handler.emit(record("вторая"))

    assert [e["id"] for e in handler.snapshot()] == [1, 2]


def test_a_level_stays_bounded_and_drops_its_own_oldest():
    """Журнал уровня не растёт за свой предел и теряет свои самые старые.

    Пределы у уровней разные, и отладочному отведено втрое больше: он идёт
    потоком — сотни строк за обход, — а предупреждение случается по делу.
    """
    handler = LogBufferHandler()

    for i in range(LEVEL_LIMITS["WARNING"] + 10):
        handler.emit(record(f"запись {i}", level=logging.WARNING))

    kept = handler.snapshot()
    assert len(kept) == LEVEL_LIMITS["WARNING"]
    assert kept[0]["msg"] == "запись 10"


def test_a_flood_of_debug_does_not_wash_out_an_error():
    """Поток отладочных записей не смывает ошибку.

    Ради этого журналы и разделены. Отладка идёт сотнями строк за обход, и в
    общем кольце она вытесняла ровно то, ради чего журнал открывают: человек
    видел поломку, шёл разбираться — а к его приходу строки о ней уже не было.
    """
    handler = LogBufferHandler()
    handler.emit(record("сломалось", level=logging.ERROR))

    for n in range(LEVEL_LIMITS["DEBUG"] * 2):
        handler.emit(record(f"шум {n}", level=logging.DEBUG))

    kept = handler.snapshot()
    assert [row["msg"] for row in kept if row["level"] == "ERROR"] == ["сломалось"]
    # И сама отладка свой предел держит: без этого «не смыло ошибку» прошло бы
    # и у кольца, которое не выбрасывает ничего и растёт до конца работы.
    assert len([row for row in kept if row["level"] == "DEBUG"]) == LEVEL_LIMITS["DEBUG"]


def test_the_page_mixes_the_levels_in_the_order_they_happened():
    """Без отбора записи идут вперемешку, в порядке случившегося.

    Журналы у уровней свои, а лента у человека одна: разложи мы её по уровням,
    из неё пропало бы главное — что за чем шло. Свежие сверху, как и прежде.
    """
    handler = LogBufferHandler()
    handler.emit(record("первая", level=logging.INFO))
    handler.emit(record("вторая", level=logging.ERROR))
    handler.emit(record("третья", level=logging.DEBUG))

    page = handler.page()

    assert [row["msg"] for row in page["records"]] == ["третья", "вторая", "первая"]
    assert page["total"] == 3


def test_a_critical_record_shares_the_bounds_of_an_error():
    """`CRITICAL` живёт в журнале ошибок, а не своим.

    Окно рисует их одной пилюлей и одним цветом; заведи мы им отдельный
    предел, число в пилюле перестало бы отвечать за строки под ней.
    """
    handler = LogBufferHandler()

    for n in range(LEVEL_LIMITS["ERROR"] + 10):
        handler.emit(record(f"беда {n}", level=logging.CRITICAL))

    assert len(handler.snapshot()) == LEVEL_LIMITS["ERROR"]
    assert handler.page()["level_counts"]["ERROR"] == LEVEL_LIMITS["ERROR"]


def test_clearing_returns_the_count_and_empties_every_level():
    """Очистка возвращает число убранного и опустошает все четыре кольца.

    Записи разных уровней нарочно: чистка обходит кольца по одному, и забудь
    она хоть одно — экран после «очистить» показывал бы прежние строки, ради
    чего чистку и жмут.
    """
    handler = LogBufferHandler()
    handler.emit(record("сведение"))
    handler.emit(record("предупреждение", level=logging.WARNING))
    handler.emit(record("беда", level=logging.ERROR))
    handler.emit(record("отладка", level=logging.DEBUG))

    assert handler.clear() == 4
    assert handler.snapshot() == []


def test_the_subscriber_receives_every_record():
    """Подписчик получает каждую запись."""
    handler = LogBufferHandler()
    seen: list[dict] = []
    handler.on_record = seen.append

    handler.emit(record("сообщение"))

    assert [e["msg"] for e in seen] == ["сообщение"]


def test_a_failing_subscriber_does_not_stop_buffering():
    """Упавший подписчик не мешает записи попасть в буфер."""
    handler = LogBufferHandler()

    def failing_subscriber(entry):
        raise RuntimeError("подписчик сломался")

    handler.on_record = failing_subscriber

    handler.emit(record("сообщение"))

    assert handler.snapshot()[-1]["msg"] == "сообщение"


def test_a_failing_subscriber_is_reported_and_not_swallowed(clean_log_file):
    """Об упавшем подписчике сообщается, а не молчится.

    Записать беду обычным путём тут нельзя — это сам обработчик логов, и
    запись из него ушла бы по кругу. Штатный для такого `handleError`
    печатает в поток ошибок, а в оконной сборке его нет вовсе — поэтому
    сообщается прямо в файл журнала, мимо логирования.
    """
    handler = LogBufferHandler()

    def failing_subscriber(entry):
        raise RuntimeError("подписчик сломался")

    handler.on_record = failing_subscriber

    handler.emit(record("сообщение"))

    assert "подписчик сломался" in clean_log_file.read_text(encoding="utf-8")


def test_a_traceback_lands_in_the_details():
    """Трассировка попадает в подробности записи."""
    import sys

    handler = LogBufferHandler()
    handler.setFormatter(logging.Formatter("%(message)s"))
    try:
        raise ValueError("сломалось")
    except ValueError:
        entry = logging.LogRecord(
            name="проверка", level=logging.ERROR, pathname=__file__, lineno=1,
            msg="упало", args=(), exc_info=sys.exc_info(),
        )
        handler.emit(entry)

    assert "ValueError: сломалось" in handler.snapshot()[-1]["details"]


def test_a_record_without_an_exception_has_no_details():
    """У записи без исключения подробностей нет."""
    handler = LogBufferHandler()

    handler.emit(record("сообщение"))

    assert handler.snapshot()[-1]["details"] is None


def test_install_attaches_the_handler_and_lets_debug_through(clean_root_logger):
    """Установка вешает обработчик и пропускает отладочные записи."""
    clean_root_logger.setLevel(logging.INFO)

    handler = install()
    logging.getLogger("backend.проверка").debug("отладочное")

    assert handler in clean_root_logger.handlers
    assert handler.snapshot()[-1]["msg"] == "отладочное"


def test_installing_twice_attaches_one_handler(clean_root_logger):
    """Повторная установка не вешает второй обработчик."""
    from backend.log_buffer import get_handler

    install()
    install()

    assert clean_root_logger.handlers.count(get_handler()) == 1


def test_a_critical_record_is_counted_as_an_error():
    """Записи `CRITICAL` считаются ошибками, а не отдельной породой.

    Окно рисует их одним цветом и одной пилюлей: заведи счёт отдельно —
    человек увидел бы «ошибок: 0» рядом с красной строкой и решил бы, что
    счётчик врёт.
    """
    handler = LogBufferHandler()
    handler.emit(record("обычная беда", level=logging.ERROR))
    handler.emit(record("беда пострашнее", level=logging.CRITICAL))

    counts = handler.page()["level_counts"]

    assert counts["ERROR"] == 2
    assert "CRITICAL" not in counts


def test_the_page_gives_all_the_rings_hold():
    """Страница отдаёт всё, что лежит в кольцах, и ни строкой меньше.

    Отбор по уровню окно делает у себя: обрежь мы страницу — пилюля обещала бы
    записи, которых человеку не достать ничем. Потолок ответа держат сами
    кольца, и другого потолка здесь нет.

    Наполняем два кольца, а не одно: на одном «потолка нет» не отличалось бы от
    потолка страницы в тот же предел кольца.
    """
    handler = LogBufferHandler()
    for n in range(LEVEL_LIMITS["INFO"] + 200):
        handler.emit(record(f"сведение {n}"))
    for n in range(LEVEL_LIMITS["ERROR"] + 200):
        handler.emit(record(f"беда {n}", level=logging.ERROR))

    page = handler.page()

    together = LEVEL_LIMITS["INFO"] + LEVEL_LIMITS["ERROR"]
    assert len(page["records"]) == together
    assert page["total"] == together
    assert page["level_counts"] == {
        "INFO": LEVEL_LIMITS["INFO"],
        "ERROR": LEVEL_LIMITS["ERROR"],
    }
