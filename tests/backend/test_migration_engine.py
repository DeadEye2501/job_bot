"""Следствия того, каким движком alembic открывает базу и как его закрывает.

Соединение он до сих пор собирал сам, мимо `adapters/db.py`. Разница не
косметическая: сид (`aa4e0de05368`) пишет в JSON-колонки, а без сериализатора
из `adapters/db.py` кириллица ложится туда экранированной и становится
недостижимой для поиска.

Наблюдать эту разницу тестом нельзя: сид лежит вне репозитория, в нём личные
данные, и стенд до него не поднимается. Наблюдаема из трёх PRAGMA ровно одна —
`journal_mode`: она записана в самом файле базы и переживает соединение, тогда
как внешние ключи, подменённый `lower` и сериализатор живут ровно столько,
сколько открыто соединение. По ней и видно, чьим движком схему поднимали.

Внешние ключи наблюдаемы иначе — не по файлу, а по тому, что при них не
проходит: пересоздание таблицы, на которую ссылаются. Отсюда учебная пара
ревизий ниже.
"""

import sqlite3

import pytest
from alembic import command

from backend.bootstrap import alembic_config
from tests.conftest import INIT_REVISION

# Учебная пара таблиц: у «дома» есть «жильцы», и связь между ними настоящая.
# Проектных таблиц для этого не берут: они переезжают вместе со схемой, и
# сторож ловил бы их переезды вместо того, ради чего заведён.
_HOUSE_REVISION = '''
revision = "дом_заведён"
down_revision = None

from alembic import op


def upgrade():
    op.execute("CREATE TABLE дом (id INTEGER PRIMARY KEY)")
    op.execute(
        "CREATE TABLE жилец ("
        "id INTEGER PRIMARY KEY, дом_id INTEGER REFERENCES дом(id))"
    )
    op.execute("INSERT INTO дом (id) VALUES (1)")
    op.execute("INSERT INTO жилец (id, дом_id) VALUES (1, 1)")


'''

_REBUILD_HEAD = '''
revision = "дом_перестроен"
down_revision = "дом_заведён"

import sqlalchemy as sa
from alembic import op


def upgrade():
{quench}
    with op.batch_alter_table("дом", recreate="always") as batch:
        batch.add_column(sa.Column("этажей", sa.Integer()))
'''

# Гашение действует до конца прогона миграций, и вернуть ключи внутри той же
# ревизии нечем: копирующий `INSERT` открывает настоящую транзакцию, а при
# открытой `PRAGMA foreign_keys` — пустое место (замерено: следующая ревизия
# видит `foreign_keys = 0`). Дальше прогона это не уходит — соединение
# закрывается вместе с движком, — но ревизии за гасящей идут без ключей, и
# ставить её надо последней.
_QUENCHED = _REBUILD_HEAD.format(quench='    op.execute("PRAGMA foreign_keys=OFF")')
_AS_IS = _REBUILD_HEAD.format(quench="")


def _learning_project(tmp_path, rebuild: str):
    """Настройка alembic, у которой ревизии свои, а `env.py` проектный.

    Подменяется только каталог версий: движок, PRAGMA и порядок соединения
    остаются те же, которыми поднимается настоящая схема, — иначе сторож
    смотрел бы на чужие правила.
    """
    versions = tmp_path / "версии"
    versions.mkdir()
    (versions / "дом.py").write_text(_HOUSE_REVISION, encoding="utf-8")
    (versions / "перестройка.py").write_text(rebuild, encoding="utf-8")
    cfg = alembic_config()
    cfg.set_main_option("version_locations", str(versions))
    return cfg


def _tenants(db_file) -> list[tuple]:
    connection = sqlite3.connect(db_file)
    try:
        return connection.execute("SELECT id, дом_id FROM жилец").fetchall()
    finally:
        connection.close()


def test_a_rebuild_that_did_not_quench_the_keys_is_refused(
    migrations_target, tmp_path
):
    """Пересоздание таблицы без гашения ключей миграция не проводит.

    На SQLite `batch_alter_table` меняет колонки только пересозданием: копия,
    удаление прежней таблицы, переименование. Удаление при включённых ключах
    задевает всех, кто на прежнюю таблицу ссылается, — и получает отказ.

    Это же и сторож самих ключей: раньше alembic собирал соединение сам, и
    внешние ключи в нём стояли выключенными. Верни он такое соединение — и
    пересоздание пройдёт молча, а вместе с ним мимо миграций пройдут и
    остальные правила проекта.
    """
    cfg = _learning_project(tmp_path, _AS_IS)

    with pytest.raises(Exception, match="FOREIGN KEY"):
        command.upgrade(cfg, "head")


def test_a_rebuild_that_quenched_the_keys_keeps_the_rows_pointing_at_the_table(
    migrations_target, tmp_path
):
    """Погасив ключи, пересоздание не теряет строк, ссылающихся на таблицу.

    Сторож учебный: своей `batch_alter_table` в проекте пока нет, и держит он
    не её, а рецепт, который первая же обязана повторить. Забытое гашение в
    будущей настоящей миграции он не поймает — оно упрётся в соседнюю
    проверку выше и в собственный прогон.

    Гашение действует потому, что pysqlite откладывает `BEGIN` до первой
    записи: миграцию alembic оборачивает транзакцией, но к моменту `PRAGMA`
    она ещё не началась. Внутри начавшейся `PRAGMA foreign_keys` — пустое
    место, и вернуть ключи тем же способом уже нельзя.
    """
    cfg = _learning_project(tmp_path, _QUENCHED)

    command.upgrade(cfg, "head")

    assert _tenants(migrations_target) == [(1, 1)]


def test_the_database_alembic_touched_stays_in_wal(migrations_target):
    """База, через которую прошёл alembic, остаётся в журнале WAL.

    Собранный на месте движок не выпускает PRAGMA вовсе, и файл остаётся в
    режиме `delete` — вместе с ним мимо миграций проходят и остальные правила
    проекта, которых по файлу уже не видно.
    """
    db_file = migrations_target

    command.upgrade(alembic_config(), INIT_REVISION)

    connection = sqlite3.connect(db_file)
    try:
        mode = connection.execute("PRAGMA journal_mode").fetchone()[0]
    finally:
        connection.close()

    assert mode == "wal"


def test_a_migration_that_blew_up_lets_go_of_the_database(migrations_target):
    """Упавшая миграция отпускает базу, а не держит её открытой.

    Спутник `-wal` живёт ровно столько, сколько открыто последнее соединение.
    Оставшийся после падения означает, что соединение висит в пуле: на Windows
    такой файл нельзя ни переименовать, ни удалить, а вызывающий, который хотел
    показать беду и предложить откат, упирается в занятый файл.
    """
    db_file = migrations_target
    prepared = sqlite3.connect(db_file)
    try:
        prepared.execute("CREATE TABLE company (id INTEGER PRIMARY KEY)")
        prepared.commit()
    finally:
        prepared.close()

    with pytest.raises(Exception, match="company"):
        command.upgrade(alembic_config(), INIT_REVISION)

    assert not db_file.with_name(db_file.name + "-wal").exists()
