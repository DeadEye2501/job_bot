"""Стенд: подмена каталога данных, хранилища ключей и базы.

Порядок в этом файле — часть договора, а не оформление. Каталог подменяется
до первого импорта проекта: `backend/bot.py` вычисляет `MEDIA_DIR` на импорте,
и без подмены импорт модуля создал бы папку в боевом каталоге. Хранилище
ключей подменяется до первого шифрования, схема поднимается после обоих.
"""

import os
import shutil
import tempfile
from pathlib import Path

# Настоящее значение — до подмены строкой ниже. Нужно, чтобы потом сравнить
# с ним `config.get_data_dir()` и поймать тест, который снимет `APPDATA`
# и тем самым откатит стенд на боевой каталог пользователя.
_REAL_APPDATA = os.environ.get("APPDATA")

TMP_ROOT = Path(tempfile.mkdtemp(prefix="jobbot-tests-"))
os.environ["APPDATA"] = str(TMP_ROOT)
os.environ["XDG_DATA_HOME"] = str(TMP_ROOT)

# `adapters.telegram` тянет `pyrogram`, а тот на импорте зовёт
# `asyncio.get_event_loop()`. На Windows `pytest-asyncio` в режиме auto
# успевает испортить состояние event loop policy ещё до первого теста —
# ленивый импорт внутри фикстуры `_sending_locked` ловит это как
# `RuntimeError` на самом первом прогоне. Импорт здесь, во время сбора
# тестов (до того как pytest-asyncio успевает это состояние сломать),
# кладёт модуль в кэш `sys.modules` — повторный `import` в фикстуре ниже
# просто берёт его оттуда.
import adapters.telegram  # noqa: E402, F401 — импорт только ради побочного эффекта
import keyring  # noqa: E402 — только после подмены каталога
import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker  # noqa: E402

from config import APP_NAME  # noqa: E402
from tests.fakes.keyring import MemoryKeyring  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Ревизия init. До `head` не поднимаемся: следующая ревизия засевает личные
# данные и лежит вне репозитория — набор тестов стал бы невоспроизводимым.
INIT_REVISION = "8ba64b863cb1"

# Боевые каталоги данных — то, во что превращается `config.get_data_dir()`
# без подмены `APPDATA`. `_REAL_DATA_DIR` — если переменная была задана до
# подмены; `_FALLBACK_DATA_DIR` — путь, на который `config.py` откатывается,
# когда `APPDATA` не задана вовсе (см. `config._user_data_dir`).
_REAL_DATA_DIR = Path(_REAL_APPDATA) / APP_NAME if _REAL_APPDATA else None
_FALLBACK_DATA_DIR = Path.home() / "AppData" / "Roaming" / APP_NAME


@pytest.fixture(scope="session", autouse=True)
def _temporary_data_dir():
    yield TMP_ROOT
    shutil.rmtree(TMP_ROOT, ignore_errors=True)


@pytest.fixture(scope="session", autouse=True)
def _memory_keyring():
    backend = MemoryKeyring()
    keyring.set_keyring(backend)
    return backend


@pytest.fixture(autouse=True)
def _appdata_guard():
    """Каталог данных не совпадает с боевым и не лежит внутри него.

    Единственная защита от однажды написанного `monkeypatch.delenv("APPDATA")`
    или подпроцесса с вычищенным окружением: без неё `config.get_data_dir()`
    в таких случаях молча откатывается на боевой каталог пользователя
    (`_REAL_DATA_DIR` или `_FALLBACK_DATA_DIR`), и туда же уедут любые
    записи теста. Проверка идёт перед телом каждого теста — до того, как
    он успеет что-то записать.
    """
    from config import get_data_dir

    data_dir = get_data_dir()
    for real_dir in (_REAL_DATA_DIR, _FALLBACK_DATA_DIR):
        if real_dir is None:
            continue
        assert not data_dir.is_relative_to(real_dir), (
            f"каталог данных лежит в боевом каталоге: {data_dir}"
        )


