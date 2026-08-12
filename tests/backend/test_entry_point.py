"""Следствия запуска приложения из единственной точки входа.

Порядок трёх шагов здесь не случаен и весь про то, чтобы не потерять данные.
Хранилище ключей проверяется первым: с небезопасным или сломанным секреты
уходят на диск открытым текстом либо теряются после первого же запуска — окно
поднимать уже поздно, и отказ выходит текстом в поток ошибок.

Схема базы обновляется вторым, до окна: обновление поднимает собственный цикл
событий, и внутри чужого оно не запустится.

Отказ на первом шаге даёт свой код возврата, отличный от обычного: запуск из
командной строки должен уметь отличить «не смог начать» от «отработал и
вышел».
"""

import logging
import os
import subprocess
import sys
import threading
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


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
    monkeypatch.setitem(
        sys.modules, "client.shell", type("Shell", (), {"run_ui": staticmethod(run_ui)})
    )
    yield module, order
    sys.excepthook, threading.excepthook = hooks


def test_the_launch_goes_through_all_three_steps(entry):
    """Запуск проходит проверку ключей, схему базы и открывает окно."""
    module, order = entry

    assert module.main() == 0
    assert order == ["хранилище ключей", "схема базы", "окно"]


def test_the_schema_is_updated_before_the_window(entry):
    """Схема базы обновляется до окна.

    Обновление поднимает собственный цикл событий; внутри уже
    запущенного оконного цикла оно не стартует вовсе.
    """
    module, order = entry

    module.main()

    assert order.index("схема базы") < order.index("окно")


def test_a_second_copy_does_not_start(entry, capsys):
    """Вторая копия не запускается и говорит об этом человеку.

    Замок берётся до всех шагов: обе копии делят файл журнала, а тот
    поворачивается переименованием — после первой же ротации одна из копий
    пишет в переименованный файл, который сотрут следующей.

    Код возврата свой: запускающему из командной строки «уже запущено» — не то
    же, что «отработал и вышел», и не то же, что сломанное хранилище ключей.
    """
    module, order = entry
    from backend.single_instance import hold_the_only_copy

    first = hold_the_only_copy(module.get_lock_path())

    assert module.main() == 3
    assert order == []
    assert "уже запущено" in capsys.readouterr().err

    first.close()


def test_the_lock_is_let_go_when_the_window_closes(entry):
    """Закрытое окно замок отпускает.

    Иначе второй запуск после штатного выхода упирался бы в самого себя —
    замок сняла бы только перезагрузка.
    """
    module, _ = entry
    from backend.single_instance import hold_the_only_copy

    module.main()

    after_the_window = hold_the_only_copy(module.get_lock_path())

    assert after_the_window is not None
    after_the_window.close()


def test_a_broken_key_store_stops_the_launch(entry, monkeypatch, capsys):
    """Небезопасное хранилище ключей запуск останавливает.

    С ним секреты ушли бы на диск открытым текстом. Окна ещё нет, и
    показать беду можно только текстом в поток ошибок.
    """
    module, order = entry

    def refuse():
        raise RuntimeError("хранилище пишет пароли открытым текстом")

    monkeypatch.setattr("backend.crypto._check_keyring_backend", refuse)

    assert module.main() == 2
    assert order == []
    assert "хранилище пишет пароли открытым текстом" in capsys.readouterr().err


def test_the_window_return_code_is_passed_through(entry, monkeypatch):
    """Код возврата окна передаётся наружу как есть.

    По нему запускающий отличает нормальный выход от аварийного.
    """
    module, _ = entry
    monkeypatch.setitem(
        sys.modules,
        "client.shell",
        type("Shell", (), {"run_ui": staticmethod(lambda: 3)}),
    )

    assert module.main() == 3


def test_a_console_that_refuses_utf8_is_reported(entry, monkeypatch, capsys):
    """Отказ консоли перейти на UTF-8 показывается, а не проглатывается."""
    module, _ = entry

    def refuses(**_kwargs):
        raise OSError("консоль не отдаёт кодировку")

    # Подменяется один вызов, а не весь поток вывода: подмена потока пережила
    # бы тест и оставила бы прогон писать в мёртвый буфер.
    monkeypatch.setattr(sys.stdout, "reconfigure", refuses, raising=False)

    module._use_utf8_stdout()

    assert "консоль не отдаёт кодировку" in capsys.readouterr().err


def _write_through(module, text: str) -> str:
    """Провести запись через обработчики журнала и вернуть содержимое файла.

    Обработчики берутся у самого модуля, а не у корневого logger'а:
    `basicConfig` на прогоне ничего не вешает — под pytest у корневого уже
    стоят свои обработчики, и он выходит ни с чем. Что проводка на месте,
    смотрит отдельный сторож, запускающий приложение подпроцессом.
    """
    from config import get_log_path

    get_log_path().unlink(missing_ok=True)
    record = logging.LogRecord(
        "проверка", logging.WARNING, __file__, 0, text, None, None
    )
    handlers = module._log_handlers()
    try:
        for handler in handlers:
            handler.handle(record)
    finally:
        for handler in handlers:
            handler.close()
    return get_log_path().read_text(encoding="utf-8")


