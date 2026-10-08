"""Дочерний процесс, привязанный к приложению, не переживает его аварийный выход.

Проверка на настоящих процессах Windows: «приложение» здесь — промежуточный
Python, который поднимает «внука», привязывает его (или нет) через
`tie_to_app` и обрывается без единой уборки. Подставной процесс ничего бы не
доказал: снимает внука система, а не наш код.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="задания есть только в Windows")

ROOT = Path(__file__).resolve().parents[2]

_APP = """
import os, subprocess, sys
from adapters import app_tied_process
child = subprocess.Popen(
    [sys.executable, "-c", "import time; time.sleep(60)"],
    stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
)
if sys.argv[1] == "tie":
    app_tied_process.tie_to_app(child.pid)
print(child.pid, flush=True)
os._exit(1)
"""
# Вывод у внука закрыт: унаследуй он трубу «приложения», чтение её ждало бы,
# пока внук сам не умрёт, и проверка смотрела бы на уже мёртвый процесс.


def _alive(pid: int) -> bool:
    shown = subprocess.run(
        ["tasklist", "/FI", f"PID eq {pid}", "/NH"], capture_output=True, text=True, check=True
    ).stdout
    return str(pid) in shown


def _orphan(mode: str) -> int:
    """Номер внука, оставшегося после аварийного выхода «приложения»."""
    env = {**os.environ, "PYTHONPATH": str(ROOT)}
    out = subprocess.run(
        [sys.executable, "-c", _APP, mode], capture_output=True, text=True, env=env, timeout=30
    ).stdout
    return int(out.split()[0])


def test_a_tied_child_dies_with_the_app_however_it_ended():
    """Привязанный внук снят системой, хотя «приложение» оборвалось без уборки."""
    pid = _orphan("tie")

    assert not _alive(pid)


def test_an_untied_child_outlives_the_app():
    """Без привязки внук переживает «приложение» — снимает именно привязка."""
    pid = _orphan("free")
    try:
        assert _alive(pid)
    finally:
        subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True)
