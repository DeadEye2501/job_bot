"""Следствия подготовки схемы базы при запуске.

Обновление схемы получает две вещи: где лежат сами миграции и до какой
ревизии дойти. Ошибка в любой — приложение стартует на базе без колонок,
которые код уже читает, либо не находит миграций вовсе.

Пути к базе среди них нет: его владелец — `alembic/env.py`, который
перезаписывает `sqlalchemy.url` первой же строкой, чем бы его ни наполнили
снаружи. Следствие «схема легла туда, где сказано в настройках»
наблюдает `test_migration_engine.py`: он уводит путь через сами настройки
и смотрит, что именно там оказалось. Появления файла для этого мало —
его создало бы и обычное подключение; доказывают режим журнала, который
выставляют только наши PRAGMA, и столкновение с заранее заведённой
таблицей.

Само обновление здесь не запускается: оно применяет к базе все ревизии, а
стенд нарочно останавливается раньше — в последней лежат настоящие учётные
данные пользователя, и в тестовую базу им попадать нельзя.
"""

from pathlib import Path

import pytest

from backend.bootstrap import ensure_schema


@pytest.fixture
def upgrades(monkeypatch):
    """Перехватывает обновление и запоминает, о чём его попросили."""
    asked: list[tuple] = []

    def upgrade(cfg, revision):
        asked.append((cfg, revision))

    monkeypatch.setattr("alembic.command.upgrade", upgrade)
    return asked


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
