"""Существующие Windows/POSIX-замки с одной точкой выбора."""

from adapters.platforms import implementation

lock_file = implementation("locking").lock_file
