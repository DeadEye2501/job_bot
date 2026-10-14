"""Короткие обращения к базе из теста.

Положить готовые строки и прочитать результат обратно — работа, которую
повторяет каждый тест, идущий в базу; тесты миграций читают ещё и сам файл
базы мимо ORM. Построение самих строк остаётся за фабриками: здесь только
доступ.

От `tests.conftest` отличается тем, что здесь не фикстуры. Стенд заводит
подключение и убирает за тестом сам, без спроса; эти же обращения тест
делает по своей воле и там, где ему нужно, — фикстурой такое не выражается.
"""

import sqlite3

from sqlalchemy import select

from backend.repository.aggregator_resumes import resumes_of


async def put(session_factory, *rows) -> None:
    """Положить строки в базу до того, как их прочитает проверяемый код."""
    async with session_factory() as session:
        async with session.begin():
            for row in rows:
                session.add(row)


async def only_row(session_factory, model):
    """Единственная строка таблицы, прочитанная заново из базы."""
    async with session_factory() as session:
        return (await session.scalars(select(model))).first()


async def all_rows(session_factory, model) -> list:
    """Все строки таблицы, прочитанные заново из базы.

    Нужен там, где предмет проверки — само их число: «обновил, а не завёл
    вторую» видно только по полному содержимому таблицы.
    """
    async with session_factory() as session:
        return list((await session.scalars(select(model))).all())


async def resume_marks(session_factory, aggregator_id: int) -> list[tuple[str, bool]]:
    """Резюме сайта в порядке сайта: название и отметка «откликаться этим»."""
    async with session_factory() as session:
        return [(r.title, r.is_chosen) for r in await resumes_of(session, aggregator_id)]


def sqlite_rows(db_file, sql: str) -> list[tuple]:
    """Строки запроса к файлу базы мимо ORM.

    Тестам миграций модели не годятся: они описывают `head`, а смотреть надо
    на базу, стоящую на другой ревизии.
    """
    connection = sqlite3.connect(db_file)
    try:
        return connection.execute(sql).fetchall()
    finally:
        connection.close()


def sqlite_write(db_file, *statements: str) -> None:
    """Записать в файл базы мимо ORM одной сделкой — по той же причине, что
    `sqlite_rows`: модели описывают `head`, а база стоит на другой ревизии."""
    connection = sqlite3.connect(db_file)
    try:
        for sql in statements:
            connection.execute(sql)
        connection.commit()
    finally:
        connection.close()


def sqlite_tables(db_file) -> set[str]:
    """Имена таблиц в файле базы — то, что ревизия завела или сняла."""
    return {name for (name,) in sqlite_rows(db_file, "SELECT name FROM sqlite_master WHERE type = 'table'")}