def test_the_log_is_written_to_a_file_beside_the_database(entry):
    """Записи журнала оказываются в файле каталога данных.

    Экран «Логи» показывает кольцевой буфер в памяти, и тот пропадает вместе
    с окном. Файл — единственное, по чему разбирают падение после него.

    Строка нарочно не-ASCII: без явной кодировки файл открылся бы кодировкой
    системы, а в журнал попадают тексты из Telegram, где встречается всё.
    """
    module, _ = entry

    assert "эмодзи 🙂 в журнале" in _write_through(module, "эмодзи 🙂 в журнале")


def test_a_gone_stream_gets_no_handler_at_all(entry, monkeypatch, capsys):
    """Без потока вывода обработчик на него не заводится вовсе.

    У оконной сборки (`console=False`) `sys.stdout` равен `None`, а
    `StreamHandler(None)` молча подставляет себе поток ошибок — которого там
    тоже нет. Поэтому проверяется не только файл, но и то, что мимо файла не
    ушло ничего.
    """
    module, _ = entry
    monkeypatch.setattr(sys, "stdout", None)

    assert "окно без консоли" in _write_through(module, "окно без консоли")
    assert capsys.readouterr().err == ""


def test_the_log_rotates_by_size(entry, monkeypatch):
    """Разросшийся журнал переходит на новый файл, а прежний остаётся рядом.

    Без ротации файл растёт без края: приложение живёт часами и пишет в него
    каждый обход каналов.
    """
    module, _ = entry
    from config import get_log_path

    get_log_path().unlink(missing_ok=True)
    monkeypatch.setattr(module, "LOG_BYTES", 200)
    handlers = module._log_handlers()
    try:
        for n in range(20):
            record = logging.LogRecord(
                "проверка", logging.WARNING, __file__, 0, f"строка {n}", None, None
            )
            for handler in handlers:
                handler.handle(record)
    finally:
        for handler in handlers:
            handler.close()

    kept = get_log_path().parent / (get_log_path().name + ".1")
    assert kept.exists()


def test_a_torn_rotation_says_so_in_the_log_once(entry, monkeypatch, capsys):
    """Сорванный переход на новый файл ложится в тот же журнал, и один раз.

    Жалоба на каждую запись была бы не лучше молчания: предел размера после
    отказа снят, и повторяющаяся трассировка растила бы ровно тот файл,
    которому уже нечем поворачиваться. В поток ошибок при этом не уходит
    ничего: у оконной сборки его нет, и сказанное туда пропало бы.

    Наблюдается это на боевой связке обработчиков. Что сам отказ обработчик
    переживает и продолжает писать, сторожит `test_log_buffer.py`; здесь —
    число жалоб и молчание потока.
    """
    module, _ = entry
    from config import get_log_path

    get_log_path().unlink(missing_ok=True)
    monkeypatch.setattr(module, "LOG_BYTES", 200)
    handlers = module._log_handlers()

    def refuse_rename(source, dest):
        raise PermissionError("файл занят другим процессом")

    monkeypatch.setattr(os, "rename", refuse_rename)
    try:
        for n in range(20):
            record = logging.LogRecord(
                "проверка", logging.WARNING, __file__, 0, f"строка {n}", None, None
            )
            for handler in handlers:
                handler.handle(record)
    finally:
        for handler in handlers:
            handler.close()

    written = get_log_path().read_text(encoding="utf-8")
    assert written.count("файл журнала не повернуть") == 1
    assert "PermissionError" in written
    assert capsys.readouterr().err == ""


def test_an_exception_nobody_caught_reaches_the_log(entry, caplog):
    """Некому пойманное исключение становится записью журнала с трассировкой.

    Штатный ответ интерпретатора — печать в поток ошибок, а у оконной сборки
    его нет: причина падения пропадала вместе с потоком. Наблюдается здесь
    именно запись; что записи журнала доезжают до файла, сторожит отдельная
    проверка, запускающая приложение подпроцессом.
    """
    try:
        raise ValueError("некому ловить")
    except ValueError:
        crash = sys.exc_info()

    with caplog.at_level(logging.CRITICAL):
        sys.excepthook(*crash)

    assert "Traceback (most recent call last)" in caplog.text
    assert "ValueError: некому ловить" in caplog.text


