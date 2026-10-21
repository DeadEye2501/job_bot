"""Корень репозитория в тестах: от него тесты находят исходники и запускают приложение."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
