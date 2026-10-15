"""Стенд: подмена каталога данных, хранилища ключей и базы.

Порядок в этом файле — часть договора, а не оформление. Каталог данных и
хранилище ключей подменяются на уровне модуля, до первого импорта проекта:
`backend/bot/media.py` вычисляет `MEDIA_DIR` на импорте, и без подмены каталога
импорт создал бы папку в боевом каталоге пользователя. Схема поднимается
после обоих.
"""

import asyncio
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
import httpx2  # noqa: E402
import pyrogram  # noqa: E402
import pytest  # noqa: E402
from alembic import command  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import (  # noqa: E402
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
)

from backend.bootstrap import alembic_config  # noqa: E402
from config import APP_NAME  # noqa: E402


# Ревизия init — первая и из дерева не уходит. Тестам движка миграций нужна
# просто существующая ревизия; сам стенд поднимается до `head`.
INIT_REVISION = "032b8b1c9f8a"

# Боевые каталоги данных — то, во что превращается `config._user_data_dir()`
# без подмены `APPDATA`. `_REAL_DATA_DIR` — если переменная была задана до
# подмены; `_FALLBACK_DATA_DIR` — путь, на который `config.py` откатывается,
# когда `APPDATA` не задана вовсе (см. `config._user_data_dir`).
_REAL_DATA_DIR = Path(_REAL_APPDATA) / APP_NAME if _REAL_APPDATA else None


def _data_dir_without_appdata() -> Path:
    """Куда `config.py` откатывается, когда `APPDATA` не задана вовсе.

    Спрашивается у самого `config`, а не переписывается сюда: путь отката —
    его решение, и вторая запись разошлась бы с ним молча, оставив охрану
    ниже сторожить каталог, которого больше нет.
    """
    import config

    saved = os.environ.pop("APPDATA", None)
    try:
        return config._user_data_dir()
    finally:
        if saved is not None:
            os.environ["APPDATA"] = saved


_FALLBACK_DATA_DIR = _data_dir_without_appdata()


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


@pytest.fixture
def migrations_target(tmp_path, monkeypatch) -> Path:
    """Уводит настоящий прогон миграций на свежий файл базы и отдаёт его путь.

    Путь подменяется у `config`, а не в `Config`: `alembic/env.py` первой же
    строкой перезаписывает `sqlalchemy.url` тем, что вернёт
    `get_database_url()`, — переданный в `Config` не прижился бы.
    """
    db_file = tmp_path / "fresh.db"
    monkeypatch.setattr(
        "config.get_database_url",
        lambda: f"sqlite+aiosqlite:///{db_file.as_posix()}",
    )
    return db_file


@pytest.fixture(scope="session", autouse=True)
def _schema(database_url):
    """Схема поднимается один раз на прогон настоящим alembic'ом.

    Синхронная фикстура намеренно: alembic заводит свой цикл событий внутри,
    и из уже работающего цикла его звать нельзя. Параметр `database_url`
    задаёт порядок вычисления и адрес уборки.

    Строки, которые засевает ревизия, убираются сразу: иначе их видел бы
    только первый тест прогона, а следующие — нет, и исход зависел бы от
    порядка тестов.
    """
    command.upgrade(alembic_config(), "head")
    asyncio.run(_empty_database(database_url))


class TelegramReached(BaseException):
    """Тест дотянулся до настоящего Telegram.

    Наследник `BaseException`, а не `Exception`, намеренно: боевой код
    оборачивает вызовы клиента в `except Exception` — `bot/media.download_media`
    вокруг скачивания и `bot/chat` вокруг `read_chat_history`.
    Наследника `Exception` эти блоки проглотили бы, и тест, ушедший в живой
    Telegram, получил бы запись в лог и зелёный прогон — ровно тот отказ,
    ради предотвращения которого запор и ставится.
    """


@pytest.fixture(autouse=True)
def _telegram_is_unreachable(monkeypatch):
    """Обычные запросы клиента не уходят в сеть: `Client.invoke` заперт.

    Через `pyrogram.Client.invoke` приходят `send_message`, `send_photo`,
    `send_document`, `read_chat_history` и прочие обычные вызовы. Запирать
    `adapters.telegram.SEND_LOCKED` для этого мало — `backend/bot/` зовёт
    методы клиента напрямую, минуя `send_dm`.

    Единственной воронкой Pyrogram `Client.invoke` НЕ является: под заливку
    файла, скачивание медиа и подключение библиотека поднимает отдельные
    `Session`. Через первый из этих путей `send_photo`/`send_document` с путём
    к файлу сперва заливали файл на сервера Telegram и упирались в запор
    только на последнем шаге — файл к тому моменту уже был там.

    Запоров поэтому две пары. На обмене — `Client.invoke` и `Session.send`:
    ловят того, кто уже держит живой клиент или сессию. Именно `send`, а не
    `Session.invoke`: `invoke` сам сводится к `send`.

    На сокете — `Session.start` и `Auth.create`: обе открывают соединение до
    первого обмена, и запор на обмене пропускал бы их ровно до того мига,
    когда подключение уже установлено. Авторизация вынесена отдельно от
    сессии потому, что зовёт собственный `Auth.invoke` другого класса.

    Тестам, которым нужны эти пути, настоящий клиент передавать нельзя ни
    при каких условиях — только подделку из `tests/fakes/telegram.py`.
    """

    async def _refuse(*_args, **_kwargs):
        raise TelegramReached(
            "тест дотянулся до настоящего Telegram: вызван invoke у клиента, "
            "обмен или подключение сессии Pyrogram, либо создание ключа "
            "авторизации. Передайте в проверяемый код подделку из "
            "tests/fakes/telegram.py."
        )

    monkeypatch.setattr(pyrogram.Client, "invoke", _refuse)
    monkeypatch.setattr(pyrogram.session.Session, "send", _refuse)
    monkeypatch.setattr(pyrogram.session.Session, "start", _refuse)
    monkeypatch.setattr(pyrogram.session.Auth, "create", _refuse)


