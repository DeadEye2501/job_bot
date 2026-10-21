import sys

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "darwin", reason="только macOS")


def _wizard_window():
    """Окно размера мастера, нерастягиваемое — как его создаёт pywebview."""
    from AppKit import (
        NSApplication,
        NSBackingStoreBuffered,
        NSMakeRect,
        NSWindow,
        NSWindowStyleMaskTitled,
    )

    NSApplication.sharedApplication()
    return NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
        NSMakeRect(0, 0, 640, 620), NSWindowStyleMaskTitled, NSBackingStoreBuffered, False,
    )


def _pump() -> None:
    from Foundation import NSDate, NSRunLoop

    NSRunLoop.currentRunLoop().runUntilDate_(NSDate.dateWithTimeIntervalSinceNow_(0.3))


def test_window_becomes_resizable():
    from AppKit import NSWindowStyleMaskResizable

    from client.window_size import MAIN, _unlock_frame

    window = _wizard_window()

    _unlock_frame(window)
    _pump()

    assert window.styleMask() & NSWindowStyleMaskResizable
    assert (window.minSize().width, window.minSize().height) == MAIN
