"""Стенд: подмена каталога данных, хранилища ключей и базы.

Порядок в этом файле — часть договора, а не оформление. Каталог данных и
хранилище ключей подменяются на уровне модуля, до первого импорта проекта:
`backend/bot.py` вычисляет `MEDIA_DIR` на импорте, и без подмены каталога
импорт создал бы папку в боевом каталоге пользователя. Схема поднимается
после обоих.
"""

import os
import shutil
import tempfile
from pathlib import Path

# Настоящее значение — до подмены строкой ниже. Нужно, чтобы потом сравнить
# с ним `config._user_data_dir()` и поймать тест, который снимет `APPDATA`
# и тем самым откатит стенд на боевой каталог пользователя.
_REAL_APPDATA = os.environ.get("APPDATA")

TMP_ROOT = Path(tempfile.mkdtemp(prefix="jobbot-tests-"))
os.environ["APPDATA"] = str(TMP_ROOT)
os.environ["XDG_DATA_HOME"] = str(TMP_ROOT)

import keyring  # noqa: E402 — только после подмены каталога

from tests.fakes.keyring import MemoryKeyring  # noqa: E402

# Подмена хранилища ключей — здесь, а не в фикстуре: фикстура срабатывает в
# setup первого теста, а сбор тестов идёт раньше и уже импортирует всё дерево
# проекта. Сегодня ни один модуль не читает мастер-ключ на импорте, но цена
# ошибки — настоящий ключ шифрования пользователя в памяти тестового
# процесса, поэтому подмена стоит там же, где подмена каталога: до первого
# импорта проекта, а не после сбора.
MEMORY_KEYRING = MemoryKeyring()
keyring.set_keyring(MEMORY_KEYRING)

# `adapters.telegram` тянет `pyrogram`, а тот на импорте зовёт
# `asyncio.get_event_loop()`. На Windows `pytest-asyncio` в режиме auto
# успевает испортить состояние event loop policy ещё до первого теста —
# ленивый импорт внутри фикстуры `_sending_locked` ловит это как
# `RuntimeError` на самом первом прогоне. Импорт здесь, во время сбора
# тестов (до того как pytest-asyncio успевает это состояние сломать),
# кладёт модуль в кэш `sys.modules` — повторный `import` в фикстуре ниже
# просто берёт его оттуда.
import adapters.telegram  # noqa: E402, F401 — импорт только ради побочного эффекта
import pyrogram  # noqa: E402
import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import (  # noqa: E402
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
)

from config import APP_NAME  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Ревизия init. До `head` не поднимаемся: следующая ревизия засевает личные
# данные и лежит вне репозитория — набор тестов стал бы невоспроизводимым.
INIT_REVISION = "8ba64b863cb1"

# Боевые каталоги данных — то, во что превращается `config._user_data_dir()`
# без подмены `APPDATA`. `_REAL_DATA_DIR` — если переменная была задана до
# подмены; `_FALLBACK_DATA_DIR` — путь, на который `config.py` откатывается,
# когда `APPDATA` не задана вовсе (см. `config._user_data_dir`).
_REAL_DATA_DIR = Path(_REAL_APPDATA) / APP_NAME if _REAL_APPDATA else None
_FALLBACK_DATA_DIR = Path.home() / "AppData" / "Roaming" / APP_NAME


@pytest.fixture(scope="session", autouse=True)
def _temporary_data_dir():
    yield TMP_ROOT
    shutil.rmtree(TMP_ROOT, ignore_errors=True)


@pytest.fixture(scope="session")
def memory_keyring() -> MemoryKeyring:
    """Доступ к подставному хранилищу; сама подмена — на уровне модуля."""
    return MEMORY_KEYRING


