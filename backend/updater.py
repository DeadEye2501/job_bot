"""Платформенные входы обновлятора; импорт безопасен до открытия окна."""

from adapters.platforms.updater import (
    UPDATE_FLAG as UPDATE_FLAG,
    can_install_update as can_install_update,
    clear_leftovers as clear_leftovers,
    launch_updater as launch_updater,
    run as run,
)
