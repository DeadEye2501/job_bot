import os
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest

from backend import updater_macos
from macos.tests.fake_run import recorded_runs
from tests.fakes.github_release import download_url, serve_latest

darwin = pytest.mark.skipif(sys.platform != "darwin", reason="только macOS")

_MAC_FILE = "JobBot-macos-arm64.zip"


def _bundle(monkeypatch, root: Path) -> Path:
    """Запущенный бандл в `root`; ответ — его путь."""
    app = root / "JobBot.app"
    (app / "Contents" / "MacOS").mkdir(parents=True)
    monkeypatch.setattr(sys, "executable", str(app / "Contents" / "MacOS" / "JobBot"))
    return app


def test_download_lands_beside_bundle(monkeypatch, tmp_path):
    app = _bundle(monkeypatch, tmp_path)

    assert updater_macos.download_path() == app.with_name("JobBot-update.zip")


def test_leftovers_cleared(monkeypatch, tmp_path):
    app = _bundle(monkeypatch, tmp_path)
    (tmp_path / "JobBot-update.zip").write_bytes(b"zip")
    (tmp_path / "JobBot-update" / "JobBot.app").mkdir(parents=True)
    (tmp_path / "JobBot.app.old" / "Contents").mkdir(parents=True)

    updater_macos.clear_leftovers()

    assert sorted(p.name for p in tmp_path.iterdir()) == ["JobBot.app"]
    assert app.is_dir()


def test_clean_start_has_nothing_to_clear(monkeypatch, tmp_path):
    app = _bundle(monkeypatch, tmp_path)

    updater_macos.clear_leftovers()

    assert app.is_dir()


def test_broken_unpack_is_a_handoff_failure(monkeypatch, tmp_path):
    """Скачанное сверено, не вышла только распаковка: это «не передано», а не
    «не скачалось» — зовущий различает их по `OSError`."""
    _bundle(monkeypatch, tmp_path)
    recorded_runs(monkeypatch, fails=True)

    with pytest.raises(OSError):
        updater_macos.launch_updater(updater_macos.download_path())


@darwin
def test_app_updater_routes_to_mac(monkeypatch, tmp_path):
    from backend import updater

    handed = []
    monkeypatch.setattr(updater_macos, "launch_updater", handed.append)
    monkeypatch.setattr(updater_macos, "clear_leftovers", lambda: handed.append("cleared"))

    updater.launch_updater(tmp_path / "JobBot-update.zip")
    updater.clear_leftovers()

    assert handed == [tmp_path / "JobBot-update.zip", "cleared"]


@darwin
async def test_mac_release_picks_its_file(monkeypatch):
    from adapters.github_release import latest_release

    def asset(name: str) -> dict:
        return {"name": name, "browser_download_url": download_url("v9.0.0", name),
                "size": 3, "digest": "sha256:" + "ab" * 32}

    both = {"tag_name": "v9.0.0", "assets": [asset("JobBot.exe"), asset(_MAC_FILE)]}
    serve_latest(monkeypatch, httpx.Response(200, json=both))
    assert (await latest_release()).url == download_url("v9.0.0", _MAC_FILE)

    exe_only = {"tag_name": "v9.0.0", "assets": [asset("JobBot.exe")]}
    serve_latest(monkeypatch, httpx.Response(200, json=exe_only))
    assert await latest_release() is None


@darwin
def test_app_routes_to_mac_updater(monkeypatch, tmp_path):
    from backend import update_download

    _bundle(monkeypatch, tmp_path)

    assert update_download.new_exe_path() == updater_macos.download_path()


def _mark(app: Path, mark: str) -> Path:
    """Метка версии внутри бандла: по ней видно, какой из двух стоит на месте."""
    (app / "Contents").mkdir(parents=True, exist_ok=True)
    (app / "Contents" / "mark").write_text(mark)
    return app


def _swap_bench(monkeypatch, tmp_path, fresh_name: str) -> tuple[Path, Path, subprocess.Popen]:
    """Установленный бандл с меткой «old», скачанный zip с бандлом `fresh_name` и
    меткой «new», подменённый `open` и «приложение» — `sleep 2`, выхода которого
    ждёт подменщик. Ответ — бандл, файл с аргументом `open`, процесс приложения."""
    old = _mark(_bundle(monkeypatch, tmp_path / "Applications"), "old")
    fresh = _mark(tmp_path / "fresh" / fresh_name, "new")
    subprocess.run(["ditto", "-c", "-k", "--keepParent", str(fresh), str(updater_macos.download_path())],
                   check=True)
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    opened = tmp_path / "opened"
    (fake_bin / "open").write_text(f'#!/bin/sh\necho "$1" > "{opened}"\n')
    (fake_bin / "open").chmod(0o755)
    monkeypatch.setenv("PATH", f"{fake_bin}:{os.environ['PATH']}")
    app = subprocess.Popen(["sleep", "2"])
    monkeypatch.setattr(os, "getpid", lambda: app.pid)
    return old, opened, app


def _swapped(app: subprocess.Popen) -> None:
    app.wait()
    updater_macos._swapper.wait(timeout=10)


@darwin
def test_swap_waits_then_replaces_bundle(monkeypatch, tmp_path):
    old, opened, app = _swap_bench(monkeypatch, tmp_path, "JobBot.app")

    updater_macos.launch_updater(updater_macos.download_path())
    time.sleep(0.5)

    assert (old / "Contents" / "mark").read_text() == "old"
    assert not opened.exists()

    _swapped(app)

    assert (old / "Contents" / "mark").read_text() == "new"
    assert opened.read_text().strip() == str(old)
    assert sorted(p.name for p in old.parent.iterdir()) == ["JobBot.app"]


@darwin
def test_failed_swap_keeps_old_bundle(monkeypatch, tmp_path):
    old, opened, app = _swap_bench(monkeypatch, tmp_path, "Other.app")

    updater_macos.launch_updater(updater_macos.download_path())
    _swapped(app)

    assert (old / "Contents" / "mark").read_text() == "old"
    assert opened.read_text().strip() == str(old)
