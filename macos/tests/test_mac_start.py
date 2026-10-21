import os
import subprocess
import sys

import pytest

from tests.paths import ROOT

pytestmark = pytest.mark.skipif(sys.platform != "darwin", reason="только macOS")


def test_package_names_lead_to_twins(monkeypatch):
    import adapters.browser
    from adapters import claude_code_process

    calls = []
    monkeypatch.setattr("adapters.app_tied_process.tie_to_app", calls.append)

    claude_code_process.app_tied_process.tie_to_app(5)

    assert calls == [5]
    assert adapters.browser.has_window(os.getpid()) is False


def _watcher_run(home, stdin: bytes) -> subprocess.CompletedProcess:
    """`main.py` сторожем, с этим вводом и домашним каталогом `home`."""
    from adapters.tie_watch_macos import TIE_WATCH_FLAG

    return subprocess.run(
        [sys.executable, str(ROOT / "main.py"), TIE_WATCH_FLAG],
        cwd=ROOT, env={**os.environ, "HOME": str(home)}, input=stdin,
        capture_output=True, timeout=20,
    )


def _data_files(home) -> list:
    return [p for p in (home / "Library" / "Application Support").rglob("*") if p.is_file()]


def test_tie_watch_flag_skips_app(tmp_path):
    assert _watcher_run(tmp_path, b"").returncode == 0
    assert not _data_files(tmp_path)


def test_watcher_failure_stays_out_of_the_log(tmp_path):
    _watcher_run(tmp_path, b"not-a-pid\n")

    assert not _data_files(tmp_path)
