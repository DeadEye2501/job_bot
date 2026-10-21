import subprocess
import sys

import pytest

from client.bridge import desktop_macos


def _open_calls(monkeypatch, fails: bool = False) -> list[list[str]]:
    """Подменить запуск программ; ответ — с чем их звали."""
    calls = []

    def run(args, **_kwargs):
        calls.append(args)
        if fails:
            raise subprocess.CalledProcessError(1, args)
        return subprocess.CompletedProcess(args, 0)

    monkeypatch.setattr(subprocess, "run", run)
    return calls


def test_link_opens_with_open(monkeypatch):
    calls = _open_calls(monkeypatch)

    assert desktop_macos.open_in_system("tg://resolve?domain=x") is True
    assert calls == [["open", "tg://resolve?domain=x"]]


def test_open_failure_is_false(monkeypatch):
    _open_calls(monkeypatch, fails=True)

    assert desktop_macos.open_in_system("/tmp/a.pdf") is False


def test_show_in_folder_reveals(monkeypatch):
    calls = _open_calls(monkeypatch)

    assert desktop_macos.show_in_folder("/tmp/a.pdf") is True
    assert calls == [["open", "-R", "/tmp/a.pdf"]]


def test_show_in_folder_failure_is_false(monkeypatch):
    _open_calls(monkeypatch, fails=True)

    assert desktop_macos.show_in_folder("/tmp/a.pdf") is False


@pytest.mark.skipif(sys.platform != "darwin", reason="только macOS")
def test_bridge_asks_the_twin(monkeypatch):
    from client.bridge import desktop

    calls = _open_calls(monkeypatch)

    assert desktop.open_in_system("mailto:a@b.c") is True
    assert desktop._show_in_folder("/tmp/a.pdf") is True
    assert calls == [["open", "mailto:a@b.c"], ["open", "-R", "/tmp/a.pdf"]]
