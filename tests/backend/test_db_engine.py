"""Следствия настроек, которые ставятся на каждое соединение с базой.

SQLite по умолчанию внешние ключи не стережёт, пишет журнал так, что читатель
и писатель мешают друг другу, и на занятую базу отвечает отказом мгновенно.
Приложение же ходит в неё из трёх мест разом — обход каналов, слушатель личных
сообщений и окно, — и с умолчаниями это даёт «база занята» на ровном месте и
тихо порченные ссылки между строками.

Настройки ставятся на каждое соединение, а не один раз: соединения берутся из
общего запаса, и новое приходит с чистыми умолчаниями.
"""

import pytest
from sqlalchemy import text

from adapters.db import check, make_engine


@pytest.fixture
async def engine_on_disk(tmp_path):
    """Настоящий движок на файле: в памяти журнал ведёт себя иначе."""
    engine = make_engine(f"sqlite+aiosqlite:///{tmp_path / 'проба.db'}")
    yield engine
    await engine.dispose()


async def _pragma(engine, name):
    """Читает настройку у свежего соединения."""
    async with engine.connect() as conn:
        return (await conn.execute(text(f"PRAGMA {name}"))).scalar_one()


async def test_foreign_keys_are_enforced(engine_on_disk):
    """Внешние ключи стерегутся.

    Без этого удаление канала оставляет в событиях мусора ссылку на
    несуществующую строку, хотя объявление обещает её обнулить.
    """
    assert await _pragma(engine_on_disk, "foreign_keys") == 1


async def test_the_journal_lets_readers_and_writers_coexist(engine_on_disk):
    """Журнал переведён в режим, где чтение не ждёт записи.

    Обход каналов пишет минутами; с умолчанием окно всё это время
    получало бы «база занята» на каждый запрос.
    """
    assert await _pragma(engine_on_disk, "journal_mode") == "wal"


async def test_a_busy_base_is_waited_for(engine_on_disk):
    """На занятую базу соединение ждёт, а не отказывает сразу.

    Умолчание — ноль: два одновременных обращения из трёх мест
    приложения давали бы отказ при первом же пересечении.
    """
    assert await _pragma(engine_on_disk, "busy_timeout") == 5000


async def test_every_connection_gets_the_settings(engine_on_disk):
    """Настройки достаются каждому соединению, а не первому.

    Соединения открываются здесь одновременно нарочно: последовательные
    вернулись бы из общего запаса тем же самым, и «настроено однажды» не
    отличалось бы от «настроено каждому». Приложение же ходит в базу из
    трёх мест разом, и второму соединению умолчания достались бы чистые.
    """
    async with engine_on_disk.connect() as first:
        async with engine_on_disk.connect() as second:
            values = [
                (await conn.execute(text("PRAGMA foreign_keys"))).scalar_one()
                for conn in (first, second)
            ]

    assert values == [1, 1]


async def test_the_check_names_the_engine_and_its_version(engine_on_disk):
    """Проверка соединения называет движок и его версию.

    Её ответ показывают пользователю в настройках: «подключение есть» без
    подробностей не отличить от заглушки.
    """
    answer = await check(engine_on_disk)

    assert answer.startswith("SQLite ")
    assert answer.split()[1][0].isdigit()
