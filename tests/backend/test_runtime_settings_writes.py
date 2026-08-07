"""Следствия записи настроек: у одних методов их два, у других — одно.

У большинства set-методов запись идёт и в базу, и в кэш `RuntimeSettings`
разом: запись, не дошедшая до базы, не переживёт перезапуск, а не дошедшая
до кэша — не подействует до перезагрузки. Часть тестов проверяет оба
следствия, часть — только одно (второе уже закреплено соседним тестом, и
дублировать его смысла нет). У режима бота кэша в памяти нет вовсе:
`RuntimeSettings` не хранит режим полем, `get_mode` каждый раз читает базу
заново, — поэтому тесты режима проверяют только базу.
"""

from backend.models import AppSetting, BotMode, BotState, LlmConfig, LlmConfigKind, TgAccount
from backend.runtime_settings import RuntimeSettings, decrypt_bytes, decrypt_str
from tests.dbio import all_rows, only_row, put
from tests.factories import app_setting_row, bot_state_row


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
    """В базе шифротекст настоящего Fernet, а не исходная строка и не её кодировка.

    Префикс `gAAAAA` — версионный байт токена Fernet — закрепляет именно
    алгоритм: подделка вроде `base64.b64encode` тоже прошла бы проверку на
    отсутствие подстроки, потому что кириллица не входит в алфавит base64.
    """
    settings = await RuntimeSettings.load(session_factory)

    await settings.set_tg(api_id=1, api_hash="шифр", phone="+7")

    row = await only_row(session_factory, TgAccount)
    assert "шифр" not in row.api_hash_encrypted
    assert row.api_hash_encrypted.startswith("gAAAAA")


async def test_an_empty_password_is_stored_as_absent(session_factory):
    """Пустой пароль стирает прежний шифротекст, а не оставляет его в базе."""
    settings = await RuntimeSettings.load(session_factory)
    await settings.set_tg(api_id=1, api_hash="ш", phone="+7", password="старый")

    await settings.set_tg(api_id=1, api_hash="ш", phone="+7", password="")

    assert (await only_row(session_factory, TgAccount)).password_encrypted is None


async def test_an_absent_session_is_stored_as_absent(session_factory):
    """Выход без строки сессии стирает прежний шифротекст, а не оставляет его."""
    settings = await RuntimeSettings.load(session_factory)
    await settings.set_tg(api_id=1, api_hash="ш", phone="+7", session_string="старая")

    await settings.set_tg(api_id=1, api_hash="ш", phone="+7")

    assert (await only_row(session_factory, TgAccount)).session_blob_encrypted is None


async def test_writing_credentials_twice_updates_the_same_row(session_factory):
    """Повторная запись обновляет ту же строку, а не заводит вторую."""
    settings = await RuntimeSettings.load(session_factory)

    await settings.set_tg(api_id=1, api_hash="первый", phone="+7")
    await settings.set_tg(api_id=2, api_hash="второй", phone="+8")

    rows = await all_rows(session_factory, TgAccount)
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


async def test_writing_the_chat_provider_twice_updates_the_same_row(session_factory):
    """Смена провайдера обновляет ту же строку, а не заводит вторую."""
    settings = await RuntimeSettings.load(session_factory)

    await settings.set_chat(base_url="http://a.test", api_key="sk-1", model="qwen")
    await settings.set_chat(base_url="http://b.test", api_key="sk-2", model="llama")

    rows = await all_rows(session_factory, LlmConfig)
    assert len(rows) == 1
    assert rows[0].base_url == "http://b.test"
    assert decrypt_str(rows[0].api_key_encrypted) == "sk-2"
    assert rows[0].model == "llama"


async def test_the_two_provider_kinds_do_not_overwrite_each_other(session_factory):
    """Запись одного рода провайдера не затирает другой."""
    settings = await RuntimeSettings.load(session_factory)

    await settings.set_chat(base_url="http://a.test", api_key="", model="чат")
    await settings.set_embed(base_url="http://b.test", api_key="", model="встраивания")

    assert settings.chat.model == "чат"
    assert settings.embed.model == "встраивания"
    assert len(await all_rows(session_factory, LlmConfig)) == 2


async def test_a_provider_without_a_key_stores_no_ciphertext(session_factory):
    """Переход на местный провайдер стирает прежний шифротекст, а не оставляет его."""
    settings = await RuntimeSettings.load(session_factory)
    await settings.set_chat(base_url="http://a.test", api_key="sk-1", model="qwen")

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
    await put(session_factory, app_setting_row("scoring_threshold", "10"))
    settings = await RuntimeSettings.load(session_factory)

    await settings.set_app("scoring_threshold", "42")

    rows = await all_rows(session_factory, AppSetting)
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
    await put(session_factory, bot_state_row(BotMode.OFF))
    settings = await RuntimeSettings.load(session_factory)

    await settings.set_mode(BotMode.DM_ONLY)

    rows = await all_rows(session_factory, BotState)
    assert len(rows) == 1
    assert rows[0].mode is BotMode.DM_ONLY


async def test_credentials_written_earlier_survive_a_reload(session_factory):
    """Записанное перечитывается из базы тем же самым."""
    settings = await RuntimeSettings.load(session_factory)
    await settings.set_tg(api_id=7, api_hash="шифр", phone="+79991234567")

    await settings.reload()

    assert settings.tg.api_id == 7
    assert settings.tg.api_hash == "шифр"
