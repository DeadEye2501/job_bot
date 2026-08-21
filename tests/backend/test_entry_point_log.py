"""Следствия журнала приложения: файл, поворот, кодировка и падения.

Журнал заводится тем же ввозом, что и точка входа, и правит корневой logger
насовсем — поэтому смотрят на него через ту же фикстуру `entry`, что и
запуск, а сам порядок шагов запуска проверяет сосед, `test_entry_point.py`.

Записи о необработанном падении здесь же: крючки на них ставит тот же ввоз, и
наблюдаются они тем же журналом.
"""

import logging
import os
import subprocess
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


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
