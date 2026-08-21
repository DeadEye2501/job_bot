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

Миграции проекта здесь до конца не доводятся: в последней ревизии лежат
настоящие учётные данные пользователя, и в тестовую базу им попадать нельзя.
Поэтому следствия разведены по двум сторожам, и каждый берёт то, что на его
наборе наблюдаемо. «Миграции нашлись» проверяется на настоящих миграциях
проекта — только у них есть свой путь, который и может указать в пустоту, —
а «дошли до последней» на подложенном наборе из двух ревизий, потому что у
проектного дойти до конца нельзя. Прогон в обоих случаях настоящий.
"""

import re
import sqlite3
from pathlib import Path

from alembic import command

from backend.bootstrap import alembic_config, ensure_schema
from tests.conftest import INIT_REVISION

_ENV_PY = '''
from alembic import context
from sqlalchemy import create_engine

engine = create_engine("sqlite:///{db}")
try:
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=None)
        with context.begin_transaction():
            context.run_migrations()
finally:
    engine.dispose()
'''

_REVISION_PY = '''
revision = "{revision}"
down_revision = {parent}

from alembic import op


def upgrade():
    op.execute("CREATE TABLE {table} (id INTEGER PRIMARY KEY)")


def downgrade():
    op.execute("DROP TABLE {table}")
'''


def _tables(db_file) -> set[str]:
    connection = sqlite3.connect(db_file)
    try:
        rows = connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
    finally:
        connection.close()
    return {name for (name,) in rows}


def _revision_reached(db_file) -> str:
    connection = sqlite3.connect(db_file)
    try:
        return connection.execute("SELECT version_num FROM alembic_version").fetchone()[0]
    finally:
        connection.close()


def _project_of_two_revisions(root, db_file) -> None:
    """Подкладывает проект с двумя ревизиями: первая заводит `первая`, вторая
    `вторая`. Дошли до последней — на месте обе.
    """
    versions = root / "alembic" / "versions"
    versions.mkdir(parents=True)
    (root / "alembic.ini").write_text(
        "[alembic]\nscript_location = alembic\n", encoding="utf-8"
    )
    (root / "alembic" / "env.py").write_text(
        _ENV_PY.format(db=db_file.as_posix()), encoding="utf-8"
    )
    (versions / "first.py").write_text(
        _REVISION_PY.format(revision="first", parent="None", table="первая"),
        encoding="utf-8",
    )
    (versions / "second.py").write_text(
        _REVISION_PY.format(revision="second", parent='"first"', table="вторая"),
        encoding="utf-8",
    )


def test_the_migrations_are_found_from_a_foreign_working_directory(
    migrations_target, monkeypatch, tmp_path
):
    """Миграции проекта находятся и из чужого рабочего каталога.

    В собранном приложении рабочий каталог чужой: путь, посчитанный от него,
    указал бы в пустоту, и прогон упал бы, не заведя ни одной таблицы.
    """
    monkeypatch.chdir(tmp_path)

    command.upgrade(alembic_config(), INIT_REVISION)

    assert "vacancy" in _tables(migrations_target)


def test_the_schema_is_brought_to_the_latest_revision(
    migrations_target, monkeypatch, tmp_path
):
    """Схема доводится до последней ревизии, а не до первой.

    Остановившись раньше, приложение стартовало бы на базе без колонок,
    которые код уже читает.
    """
    root = tmp_path / "проект"
    _project_of_two_revisions(root, migrations_target)
    monkeypatch.setattr("backend.bootstrap._PROJECT_ROOT", root)

    ensure_schema()

    assert {"первая", "вторая"} <= _tables(migrations_target)
    assert _revision_reached(migrations_target) == "second"


def _revisions_in(paths) -> set[str]:
    """Ревизии, объявленные названными файлами миграций."""
    found = set()
    for path in paths:
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith("revision:") or line.startswith("revision ="):
                found.add(line.split("=", 1)[1].strip().strip("'\""))
                break
    return found


def test_the_build_carries_every_revision_the_sources_can_reach():
    """История миграций в сборке покрывает ту же, до которой доходят исходники.

    Каталог данных у сборки и у исходников один. Запуск из исходников доводит
    базу до своей последней ревизии и пишет её в `alembic_version`; собранный
    exe при старте зовёт `upgrade head`, ищет эту запись в своей истории и, не
    найдя, бросает `CommandError`. Окна у него нет, консоли тоже — человек
    жмёт ярлык, и не происходит ничего. Каждый раз.

    Засевная миграция в сборку не едет нарочно — в ней личные данные, — но
    исключать её надо из содержимого, а не из истории: заглушка с тем же
    номером ревизии оставляет новую базу пустой и не роняет старую.

    Сравнение вложением, а не равенством: сама засевная под версией не ходит, и
    на свежем клоне её в `versions/` нет вовсе. Забытая в сборке новая ревизия
    краснеет всё так же — она была бы слева и не нашлась бы справа.
    """
    root = Path(__file__).resolve().parents[2]
    spec = (root / "JobBot.spec").read_text(encoding="utf-8")
    bundled = [
        root / name
        for name in re.findall(r"'(alembic/[^']+[.]py)'", spec)
        if "env.py" not in name
    ]

    assert _revisions_in((root / "alembic" / "versions").glob("*.py")) <= (
        _revisions_in(bundled)
    )
