"""Следствия подготовки схемы базы при запуске.

Обновление схемы получает три вещи: где лежат сами миграции, куда их
применять и до какой ревизии дойти. Ошибка в любой из трёх — либо приложение
стартует на пустой базе, либо, что хуже, миграции уходят не в тот файл.

Путь к базе берётся из настроек, а не задаётся здесь: пользователь волен
перенести папку с данными, и жёсткий путь молча увёл бы приложение на старую
копию.

Само обновление здесь не запускается: оно применяет к базе все ревизии, а
стенд нарочно останавливается раньше — в последней лежат настоящие учётные
данные пользователя, и в тестовую базу им попадать нельзя.
"""

from pathlib import Path

import pytest

from backend.bootstrap import ensure_schema
from config import get_database_url


@pytest.fixture
def upgrades(monkeypatch):
    """Перехватывает обновление и запоминает, о чём его попросили."""
    asked: list[tuple] = []

    def upgrade(cfg, revision):
        asked.append((cfg, revision))

    monkeypatch.setattr("alembic.command.upgrade", upgrade)
    return asked


def test_the_migrations_are_applied_to_the_configured_database(upgrades):
    """Миграции применяются к базе из настроек, а не к жёстко заданной.

    Пользователь волен перенести папку с данными; жёсткий путь молча
    увёл бы приложение на старую копию.
    """
    ensure_schema()

    cfg, _ = upgrades[0]
    assert cfg.get_main_option("sqlalchemy.url") == get_database_url()


def test_the_migrations_are_taken_from_the_project(upgrades):
    """Миграции берутся из папки проекта, и она существует.

    В собранном приложении рабочий каталог чужой: путь, посчитанный от
    него, указал бы в пустоту.
    """
    ensure_schema()

    cfg, _ = upgrades[0]
    location = Path(cfg.get_main_option("script_location"))
    assert location.is_absolute()
    assert location.is_dir()


def test_the_schema_is_brought_to_the_latest_revision(upgrades):
    """Схема доводится до последней ревизии.

    Остановившись раньше, приложение стартовало бы на базе без колонок,
    которые код уже читает.
    """
    ensure_schema()

    assert [revision for _, revision in upgrades] == ["head"]
