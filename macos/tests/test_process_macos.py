import sys
import types

from adapters import process_macos

_ALL, _ON_SCREEN = 0, 1


def _quartz(monkeypatch, windows: list[dict]) -> list[int]:
    """Подложить фейковый Quartz с этими окнами; ответ — какие списки спрошены."""
    asked = []

    def window_list(option, _relative_to):
        asked.append(option)
        return windows

    monkeypatch.setitem(sys.modules, "Quartz", types.SimpleNamespace(
        kCGWindowListOptionAll=_ALL,
        kCGWindowListOptionOnScreenOnly=_ON_SCREEN,
        kCGNullWindowID=0,
        CGWindowListCopyWindowInfo=window_list,
    ))
    return asked


def test_window_of_pid_found(monkeypatch):
    _quartz(monkeypatch, [{"kCGWindowOwnerPID": 7, "kCGWindowLayer": 0}])

    assert process_macos.has_window(7) is True
    assert process_macos.has_window(8) is False


def test_menu_bar_layer_is_not_a_window(monkeypatch):
    _quartz(monkeypatch, [{"kCGWindowOwnerPID": 7, "kCGWindowLayer": 25}])

    assert process_macos.has_window(7) is False


def test_minimized_window_still_counts(monkeypatch):
    asked = _quartz(monkeypatch, [{"kCGWindowOwnerPID": 7, "kCGWindowLayer": 0}])

    assert process_macos.has_window(7) is True
    assert asked == [_ALL]