class ProviderReached(BaseException):
    """Тест дотянулся до настоящего API Anthropic.

    Наследник `BaseException` по той же причине, что у `TelegramReached`:
    адаптер ловит ошибки SDK, и наследника `Exception` проглотил бы.
    """


@pytest.fixture(autouse=True)
def _anthropic_is_unreachable(monkeypatch):
    """Настоящий транспорт `httpx2` заперт; подделки ходят через `MockTransport`.

    SDK Anthropic ходит своим клиентом, мимо подделок `tests/fakes/llm.py`, и
    тест с забытой подделкой ушёл бы к настоящей модели за деньги. Запор стоит
    на транспорте, а не на клиенте: клиента SDK собирает сам, и подменить его
    в каждом месте сборки нельзя.
    """

    async def _refuse(*_args, **_kwargs):
        raise ProviderReached(
            "тест дотянулся до настоящего API Anthropic. Передайте в проверяемый "
            "код подделку из tests/fakes/claude.py."
        )

    monkeypatch.setattr(httpx2.AsyncHTTPTransport, "handle_async_request", _refuse)


@pytest.fixture(autouse=True)
def _claude_code_is_unreachable(monkeypatch):
    """Настоящий Claude Code из тестов не запускается: запуск процесса заперт.

    Каждый запрос тратит лимит подписки человека. Подделка
    `tests/fakes/claude_code.py` подменяет этот же вход поверх запора.

    Живой процесс модуль держит между запросами, и тест, оставивший его,
    передал бы следующему чужой процесс — поэтому после теста он забывается.
    """
    from adapters import claude_code_process

    async def _refuse(*_args, **_kwargs):
        raise ProviderReached(
            "тест запустил настоящий Claude Code. Подставьте подделку из "
            "tests/fakes/claude_code.py."
        )

    monkeypatch.setattr(claude_code_process, "spawn_cli", _refuse)
    yield
    claude_code_process._session = None
    claude_code_process._closing = False


class EngineReached(BaseException):
    """Тест загрузил настоящую модель эмбеддингов.

    Наследник `BaseException` по той же причине, что у соседей: адаптер
    превращает беды движка в «модель недоступна», и наследника `Exception`
    проглотил бы.
    """


@pytest.fixture(autouse=True)
def _model_engine_is_locked(monkeypatch):
    """Настоящий движок эмбеддингов из тестов не грузится.

    Тест с забытой подделкой поднял бы модель на сотни мегабайт и прошёл бы
    зелёным; подделка `tests/fakes/gguf.py` подменяет этот же вход поверх запора.
    """
    from adapters import gguf_embed

    def _refuse(*_args, **_kwargs):
        raise EngineReached(
            "тест грузит настоящую модель эмбеддингов. Подставьте подделку из "
            "tests/fakes/gguf.py."
        )

    monkeypatch.setattr(gguf_embed, "_open_model", _refuse)


@pytest.fixture(autouse=True)
def _sending_locked(monkeypatch):
    """Второй слой запора: в боевом коде `SEND_LOCKED = False`.

    Читается ровно в `adapters.telegram.send_dm`. Держим вместе с подменой
    `pyrogram.Client.invoke` выше: тот ловит уже совершённый вызов, а этот
    не даёт `send_dm` дойти до вызова вообще.
    """
    import adapters.telegram

    monkeypatch.setattr(adapters.telegram, "SEND_LOCKED", True)


@pytest.fixture(autouse=True)
def _secrets_forgotten(monkeypatch):
    """Запомненные секреты журнала не переходят в следующий тест.

    Набор общий на процесс: пароль, сохранённый одним тестом, вымарывался бы
    в журнале всех последующих, и тест образца зеленел бы без образца.
    """
    from backend import log_secrets

    monkeypatch.setattr(log_secrets, "_KNOWN_SECRETS", frozenset())


async def _clear_all_tables(engine: AsyncEngine) -> None:
    """Удаляет все строки из всех таблиц, кроме `alembic_version`.

    Список таблиц берётся из `sqlite_master`, а не из `Base.metadata`: схема
    поднята alembic'ом один раз до `head`, и если модели когда-нибудь
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


async def _empty_database(database_url) -> None:
    """Очистить базу своим движком: чужой к этому моменту может быть закрыт."""
    from adapters.db import make_engine

    cleaner = make_engine(database_url)
    try:
        await _clear_all_tables(cleaner)
    finally:
        await cleaner.dispose()


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

    await _empty_database(database_url)


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
