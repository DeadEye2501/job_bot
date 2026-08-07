"""Следствия записи настроек насквозь: в базу и в память сразу.

Проверяется и то, и другое: запись, не дошедшая до базы, переживёт только до
перезапуска, а запись, не дошедшая до памяти, не подействует до перезагрузки.
"""

from sqlalchemy import select

from backend.models import AppSetting, BotMode, BotState, LlmConfig, LlmConfigKind, TgAccount
from backend.runtime_settings import RuntimeSettings, decrypt_bytes, decrypt_str
from tests.factories import app_setting_row, bot_state_row, tg_account_row


async def only_row(session_factory, model):
    """Единственная строка таблицы, прочитанная заново из базы."""
    async with session_factory() as session:
        return (await session.scalars(select(model))).first()


async def test_new_telegram_credentials_reach_both_the_database_and_memory(session_factory):
    """Учётные данные Telegram записываются и сразу видны в памяти."""
    settings = await RuntimeSettings.load(session_factory)

    await settings.set_tg(
        api_id=1, api_hash="шифр", phone="+79991234567",
        password="пароль", session_string="сессия",
    )

    assert settings.tg.api_hash == "шифр"
    row = await only_row(session_factory, TgAccount)
    assert decrypt_str(row.api_hash_encrypted) == "шифр"
    assert decrypt_str(row.password_encrypted) == "пароль"
    assert decrypt_bytes(row.session_blob_encrypted) == "сессия".encode("utf-8")


async def test_the_secret_is_not_stored_in_the_clear(session_factory):
    """В базе шифротекст, а не исходная строка."""
    settings = await RuntimeSettings.load(session_factory)

    await settings.set_tg(api_id=1, api_hash="шифр", phone="+7")

    row = await only_row(session_factory, TgAccount)
    assert "шифр" not in row.api_hash_encrypted


async def test_an_empty_password_is_stored_as_absent(session_factory):
    """Пустой пароль не шифруется, а записывается отсутствием."""
    settings = await RuntimeSettings.load(session_factory)

    await settings.set_tg(api_id=1, api_hash="ш", phone="+7", password="")

    assert (await only_row(session_factory, TgAccount)).password_encrypted is None


async def test_an_absent_session_is_stored_as_absent(session_factory):
    """Отсутствие строки сессии записывается отсутствием: входа ещё не было."""
    settings = await RuntimeSettings.load(session_factory)

    await settings.set_tg(api_id=1, api_hash="ш", phone="+7")

    assert (await only_row(session_factory, TgAccount)).session_blob_encrypted is None


async def test_writing_credentials_twice_updates_the_same_row(session_factory):
    """Повторная запись обновляет ту же строку, а не заводит вторую."""
    settings = await RuntimeSettings.load(session_factory)

    await settings.set_tg(api_id=1, api_hash="первый", phone="+7")
    await settings.set_tg(api_id=2, api_hash="второй", phone="+8")

    async with session_factory() as session:
        rows = (await session.scalars(select(TgAccount))).all()
    assert len(rows) == 1
    assert decrypt_str(rows[0].api_hash_encrypted) == "второй"


async def test_clearing_credentials_empties_both_the_table_and_memory(session_factory):
    """Выход из учётной записи стирает и строку, и память."""
    settings = await RuntimeSettings.load(session_factory)
    await settings.set_tg(api_id=1, api_hash="ш", phone="+7")

    await settings.clear_tg()

    assert settings.tg is None
    assert await only_row(session_factory, TgAccount) is None


async def test_clearing_credentials_that_are_absent_is_harmless(session_factory):
    """Выход при отсутствующих данных ничего не ломает."""
    settings = await RuntimeSettings.load(session_factory)

    await settings.clear_tg()

    assert settings.tg is None


async def test_the_chat_provider_is_written_and_cached(session_factory):
    """Настройка провайдера чата доходит и до базы, и до памяти."""
    settings = await RuntimeSettings.load(session_factory)

    await settings.set_chat(base_url="http://a.test", api_key="sk-1", model="qwen")

    assert settings.chat.model == "qwen"
    row = await only_row(session_factory, LlmConfig)
    assert row.kind is LlmConfigKind.CHAT
    assert decrypt_str(row.api_key_encrypted) == "sk-1"


async def test_the_two_provider_kinds_do_not_overwrite_each_other(session_factory):
    """Запись одного рода провайдера не затирает другой."""
    settings = await RuntimeSettings.load(session_factory)

    await settings.set_chat(base_url="http://a.test", api_key="", model="чат")
    await settings.set_embed(base_url="http://b.test", api_key="", model="встраивания")

    assert settings.chat.model == "чат"
    assert settings.embed.model == "встраивания"
    async with session_factory() as session:
        assert len((await session.scalars(select(LlmConfig))).all()) == 2


async def test_a_provider_without_a_key_stores_no_ciphertext(session_factory):
    """Местный провайдер без ключа не получает шифротекста."""
    settings = await RuntimeSettings.load(session_factory)

    await settings.set_chat(base_url="http://a.test", api_key="", model="qwen")

    assert (await only_row(session_factory, LlmConfig)).api_key_encrypted is None


async def test_a_new_setting_is_created(session_factory):
    """Незнакомая настройка заводится строкой."""
    settings = await RuntimeSettings.load(session_factory)

    await settings.set_app("scoring_threshold", "42")

    assert settings.scoring_threshold == 42
    assert (await only_row(session_factory, AppSetting)).value == "42"


async def test_an_existing_setting_is_updated_in_place(session_factory):
    """Знакомая настройка обновляется, а не задваивается."""
    async with session_factory() as session:
        async with session.begin():
            session.add(app_setting_row("scoring_threshold", "10"))
    settings = await RuntimeSettings.load(session_factory)

    await settings.set_app("scoring_threshold", "42")

    async with session_factory() as session:
        rows = (await session.scalars(select(AppSetting))).all()
    assert [(r.key, r.value) for r in rows] == [("scoring_threshold", "42")]


async def test_completing_the_wizard_is_recorded(session_factory):
    """Завершение мастера первого запуска записывается настройкой."""
    settings = await RuntimeSettings.load(session_factory)

    await settings.mark_wizard_completed()

    assert settings.wizard_completed is True
    assert (await only_row(session_factory, AppSetting)).value == "true"


async def test_the_mode_is_created_when_the_row_is_missing(session_factory):
    """Первая смена режима заводит строку состояния."""
    settings = await RuntimeSettings.load(session_factory)

    await settings.set_mode(BotMode.FULL)

    assert await settings.get_mode() is BotMode.FULL
    assert (await only_row(session_factory, BotState)).mode is BotMode.FULL


async def test_changing_the_mode_updates_the_same_row(session_factory):
    """Повторная смена обновляет ту же строку: таблица односрочная."""
    async with session_factory() as session:
        async with session.begin():
            session.add(bot_state_row(BotMode.OFF))
    settings = await RuntimeSettings.load(session_factory)

    await settings.set_mode(BotMode.DM_ONLY)

    async with session_factory() as session:
        rows = (await session.scalars(select(BotState))).all()
    assert len(rows) == 1
    assert rows[0].mode is BotMode.DM_ONLY


async def test_credentials_written_earlier_survive_a_reload(session_factory):
    """Записанное перечитывается из базы тем же самым."""
    settings = await RuntimeSettings.load(session_factory)
    await settings.set_tg(api_id=7, api_hash="шифр", phone="+79991234567")

    await settings.reload()

    assert settings.tg.api_id == 7
    assert settings.tg.api_hash == "шифр"
