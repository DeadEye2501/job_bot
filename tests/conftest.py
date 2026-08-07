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
from sqlalchemy.ext.asyncio import async_sessionmaker  # noqa: E402

from tests.fakes.keyring import MemoryKeyring  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Ревизия init. До `head` не поднимаемся: следующая ревизия засевает личные
# данные и лежит вне репозитория — набор тестов стал бы невоспроизводимым.
INIT_REVISION = "8ba64b863cb1"


@pytest.fixture(scope="session", autouse=True)
def _temporary_data_dir():
    yield TMP_ROOT
    shutil.rmtree(TMP_ROOT, ignore_errors=True)


@pytest.fixture(scope="session", autouse=True)
def _memory_keyring():
    backend = MemoryKeyring()
    keyring.set_keyring(backend)
    return backend


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
    cfg.set_main_option("sqlalchemy.url", database_url)
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


@pytest.fixture
async def session(_schema, database_url):
    """Сессия внутри транзакции, которая откатывается после теста.

    `join_transaction_mode="create_savepoint"` нужен потому, что репозиторий
    местами открывает транзакцию сам через `async with session.begin()`: без
    этого внутренний `begin()` подрался бы с внешней транзакцией отката.

    Движок создаётся на каждый тест и закрывается после: пул соединений
    привязан к циклу событий, и переиспользование движка между тестами с
    разными циклами ломается непредсказуемо.
    """
    from adapters.db import make_engine

    engine = make_engine(database_url)
    try:
        async with engine.connect() as connection:
            transaction = await connection.begin()
            maker = async_sessionmaker(
                bind=connection,
                join_transaction_mode="create_savepoint",
                expire_on_commit=False,
            )
            async with maker() as opened:
                yield opened
            await transaction.rollback()
    finally:
        await engine.dispose()
