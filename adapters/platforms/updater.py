"""Одна точка выбора и проверки возможности установки обновления."""

import sys

from adapters.platforms import implementation

_backend = implementation("updater")
UPDATE_FLAG = "--update"


def supports_updates() -> bool:
    return _backend.SUPPORTS_UPDATES


def can_install_update() -> bool:
    return supports_updates() and bool(getattr(sys, "frozen", False))


clear_leftovers = _backend.clear_leftovers


def run(args: list[str]) -> int:
    if not can_install_update():
        return 2
    return _backend.run(args)


def launch_updater(new) -> None:
    if not can_install_update():
        raise OSError("Установка обновления не поддерживается этой копией приложения")
    _backend.launch_updater(new)
