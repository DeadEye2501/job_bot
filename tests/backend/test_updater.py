"""Подмена exe: копия ждёт выхода приложения, заменяет его файл и запускает новый."""

import logging
import os
import subprocess
import sys

import pytest

from backend import updater

REAL_POPEN = subprocess.Popen
"""Настоящий запуск процесса: подменщику его подменяют, а тесту он нужен живым."""


@pytest.fixture
def app(tmp_path):
    """Старый exe и скачанный новый рядом с ним."""
    exe = tmp_path / "JobBot.exe"
    exe.write_bytes(b"old")
    new = tmp_path / "JobBot.exe.new"
    new.write_bytes(b"new")
    return exe, new


@pytest.fixture
def started(monkeypatch, tmp_path):
    """Что подменщик запустил после замены. Его журнал — в папке теста, и после
    теста обработчик снимается: открытый файл не дал бы её убрать."""
    launched = []
    monkeypatch.setattr(updater.subprocess, "Popen", lambda args, **kw: launched.append(args))
    monkeypatch.setattr(updater, "_PAUSE_SEC", 0)
    monkeypatch.setattr(updater.tempfile, "gettempdir", lambda: str(tmp_path))
    yield launched
    for handler in updater.logger.handlers[:]:
        handler.close()
        updater.logger.removeHandler(handler)
    updater.logger.propagate = True


def test_the_copy_waits_for_the_app_to_exit(app, started):
    """Пока приложение не вышло, его exe занят: копия ждёт его процесса."""
    exe, new = app
    worker = REAL_POPEN([sys.executable, "-c", "import time; time.sleep(0.5)"])

    assert updater.run([str(worker.pid), str(exe), str(new)]) == 0

    assert worker.poll() is not None
    assert exe.read_bytes() == b"new" and not new.exists()
    assert started == [[str(exe)]]


def test_a_file_held_for_a_moment_is_replaced_after_retries(app, started, monkeypatch):
    """Антивирус держит свежий файл — копия повторяет, а не бросает дело."""
    exe, new = app
    real_replace = updater.os.replace
    tries = []

    def held_twice(source, target):
        tries.append(source)
        if len(tries) <= 2:
            raise PermissionError("файл занят")
        real_replace(source, target)

    monkeypatch.setattr(updater.os, "replace", held_twice)

    assert updater.run(["0", str(exe), str(new)]) == 0
    assert exe.read_bytes() == b"new" and len(tries) == 3


def test_a_download_gone_to_quarantine_still_leaves_the_app_running(app, started):
    """Антивирус унёс скачанный exe — подменять нечем, но человек нажал «обновить»
    и ждёт приложения: запускается прежнее."""
    exe, new = app
    new.unlink()

    assert updater.run(["0", str(exe), str(new)]) == 1
    assert exe.read_bytes() == b"old"
    assert started == [[str(exe)]]


def test_a_file_held_for_good_leaves_the_old_app_working(app, started, monkeypatch):
    """Заменить так и не вышло — старый exe цел и запускается он, а беда в журнале."""
    exe, new = app

    def held(source, target):
        raise PermissionError("файл занят")

    monkeypatch.setattr(updater.os, "replace", held)

    assert updater.run(["0", str(exe), str(new)]) == 1
    assert exe.read_bytes() == b"old"
    assert started == [[str(exe)]]


@pytest.fixture
def leftovers(tmp_path, monkeypatch):
    """Что осталось от обновления: скачанный файл рядом с exe и копия-подменщик."""
    monkeypatch.setattr(sys, "executable", str(tmp_path / "JobBot.exe"))
    monkeypatch.setattr(updater.tempfile, "gettempdir", lambda: str(tmp_path))
    new = tmp_path / "JobBot.exe.new"
    new.write_bytes(b"new")
    updater.updater_copy().write_bytes(b"copy")
    return new, updater.updater_copy()


def test_a_normal_start_clears_what_the_update_left(leftovers):
    """Скачанный файл и копия-подменщик после обновления не нужны."""
    updater.clear_leftovers()

    assert not any(path.exists() for path in leftovers)


def test_a_copy_still_running_is_left_for_the_next_start(leftovers):
    """Копия выходит сразу после запуска нового exe, и её файл обычно ещё занят:
    запуск от этого не падает, а занятое уберёт следующий."""
    new, copy = leftovers
    with copy.open("rb"):
        updater.clear_leftovers()

    assert copy.exists() and not new.exists()


def test_the_copy_is_told_which_file_replaces_which(tmp_path, monkeypatch):
    """Порядок доводов один у запуска и у разбора: перепутай их — рабочий exe
    уехал бы на место скачанного. Ждать велено родителя — загрузчик PyInstaller,
    который держит exe дольше питона."""
    launched = []
    monkeypatch.setattr(sys, "executable", str(tmp_path / "JobBot.exe"))
    monkeypatch.setattr(updater.tempfile, "gettempdir", lambda: str(tmp_path))
    monkeypatch.setattr(updater.shutil, "copy2", lambda source, target: None)
    monkeypatch.setattr(updater.subprocess, "Popen", lambda args, **kw: launched.append(args))
    new = tmp_path / "JobBot.exe.new"

    updater.launch_updater(new)

    copy, flag, pid, exe, replacement = launched[0]
    assert (copy, flag, pid) == (str(updater.updater_copy()), "--update", str(os.getppid()))
    assert (exe, replacement) == (str(tmp_path / "JobBot.exe"), str(new))


def test_both_launches_ask_for_a_fresh_unpacking(app, started, tmp_path, monkeypatch):
    """Собранный exe, запущенный из собранного, без этой просьбы может взять
    распаковку запустившего — а её сотрут, едва тот выйдет."""
    exe, new = app
    envs = []
    monkeypatch.setattr(updater.subprocess, "Popen", lambda args, **kw: envs.append(kw.get("env") or {}))
    monkeypatch.setattr(updater.shutil, "copy2", lambda source, target: None)

    updater.launch_updater(new)
    updater.run(["0", str(exe), str(new)])

    assert [env.get("PYINSTALLER_RESET_ENVIRONMENT") for env in envs] == ["1", "1"]


def test_the_copy_writes_its_own_log_not_the_apps(app, started, tmp_path, caplog):
    """Журнал приложения сторожит замок, а копия замка не берёт: её записи не идут
    наверх, к обработчикам приложения, а ложатся в свой файл."""
    exe, new = app

    with caplog.at_level(logging.INFO):
        updater.run(["0", str(exe), str(new)])

    assert not [r for r in caplog.records if r.name == updater.logger.name]
    assert "exe подменён" in (tmp_path / "JobBot-update.log").read_text(encoding="utf-8")
