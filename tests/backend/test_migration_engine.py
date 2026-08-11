"""Следствия того, каким движком alembic открывает базу и как его закрывает.

Соединение он до сих пор собирал сам, мимо `adapters/db.py`. Разница не
косметическая: сид (`aa4e0de05368`) пишет в JSON-колонки, а без сериализатора
из `adapters/db.py` кириллица ложится туда экранированной и становится
недостижимой для поиска — с этого пункт роадмапы и начался.

Наблюдать эту разницу тестом нельзя: сид лежит вне репозитория, в нём личные
данные, и стенд до него не поднимается. Наблюдаема из трёх PRAGMA ровно одна —
`journal_mode`: она записана в самом файле базы и переживает соединение, тогда
как внешние ключи, подменённый `lower` и сериализатор живут ровно столько,
сколько открыто соединение. По ней и видно, чьим движком схему поднимали.
"""

import sqlite3

import pytest
from alembic import command

from backend.bootstrap import alembic_config
from tests.conftest import INIT_REVISION


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
