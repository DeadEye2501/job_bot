"""Схема базы и объявления моделей не разошлись.

Схему пишет миграция, а код читает объявления моделей, и сверять их до сих пор
было нечем: миграция пересобирается руками, и забытая в ней колонка всплывает
уже в бою — обращением к тому, чего в базе нет.

Сравнение идёт по той же базе, что поднял стенд: alembic сам говорит, чем
нынешняя схема отличается от объявленной. Пустой ответ и есть «не разошлись».
"""

from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import create_engine

from backend.models import Base


def test_the_schema_says_the_same_as_the_models(database_url):
    """Схема поднятой базы отвечает объявлениям моделей до последней колонки.

    Разойтись они могут в обе стороны: колонка, добавленная в модель без
    миграции, роняет первое же обращение к ней, а колонка, снесённая из модели
    и оставшаяся в схеме, тихо копит мусор и путает следующую пересборку.

    Соединение синхронное: alembic заводит свой цикл событий внутри, и из
    асинхронного движка его звать нечем.
    """
    engine = create_engine(database_url.replace("sqlite+aiosqlite", "sqlite"))
    try:
        with engine.connect() as connection:
            found = compare_metadata(
                MigrationContext.configure(connection), Base.metadata
            )
    finally:
        engine.dispose()

    assert found == []
