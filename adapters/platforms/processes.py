"""Платформенные операции: processes."""

from adapters.platforms import implementation

_backend = implementation("processes")

tie_to_app = _backend.tie_to_app
tie_children_named = _backend.tie_children_named
cli_process_options = _backend.cli_process_options
tie_browser_driver = _backend.tie_browser_driver