@pytest.fixture(scope="session")
def database_url() -> str:
    # `alembic/env.py` сам вычисляет URL через `config.get_database_url()` и
    # безусловно перезаписывает то, что передано в `Config` (строка 14) —
    # свой путь здесь не приживётся, схема всё равно ляжет по этому URL.
    # Поэтому фикстура отдаёт тот же URL, чтобы `session` подключался
    # туда же, куда `_schema` действительно поднял таблицы.
    from config import get_database_url

    return get_database_url()


@pytest.fixture(scope="session", autouse=True)
def _schema(_memory_keyring, database_url):
    """Схема поднимается один раз на прогон настоящим alembic'ом.

    Синхронная фикстура намеренно: alembic заводит свой цикл событий внутри,
    и из уже работающего цикла его звать нельзя.
    """
    cfg = Config(str(PROJECT_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(PROJECT_ROOT / "alembic"))
    # URL сюда намеренно не кладём: `alembic/env.py` всё равно перезапишет
    # его через `config.get_database_url()` — владелец URL для миграций он,
    # а не этот `Config`. Параметр `database_url` фикстура держит явным
    # порядок вычисления (после `_memory_keyring`), а не для использования.
    command.upgrade(cfg, INIT_REVISION)


@pytest.fixture(autouse=True)
def _sending_locked(monkeypatch):
    """Отправка в Telegram заперта на всё время прогона.

    В боевом коде `SEND_LOCKED = False`. Подделка клиента и так никуда не
    ходит, но запор снимает целый класс аварий: тест, случайно получивший
    настоящий клиент, не разошлёт сообщения живым людям.
    """
    import adapters.telegram

    monkeypatch.setattr(adapters.telegram, "SEND_LOCKED", True)


async def _clear_all_tables(engine: AsyncEngine) -> None:
    """Удаляет все строки из всех таблиц, кроме `alembic_version`.

    Список таблиц берётся из `sqlite_master`, а не из `Base.metadata`: схема
    поднята alembic'ом один раз до ревизии init, и если модели когда-нибудь
    разойдутся со схемой, удаление по метаданным упадёт на несуществующей
    таблице, а по `sqlite_master` — нет. `PRAGMA foreign_keys=OFF` на время
    уборки снимает зависимость от порядка удаления. `sqlite_sequence`
    (счётчики автоинкремента) чистится отдельно, если она вообще есть —
    иначе идентификаторы поедут от прогона к прогону.
    """
    async with engine.connect() as connection:
        await connection.execute(text("PRAGMA foreign_keys=OFF"))
        tables = (
            await connection.execute(
                text(
                    "SELECT name FROM sqlite_master "
                    "WHERE type='table' AND name != 'alembic_version' "
                    "AND name NOT LIKE 'sqlite_%'"
                )
            )
        ).scalars().all()
        for table in tables:
            await connection.execute(text(f'DELETE FROM "{table}"'))

        has_sequence = (
            await connection.execute(
                text(
                    "SELECT 1 FROM sqlite_master "
                    "WHERE type='table' AND name = 'sqlite_sequence'"
                )
            )
        ).first()
        if has_sequence:
            await connection.execute(text("DELETE FROM sqlite_sequence"))

        await connection.commit()


@pytest.fixture
async def session(_schema, database_url):
    """Сессия на отдельном движке; изоляция — уборкой таблиц, не откатом.

    Откат тут не работает: pysqlite (драйвер под `aiosqlite`) откладывает
    `BEGIN` до первого DML и не даёт SQLAlchemy настоящей внешней
    транзакции, которую можно было бы откатить, — `RELEASE SAVEPOINT`
    фиксирует данные из-под `session.commit()` насовсем, независимо от
    того, что потом делает внешняя транзакция (проверено отдельно:
    `rollback()` её не отменяет). Поэтому после теста таблицы просто
    чистятся, а не откатываются.

    Движок создаётся на каждый тест и закрывается после: пул соединений
    привязан к циклу событий, и переиспользование движка между тестами с
    разными циклами ломается непредсказуемо.
    """
    from adapters.db import make_engine

    engine = make_engine(database_url)
    maker = async_sessionmaker(bind=engine, expire_on_commit=False)
    opened = maker()
    try:
        yield opened
    finally:
        await opened.close()
        await _clear_all_tables(engine)
        await engine.dispose()
