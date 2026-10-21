import os
import signal
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "darwin", reason="только macOS")

_ROOT = Path(__file__).resolve().parents[2]


def _watched(monkeypatch, tables: list[list[tuple[int, int, str]]]) -> list[int]:
    """Подложить сторожу таблицы процессов по очереди; ответ — кому ушёл SIGKILL."""
    from adapters import tie_watch_macos

    queue = iter(tables)
    monkeypatch.setattr(tie_watch_macos, "process_table", lambda _column: next(queue))
    killed = []

    def kill(pid, sig):
        assert sig == signal.SIGKILL
        killed.append(pid)

    monkeypatch.setattr(os, "kill", kill)
    return killed


def test_tied_and_descendants_killed(monkeypatch):
    from adapters.tie_watch_macos import watch

    table = [(11, 1, "t11"), (21, 11, "t21"), (31, 21, "t31"), (42, 1, "t42")]
    killed = _watched(monkeypatch, [table, table])

    watch(["11\n"])

    assert sorted(killed) == [11, 21, 31]


def test_reused_pid_is_spared(monkeypatch):
    from adapters.tie_watch_macos import watch

    then = [(11, 1, "старт-1")]
    now = [(11, 1, "старт-2"), (21, 11, "t21")]
    killed = _watched(monkeypatch, [then, now])

    watch(["11\n"])

    assert killed == []


def test_gone_process_is_not_an_error(monkeypatch):
    from adapters import tie_watch_macos

    table = [(11, 1, "t11")]
    monkeypatch.setattr(tie_watch_macos, "process_table", lambda _column: table)

    def kill(_pid, _sig):
        raise ProcessLookupError

    monkeypatch.setattr(os, "kill", kill)

    tie_watch_macos.watch(["11\n"])


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


def test_watcher_kills_tree_when_parent_dies():
    parent = subprocess.Popen(
        [sys.executable, "-c", textwrap.dedent("""
            import subprocess, time
            from adapters import app_tied_process
            child = subprocess.Popen(["sh", "-c", "sleep 60 & wait"])
            app_tied_process.tie_to_app(child.pid)
            print(child.pid, flush=True)
            time.sleep(60)
        """)],
        cwd=_ROOT, stdout=subprocess.PIPE, text=True,
    )
    shell = int(parent.stdout.readline())
    time.sleep(1)
    sleeper = int(subprocess.run(
        ["pgrep", "-P", str(shell)], capture_output=True, text=True, check=True,
    ).stdout.split()[0])

    parent.send_signal(signal.SIGKILL)
    parent.wait()
    parent.stdout.close()
    deadline = time.monotonic() + 5
    while (_alive(shell) or _alive(sleeper)) and time.monotonic() < deadline:
        time.sleep(0.1)

    assert not _alive(shell)
    assert not _alive(sleeper)
