import sys
from pathlib import Path

import pytest

from adapters import browser_macos
from adapters.browser import BRAVE, CHROME, InstalledBrowser
from tests.files import empty_file as _install


def _bases(monkeypatch, tmp_path) -> tuple[Path, Path]:
    """Системная и своя папки программ — во временном каталоге; ответ — обе."""
    system, home = tmp_path / "system", tmp_path / "home"
    monkeypatch.setattr(browser_macos, "_SYSTEM_APPS", system)
    monkeypatch.setattr(Path, "home", lambda: home)
    return system, home / "Applications"


def test_first_installed_wins(monkeypatch, tmp_path):
    _system, apps = _bases(monkeypatch, tmp_path)
    brave = _install(apps, "Brave Browser.app/Contents/MacOS/Brave Browser")

    assert browser_macos.find_browser() == InstalledBrowser(BRAVE, None, brave)


def test_chrome_before_edge_and_channel(monkeypatch, tmp_path):
    system, _apps = _bases(monkeypatch, tmp_path)
    chrome = _install(system, "Google Chrome.app/Contents/MacOS/Google Chrome")
    _install(system, "Microsoft Edge.app/Contents/MacOS/Microsoft Edge")

    assert browser_macos.find_browser() == InstalledBrowser(CHROME, "chrome", chrome)


def test_chrome_in_home_has_no_channel(monkeypatch, tmp_path):
    _system, apps = _bases(monkeypatch, tmp_path)
    chrome = _install(apps, "Google Chrome.app/Contents/MacOS/Google Chrome")

    assert browser_macos.find_browser() == InstalledBrowser(CHROME, None, chrome)


def test_nothing_installed(monkeypatch, tmp_path):
    _bases(monkeypatch, tmp_path)

    assert browser_macos.find_browser() is None


@pytest.mark.skipif(sys.platform != "darwin", reason="только macOS")
def test_app_search_finds_mac_browser(monkeypatch, tmp_path):
    from adapters import browser

    _system, apps = _bases(monkeypatch, tmp_path)
    brave = _install(apps, "Brave Browser.app/Contents/MacOS/Brave Browser")

    assert browser.find_browser() == InstalledBrowser(BRAVE, None, brave)
