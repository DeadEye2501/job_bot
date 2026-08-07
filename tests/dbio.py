"""Короткие обращения к базе из теста.

Положить готовые строки и прочитать результат обратно — работа, которую
повторяет каждый тест, идущий в базу. Построение самих строк остаётся за
`tests.factories`: здесь только доступ.

От `tests.conftest` отличается тем, что здесь не фикстуры. Стенд заводит
подключение и убирает за тестом сам, без спроса; эти же три обращения тест
делает по своей воле и там, где ему нужно, — фикстурой такое не выражается.
"""

from sqlalchemy import select


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
