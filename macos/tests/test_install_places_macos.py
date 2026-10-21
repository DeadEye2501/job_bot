import os
import shutil
import sys
from pathlib import Path

import pytest

from adapters import install_places_macos


def _home_with_local_bin(monkeypatch, home: Path) -> Path:
    """Домашний каталог `home` с `~/.local/bin`; ответ — этот каталог программ."""
    monkeypatch.setattr(Path, "home", lambda: home)
    local_bin = home / ".local" / "bin"
    local_bin.mkdir(parents=True)
    return local_bin


def test_person_order_kept(monkeypatch, tmp_path):
    local_bin = _home_with_local_bin(monkeypatch, tmp_path)
    own = str(tmp_path / "own")

    places = install_places_macos.with_install_places(own).split(os.pathsep)

    assert places[0] == own
    assert places.count(str(local_bin)) == 1


def test_named_dir_not_repeated(monkeypatch, tmp_path):
    local_bin = _home_with_local_bin(monkeypatch, tmp_path)

    places = install_places_macos.with_install_places(str(local_bin)).split(os.pathsep)

    assert places[0] == str(local_bin)
    assert places.count(str(local_bin)) == 1


@pytest.mark.skipif(sys.platform != "darwin", reason="только macOS")
def test_finder_path_finds_local_bin(monkeypatch, tmp_path):
    claude = _home_with_local_bin(monkeypatch, tmp_path) / "claude"
    claude.touch(mode=0o755)
    monkeypatch.setenv("PATH", "/usr/bin:/bin")

    install_places_macos.widen_path()

    assert shutil.which("claude") == str(claude)
