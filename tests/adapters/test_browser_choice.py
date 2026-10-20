"""Какой браузер водит агент: первый найденный из перечня."""

from pathlib import Path

from adapters.platforms.windows.browser import find_browser


def _install(root: Path, relative: str) -> Path:
    exe = root / relative
    exe.parent.mkdir(parents=True, exist_ok=True)
    exe.write_bytes(b"")
    return exe


def _roots(monkeypatch, tmp_path):
    for name in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA"):
        monkeypatch.setenv(name, str(tmp_path / name))
    return tmp_path


def test_nothing_installed_means_no_browser(monkeypatch, tmp_path):
    _roots(monkeypatch, tmp_path)
    assert find_browser() is None


def test_chrome_wins_and_goes_by_channel(monkeypatch, tmp_path):
    root = _roots(monkeypatch, tmp_path)
    chrome = _install(root / "PROGRAMFILES", "Google/Chrome/Application/chrome.exe")
    _install(root / "LOCALAPPDATA", "Vivaldi/Application/vivaldi.exe")
    found = find_browser()
    assert (found.name, found.channel, found.executable) == ("Chrome", "chrome", chrome)


def test_opera_is_driven_by_the_real_browser_not_its_launcher(monkeypatch, tmp_path):
    root = _roots(monkeypatch, tmp_path)
    _install(root / "LOCALAPPDATA", "Programs/Opera/opera.exe")
    _install(root / "LOCALAPPDATA", "Programs/Opera/99.0.1.1/opera.exe")
    real = _install(root / "LOCALAPPDATA", "Programs/Opera/112.0.5.53/opera.exe")
    assert find_browser().executable == real


def test_edge_is_the_last_resort(monkeypatch, tmp_path):
    root = _roots(monkeypatch, tmp_path)
    _install(root / "PROGRAMFILES(X86)", "Microsoft/Edge/Application/msedge.exe")
    assert find_browser().channel == "msedge"