def test_an_exception_in_a_side_thread_reaches_the_log(entry, caplog):
    """Упавший поток тоже оставляет след, а не пропадает молча.

    Окно работает многопоточным, и падение в постороннем потоке идёт мимо
    `sys.excepthook` — у потоков свой.
    """

    def fall():
        raise ValueError("некому ловить в потоке")

    with caplog.at_level(logging.CRITICAL):
        thread = threading.Thread(target=fall)
        thread.start()
        thread.join()

    assert "Traceback (most recent call last)" in caplog.text
    assert "ValueError: некому ловить в потоке" in caplog.text


def test_an_interrupt_from_the_console_is_not_called_a_crash(entry, caplog):
    """Прерывание с клавиатуры падением не считается.

    Так же, как завершение потока: это остановка по воле человека, а не
    беда. Записанное `CRITICAL`ом, оно зажгло бы в окне счётчик ошибок на
    обычном выходе из приложения.
    """
    try:
        raise KeyboardInterrupt
    except KeyboardInterrupt:
        stop = sys.exc_info()

    with caplog.at_level(logging.CRITICAL):
        sys.excepthook(*stop)

    assert caplog.text == ""


def test_a_thread_that_ended_itself_is_not_called_a_crash(entry, caplog):
    """Поток, завершивший себя сам, падением не считается.

    Штатный крючок `SystemExit` пропускает, и не зря: запись о нём зажгла бы
    счётчик ошибок в окне на обычном завершении работы.
    """

    def leave():
        sys.exit(0)

    with caplog.at_level(logging.CRITICAL):
        thread = threading.Thread(target=leave)
        thread.start()
        thread.join()

    assert caplog.text == ""


def test_the_running_application_writes_its_log_to_the_file(tmp_path):
    """Запущенное приложение пишет журнал в файл, и пишет его до конца.

    Проверяется подпроцессом, потому что иначе не увидеть главного: что
    обработчики вообще навешены (`basicConfig` молчит, когда у корневого
    logger'а уже кто-то есть — а под pytest есть), что записи чужих
    библиотек доезжают наравне со своими, и что обновление схемы на старте
    не сносит проводку по дороге.

    Секрет в строке нарочно: вымарывание навешено на корневой logger, а
    записи дочерних мимо него проходят — и ложатся на диск как есть.
    """
    done = subprocess.run(
        [
            sys.executable,
            "-c",
            "import main, logging\n"
            "from backend import bootstrap\n"
            "bootstrap.ensure_schema()\n"
            "logging.getLogger('httpx.child').warning("
            "'после схемы: Authorization: Bearer abcDEF123456_secret-token')\n",
        ],
        cwd=str(ROOT),
        env={**os.environ, "APPDATA": str(tmp_path), "PYTHONIOENCODING": "utf-8"},
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    assert done.returncode == 0, done.stderr
    written = (tmp_path / "JobBot" / "jobbot.log").read_text(encoding="utf-8")
    assert "после схемы" in written
    assert "Bearer abcDEF123456_secret-token" not in written


def test_the_running_application_writes_down_a_thread_that_fell(tmp_path):
    """Запущенное приложение пишет в файл падение постороннего потока.

    Проверяется подпроцессом, потому что иначе не увидеть главного: что
    крючки на необработанное падение ставит сам ввоз. В общем прогоне их
    ставит фикстура, и снятая проводка выглядела бы рабочей.
    """
    done = subprocess.run(
        [
            sys.executable,
            "-c",
            "import main, threading\n"
            "def fall():\n"
            "    raise ValueError('поток не дожил')\n"
            "worker = threading.Thread(target=fall)\n"
            "worker.start()\n"
            "worker.join()\n",
        ],
        cwd=str(ROOT),
        env={**os.environ, "APPDATA": str(tmp_path), "PYTHONIOENCODING": "utf-8"},
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    assert done.returncode == 0, done.stderr
    written = (tmp_path / "JobBot" / "jobbot.log").read_text(encoding="utf-8")
    assert "ValueError: поток не дожил" in written


def test_the_running_application_switches_its_output_to_utf8(tmp_path):
    """Ввоз приложения перенастраивает вывод на UTF-8.

    Проверяется подпроцессом и с чистым окружением: под `PYTHONIOENCODING`
    поток и так был бы в UTF-8, и снятая перенастройка выглядела бы рабочей.
    На Windows умолчание — однобайтовая кодировка системы, и без
    перенастройки первая же русская строка в консоли ломается.
    """
    env = {
        k: v for k, v in os.environ.items() if k not in ("PYTHONIOENCODING", "APPDATA")
    }
    done = subprocess.run(
        [sys.executable, "-c", "import main, sys; print(sys.stdout.encoding)"],
        cwd=str(ROOT),
        env={**env, "APPDATA": str(tmp_path)},
        capture_output=True,
        text=True,
    )

    assert done.returncode == 0, done.stderr
    assert done.stdout.strip().lower() == "utf-8"
