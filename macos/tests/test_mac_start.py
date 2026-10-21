import os
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "darwin", reason="только macOS")

_ROOT = Path(__file__).resolve().parents[2]


def test_package_names_lead_to_twins(monkeypatch):
    calls = []
    monkeypatch.setattr("adapters.app_tied_process.tie_children_named", calls.append)

    from adapters.app_tied_process import tie_children_named
    from adapters.process_windows import has_window

    tie_children_named("node.exe")

    assert calls == ["node.exe"]
    assert has_window(os.getpid()) is False


def test_tie_watch_flag_skips_app(tmp_path):
    env = {**os.environ, "HOME": str(tmp_path)}

    done = subprocess.run(
        [sys.executable, str(_ROOT / "main.py"), "--tie-watch"],
        cwd=_ROOT, env=env, stdin=subprocess.DEVNULL, capture_output=True, timeout=20,
    )

    assert done.returncode == 0
    data_dir = tmp_path / "Library" / "Application Support"
    assert not [p for p in data_dir.rglob("*") if p.is_file()]


def test_second_copy_is_refused(tmp_path):
    from backend.single_instance import hold_the_only_copy

    lock = tmp_path / "jobbot.lock"
    with hold_the_only_copy(lock):
        assert hold_the_only_copy(lock) is None
