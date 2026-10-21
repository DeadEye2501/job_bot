import os
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest

from backend import updater_macos
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


def _app_marked(where: Path, mark: str) -> Path:
    app = where / "JobBot.app"
    (app / "Contents").mkdir(parents=True)
    (app / "Contents" / "mark").write_text(mark)
    return app


@darwin
def test_swap_replaces_bundle(monkeypatch, tmp_path):
    installed = tmp_path / "Applications"
    old = _app_marked(installed, "old")
    monkeypatch.setattr(sys, "executable", str(old / "Contents" / "MacOS" / "JobBot"))
    fresh = _app_marked(tmp_path / "fresh", "new")
    subprocess.run(["ditto", "-c", "-k", "--keepParent", str(fresh), str(updater_macos.download_path())],
                   check=True)

    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    opened = tmp_path / "opened"
    (fake_bin / "open").write_text(f'#!/bin/sh\necho "$1" > "{opened}"\n')
    (fake_bin / "open").chmod(0o755)
    monkeypatch.setenv("PATH", f"{fake_bin}:{os.environ['PATH']}")
    app = subprocess.Popen(["sleep", "1"])
    monkeypatch.setattr(os, "getpid", lambda: app.pid)

    updater_macos.launch_updater(updater_macos.download_path())
    app.wait()
    deadline = time.monotonic() + 10
    while not opened.exists() and time.monotonic() < deadline:
        time.sleep(0.1)

    assert (old / "Contents" / "mark").read_text() == "new"
    assert opened.read_text().strip() == str(old)
    assert sorted(p.name for p in installed.iterdir()) == ["JobBot.app"]
