"""Рамка окна на маке — двойник `window_size._unlock_frame`.

Растягиваемость и наименьший размер pywebview отдаёт системе один раз, при
создании окна; передумать позволяет только сам `NSWindow`. Правится он из
потока моста, а AppKit принимает правку окна лишь в главном потоке — отсюда
`callAfter`, тем же путём pywebview ведёт к окну `move` и `resize`, и в очереди
главного потока правка рамки встаёт раньше них.
"""

from __future__ import annotations

from client.window_size import MAIN


def unlock_frame(window) -> None:
    """Разрешить окну тянуться и поднять ему наименьший размер до окна приложения."""
    from AppKit import NSMakeSize, NSWindowStyleMaskResizable
    from PyObjCTools import AppHelper

    def apply() -> None:
        window.setStyleMask_(window.styleMask() | NSWindowStyleMaskResizable)
        window.setMinSize_(NSMakeSize(*MAIN))

    AppHelper.callAfter(apply)
