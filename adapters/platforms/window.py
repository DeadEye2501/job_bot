"""Платформенные операции: window."""

from adapters.platforms import implementation

_backend = implementation("window")

unlock_frame = _backend.unlock_frame
own_taskbar_icon = _backend.own_taskbar_icon
allow_foreground = _backend.allow_foreground
show_trouble = _backend.show_trouble
