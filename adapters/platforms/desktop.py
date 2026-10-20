"""Платформенные операции: desktop."""

from adapters.platforms import implementation

_backend = implementation("desktop")

open_target = _backend.open_target
show_in_folder = _backend.show_in_folder
