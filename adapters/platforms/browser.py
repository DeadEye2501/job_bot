"""Платформенные операции: browser."""

from adapters.platforms import implementation

_backend = implementation("browser")

find_browser = _backend.find_browser
has_window = _backend.has_window
