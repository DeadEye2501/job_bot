"""Платформенная граница: безопасные импорты и запрет неподдержанной подмены."""

import ast
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from adapters.platforms import unsupported
from adapters.platforms import updater as platform_updater

ROOT = Path(__file__).resolve().parents[2]


def test_shared_imports_do_not_load_windows_api_on_a_non_windows_host():
    if sys.platform == "win32":
        pytest.skip("проверка импорта чужой платформы выполняется на macOS/Linux")
    code = """
import sys
from adapters import app_tied_process, process_windows
from client import window_size, raise_window, trouble_box
from backend import single_instance, updater
assert not any(n.startswith('adapters.platforms.windows') for n in sys.modules)
assert updater.run(['42', 'old', 'new']) == 2
"""
    subprocess.run([sys.executable, "-c", code], cwd=ROOT, check=True, timeout=10)


@pytest.mark.parametrize("operation", [
    unsupported.has_window, unsupported.tie_to_app, unsupported.open_target,
    unsupported.show_in_folder, unsupported.show_trouble, unsupported.unlock_frame,
    unsupported.cli_process_options, unsupported.tie_browser_driver,
])
def test_unimplemented_system_operations_fail_explicitly(operation):
    with pytest.raises(unsupported.UnsupportedPlatformError):
        operation()


def test_unsupported_update_does_not_touch_files(tmp_path, monkeypatch):
    executable = tmp_path / "JobBot"
    leftover = tmp_path / "JobBot.new"
    executable.write_bytes(b"app")
    leftover.write_bytes(b"unrelated")
    monkeypatch.setattr(sys, "executable", str(executable))
    unsupported.clear_leftovers()
    assert unsupported.run(["0", str(executable), str(leftover)]) == 2
    assert executable.read_bytes() == b"app"
    assert leftover.read_bytes() == b"unrelated"


@pytest.mark.parametrize(("supported", "frozen", "expected"), [
    (False, False, False), (False, True, False),
    (True, False, False), (True, True, True),
])
def test_installation_requires_both_support_and_a_frozen_app(
    supported, frozen, expected, monkeypatch,
):
    monkeypatch.setattr(platform_updater, "_backend", SimpleNamespace(SUPPORTS_UPDATES=supported))
    monkeypatch.setattr(sys, "frozen", frozen, raising=False)
    assert platform_updater.can_install_update() is expected


def test_direct_handoff_is_denied_before_the_platform_is_called(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(platform_updater, "_backend", SimpleNamespace(
        SUPPORTS_UPDATES=False, launch_updater=calls.append,
    ))
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    with pytest.raises(OSError):
        platform_updater.launch_updater(tmp_path / "JobBot.new")
    assert calls == []


async def test_unsupported_download_never_queries_github(tmp_path, monkeypatch):
    from backend import update_download

    def unexpected():
        pytest.fail("неподдержанная платформа запросила Windows-релиз")

    monkeypatch.setattr(platform_updater, "_backend", unsupported)
    monkeypatch.setattr(update_download.github_release, "latest_release", unexpected)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    target = tmp_path / "JobBot.new"
    assert await update_download.newer_release() is None
    assert await update_download.download_update(target, lambda *_args: None) == "no_update"
    assert not target.exists()


async def test_bot_cannot_bypass_unsupported_update(tmp_path, monkeypatch):
    from backend.bot.update import download_update

    monkeypatch.setattr(platform_updater, "_backend", unsupported)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    # No slot, callbacks or target path can be accessed before capability is checked.
    assert await download_update(object()) == "no_update"


def test_ui_cannot_bypass_unsupported_update(monkeypatch):
    from client.bridge.app_update import AppUpdate

    monkeypatch.setattr(platform_updater, "_backend", unsupported)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    ui = AppUpdate()  # Has no hub: an unsupported update must not access it.
    assert ui.version()["ok"]["updatable"] is False
    assert ui.update()["fail"] == "denied"


def test_raw_windows_api_is_confined_to_windows_package():
    violations = []
    for directory in ("adapters", "backend", "client"):
        for path in (ROOT / directory).rglob("*.py"):
            if path.is_relative_to(ROOT / "adapters/platforms/windows"):
                continue
            for node in ast.walk(ast.parse(path.read_text())):
                if isinstance(node, ast.ImportFrom) and node.module:
                    if node.module in {"ctypes", "ctypes.wintypes", "msvcrt", "webview.platforms.winforms"}:
                        violations.append(str(path.relative_to(ROOT)))
                if isinstance(node, ast.Import):
                    if any(n.name in {"ctypes", "ctypes.wintypes", "msvcrt"} for n in node.names):
                        violations.append(str(path.relative_to(ROOT)))
                if isinstance(node, ast.Attribute) and node.attr in {"startfile", "windll", "WinDLL", "WINFUNCTYPE"}:
                    violations.append(str(path.relative_to(ROOT)))
    assert violations == []
