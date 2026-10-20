"""Разрешение платформенной обёртки установленного CLI."""

from adapters.platforms import implementation

_backend = implementation("cli")


def executable(found: str) -> str:
    # На других ОС PATH-поиск уже работал; Windows npm shim требует разрешения.
    resolver = getattr(_backend, "executable", None)
    return resolver(found) if resolver is not None else found