@pytest.fixture(autouse=True)
def _appdata_guard():
    """Каталог данных не совпадает с боевым и не лежит внутри него.

    Зовёт `config._user_data_dir()`, а не `get_data_dir()`: второй делает
    `mkdir`, то есть сторож создавал бы боевой каталог ровно в том случае,
    от которого сторожит.

    Ловит не `monkeypatch.delenv("APPDATA")` внутри теста — `monkeypatch`
    сам возвращает переменную на место в teardown, до сборки следующего
    теста, а у этой фикстуры нет `yield`: она отрабатывает только в setup,
    до тела текущего теста. Реальный случай — правка `os.environ["APPDATA"]`
    напрямую (без `monkeypatch`) или через `monkeypatch` сессионного/модульного
    масштаба, не убранная за собой предыдущим тестом: тогда каталог данных
    к моменту setup следующего теста уже молча смотрит на боевой каталог
    пользователя (`_REAL_DATA_DIR` или `_FALLBACK_DATA_DIR`), и туда же уедут
    любые записи. Проверка идёт перед телом каждого теста — до того, как он
    успеет что-то записать.
    """
    import config

    data_dir = config._user_data_dir()
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
def _schema(database_url):
    """Схема поднимается один раз на прогон настоящим alembic'ом.

    Синхронная фикстура намеренно: alembic заводит свой цикл событий внутри,
    и из уже работающего цикла его звать нельзя.
    """
    cfg = Config(str(PROJECT_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(PROJECT_ROOT / "alembic"))
    # URL сюда намеренно не кладём: `alembic/env.py` всё равно перезапишет
    # его через `config.get_database_url()` — владелец URL для миграций он,
    # а не этот `Config`. Параметр `database_url` фикстура держит явным
    # порядок вычисления, а не для использования.
    command.upgrade(cfg, INIT_REVISION)


class TelegramReached(BaseException):
    """Тест дотянулся до настоящего Telegram.

    Наследник `BaseException`, а не `Exception`, намеренно: боевой код
    оборачивает вызовы клиента в `except Exception` — `backend/bot.py:140`
    вокруг `download_media`, `backend/bot.py:992` вокруг `read_chat_history`.
    Наследника `Exception` эти блоки проглотили бы, и тест, ушедший в живой
    Telegram, получил бы запись в лог и зелёный прогон — ровно тот отказ,
    ради предотвращения которого запор и ставится.
    """


@pytest.fixture(autouse=True)
def _telegram_is_unreachable(monkeypatch):
    """Обычные запросы клиента не уходят в сеть: `Client.invoke` заперт.

    Через `pyrogram.Client.invoke` приходят `send_message`, `send_photo`,
    `send_document`, `read_chat_history` и прочие обычные вызовы. Запирать
    `adapters.telegram.SEND_LOCKED` для этого мало — `backend/bot.py` зовёт
    методы клиента напрямую, минуя `send_dm`.

    Единственной воронкой Pyrogram `Client.invoke` НЕ является. Под часть
    работы библиотека поднимает отдельные `Session` и зовёт `Session.invoke`
    напрямую: так идут заливка файла (`save_file`), скачивание медиа вместе с
    обращением к раздающему узлу, подключение и авторизация. Через первый из
    этих путей `send_photo`/`send_document` с путём к файлу сперва заливали
    файл на сервера Telegram и упирались в запор только на последнем шаге —
    файл к тому моменту уже был там.

    Поэтому запор двойной: подменяются обе воронки. Нижняя, `Session.invoke`,
    ловит и то, что до верхней не доходит.

    Тестам, которым нужны эти пути, настоящий клиент передавать нельзя ни
    при каких условиях — только подделку из `tests/fakes/telegram.py`.
    """

    async def _refuse(*_args, **_kwargs):
        raise TelegramReached(
            "тест дотянулся до настоящего Telegram: вызван invoke у клиента или "
            "сессии Pyrogram. Передайте в проверяемый код подделку из "
            "tests/fakes/telegram.py."
        )

    monkeypatch.setattr(pyrogram.Client, "invoke", _refuse)
    monkeypatch.setattr(pyrogram.session.Session, "invoke", _refuse)


@pytest.fixture(autouse=True)
def _sending_locked(monkeypatch):
    """Второй слой запора: в боевом коде `SEND_LOCKED = False`.

    Читается ровно в `adapters.telegram.send_dm`. Держим вместе с подменой
    `pyrogram.Client.invoke` выше: тот ловит уже совершённый вызов, а этот
    не даёт `send_dm` дойти до вызова вообще.
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


@pytest.fixture(autouse=True)
async def _clean_database(_schema, database_url):
    """База пуста после каждого теста, как бы тест до неё ни добрался.

    Уборка висит здесь, а не на фикстуре `session`, потому что через сессию
    до базы доходят не все: `backend/runtime_settings.py` принимает фабрику
    сессий и коммитит внутри себя, и тест, построивший фабрику поверх
    собственного движка, оставил бы закоммиченные строки следующим файлам —
    протекло бы падениями, зависящими от порядка.

    Своя пара «движок + соединение» на уборку нужна потому, что движок
    теста к этому моменту уже закрыт: фикстура автоиспользуемая, значит
    поднимается раньше остальных функциональных и разбирается позже них.
    Она же и причина, по которой упавшее `session.close()` не оставляет
    базу грязной: pytest доводит до конца все финализаторы, даже если
    предыдущий бросил.
    """
    yield

    from adapters.db import make_engine

    cleaner = make_engine(database_url)
    try:
        await _clear_all_tables(cleaner)
    finally:
        await cleaner.dispose()


@pytest.fixture
async def engine(_schema, database_url):
    """Движок на отдельный тест.

    Создаётся на каждый тест и закрывается после: пул соединений привязан к
    циклу событий, и переиспользование движка между тестами с разными
    циклами ломается непредсказуемо.
    """
    from adapters.db import make_engine

    created = make_engine(database_url)
    try:
        yield created
    finally:
        await created.dispose()


@pytest.fixture
def session_factory(engine) -> async_sessionmaker[AsyncSession]:
    """Фабрика сессий — то, что принимают модули, коммитящие внутри себя.

    `backend/runtime_settings.py` берёт именно её, а не готовую сессию:
    каждый `set_*` открывает свою и коммитит. Стоит поверх того же движка,
    что и `session`, — тест может пользоваться обоими сразу.
    """
    return async_sessionmaker(bind=engine, expire_on_commit=False)


@pytest.fixture
async def session(session_factory):
    """Открытая сессия; изоляция — уборкой таблиц (`_clean_database`), не откатом.

    Откат тут не работает: pysqlite (драйвер под `aiosqlite`) откладывает
    `BEGIN` до первого DML и не даёт SQLAlchemy настоящей внешней
    транзакции, которую можно было бы откатить, — `RELEASE SAVEPOINT`
    фиксирует данные из-под `session.commit()` насовсем, независимо от
    того, что потом делает внешняя транзакция (проверено отдельно:
    `rollback()` её не отменяет). Поэтому после теста таблицы просто
    чистятся, а не откатываются.
    """
    opened = session_factory()
    try:
        yield opened
    finally:
        await opened.close()
