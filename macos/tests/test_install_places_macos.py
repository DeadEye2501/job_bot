import os
import shutil
import sys
from pathlib import Path

import pytest

from adapters import install_places_macos


def test_person_order_kept(monkeypatch, tmp_path):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    local_bin = tmp_path / ".local" / "bin"
    local_bin.mkdir(parents=True)
    own = str(tmp_path / "own")

    places = install_places_macos.with_install_places(own).split(os.pathsep)

    assert places[0] == own
    assert places.count(str(local_bin)) == 1


def test_named_dir_not_repeated(monkeypatch, tmp_path):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    local_bin = tmp_path / ".local" / "bin"
    local_bin.mkdir(parents=True)

    places = install_places_macos.with_install_places(str(local_bin)).split(os.pathsep)

    assert places == [str(local_bin)]


@pytest.mark.skipif(sys.platform != "darwin", reason="только macOS")
def test_finder_path_finds_local_bin(monkeypatch, tmp_path):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    claude = tmp_path / ".local" / "bin" / "claude"
    claude.parent.mkdir(parents=True)
    claude.touch(mode=0o755)

    path = install_places_macos.with_install_places("/usr/bin:/bin")

    assert shutil.which("claude", path=path) == str(claude)
