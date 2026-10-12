"""Точка входа с подменёнными шагами запуска — общая двум сторожам.

Смотрят на неё двое: `test_entry_point.py` (порядок шагов, замок, отказы) и
`test_entry_point_log.py` (журнал и необработанные падения). Фикстура одна,
потому что обоим нужно одно — ввезти `main` так, чтобы он не испортил журнал
всему прогону и вернул чужие крючки на место.
"""

import sys
import threading

import pytest


@pytest.fixture
def lock_of_its_own(monkeypatch, tmp_path):
    """Замок единственной копии — в своём каталоге, а не в боевом.

    Боевой лежит рядом с базой человека, и прогон при запущенном приложении
    получал бы отказ запуска вместо проверяемого поведения.

    Ввоз здесь такой же отложенный и по той же причине, что у соседней
    фикстуры: модуль насовсем правит корневой logger.
    """
    import main as module

    monkeypatch.setattr(module, "get_lock_path", lambda: tmp_path / "jobbot.lock")


@pytest.fixture
def entry(clean_root_logger, lock_of_its_own, monkeypatch):
    """Точка входа с подменёнными шагами запуска и возвращённым журналом.

    Ввозится она внутри фикстуры нарочно: при ввозе модуль насовсем правит
    корневой logger — вешает обработчик буфера, фильтр вымарывания секретов
    и меняет уровни навешенных обработчиков, включая тот, которым pytest
    ловит записи. На сборке это испортило бы журнал всему прогону. Тем же
    ввозом подменяются оба крючка на необработанное падение, и один
    из них — свой у pytest: им он ловит падения фоновых потоков и роняет
    тест. Не вернув его, мы сняли бы этого сторожа со всего остального
    набора. А возвращённые, они уже не ставятся заново: ввоз один на весь
    прогон, — поэтому ставим их здесь. Что их ставит сам ввоз, сторожит
    проверка, запускающая приложение подпроцессом.
    """
    hooks = (sys.excepthook, threading.excepthook)
    import main as module

    sys.excepthook = module._log_uncaught
    threading.excepthook = module._log_uncaught_in_thread

    order: list[str] = []

    def check_keyring():
        order.append("хранилище ключей")

    def ensure_schema():
        order.append("схема базы")

    def run_ui():
        order.append("окно")
        return 0

    monkeypatch.setattr(
        "backend.crypto._check_keyring_backend", check_keyring
    )
    monkeypatch.setattr("backend.bootstrap.ensure_schema", ensure_schema)
    # Уборка после обновления смотрела бы рядом с интерпретатором и в настоящей
    # временной папке; её место в запуске сторожит свой тест.
    monkeypatch.setattr("backend.updater.clear_leftovers", lambda: None)
    monkeypatch.setitem(
        sys.modules, "client.window", type("Window", (), {"run_ui": staticmethod(run_ui)})
    )
    yield module, order
    sys.excepthook, threading.excepthook = hooks
