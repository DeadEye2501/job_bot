"""Следствия чтения настроек из базы в память.

Строки кладёт сам тест, затем `RuntimeSettings.load` их читает. Закрытые
`_from_tg_row` и `_from_llm_row` видны только тем, что оказалось в кэше.
"""

from backend.crypto import encrypt_bytes, encrypt_str
from backend.models import BotMode, LlmConfigKind
from backend.runtime_settings import RuntimeSettings
from tests.dbio import put
from tests.factories import (
    app_setting_row,
    bot_state_row,
    llm_config_row,
    tg_account_row,
)


async def test_an_empty_database_yields_no_credentials(session_factory):
    """На пустой базе учётных данных нет, и это не ошибка."""
    settings = await RuntimeSettings.load(session_factory)

    assert settings.tg is None
    assert settings.chat is None
    assert settings.embed is None


async def test_telegram_credentials_come_back_decrypted(session_factory):
    """Учётные данные Telegram читаются расшифрованными."""
    await put(session_factory, tg_account_row(
        api_hash_encrypted=encrypt_str("шифр"),
        phone="+79991234567",
        password_encrypted=encrypt_str("пароль"),
        session_blob_encrypted=encrypt_bytes("сессия".encode("utf-8")),
    ))

    settings = await RuntimeSettings.load(session_factory)

    assert settings.tg.api_hash == "шифр"
    assert settings.tg.phone == "+79991234567"
    assert settings.tg.password == "пароль"
    assert settings.tg.session_string == "сессия"


async def test_a_missing_password_reads_as_an_empty_one(session_factory):
    """Отсутствие пароля читается пустой строкой, а не отсутствием."""
    await put(session_factory, tg_account_row(api_hash_encrypted=encrypt_str("ш")))

    settings = await RuntimeSettings.load(session_factory)

    assert settings.tg.password == ""


async def test_a_missing_session_reads_as_absent(session_factory):
    """Отсутствие строки сессии читается именно отсутствием: входа ещё не было."""
    await put(session_factory, tg_account_row(api_hash_encrypted=encrypt_str("ш")))

    settings = await RuntimeSettings.load(session_factory)

    assert settings.tg.session_string is None


async def test_an_account_without_an_identifier_is_not_credentials(session_factory):
    """Строка без идентификатора приложения учётными данными не считается."""
    await put(session_factory, tg_account_row(
        api_id=None, api_hash_encrypted=encrypt_str("ш")
    ))

    assert (await RuntimeSettings.load(session_factory)).tg is None


async def test_an_account_without_a_secret_is_not_credentials(session_factory):
    """Строка без шифротекста учётными данными не считается."""
    await put(session_factory, tg_account_row(api_hash_encrypted=None))

    assert (await RuntimeSettings.load(session_factory)).tg is None


async def test_an_account_without_a_phone_is_not_credentials(session_factory):
    """Строка без телефона учётными данными не считается."""
    await put(session_factory, tg_account_row(
        api_hash_encrypted=encrypt_str("ш"), phone=None
    ))

    assert (await RuntimeSettings.load(session_factory)).tg is None


async def test_the_two_provider_kinds_are_read_separately(session_factory):
    """Настройки чата и встраиваний не путаются между собой."""
    await put(
        session_factory,
        llm_config_row(LlmConfigKind.CHAT, model="чат"),
        llm_config_row(LlmConfigKind.EMBED, model="встраивания"),
    )

    settings = await RuntimeSettings.load(session_factory)

    assert settings.chat.model == "чат"
    assert settings.embed.model == "встраивания"


async def test_a_provider_key_comes_back_decrypted(session_factory):
    """Ключ провайдера читается расшифрованным."""
    await put(session_factory, llm_config_row(
        LlmConfigKind.CHAT, api_key_encrypted=encrypt_str("sk-123")
    ))

    assert (await RuntimeSettings.load(session_factory)).chat.api_key == "sk-123"


async def test_a_provider_without_a_key_reads_as_an_empty_one(session_factory):
    """Местный провайдер без ключа читается пустым ключом, а не отсутствием."""
    await put(session_factory, llm_config_row(LlmConfigKind.CHAT))

    assert (await RuntimeSettings.load(session_factory)).chat.api_key == ""


async def test_a_provider_without_an_address_is_not_a_provider(session_factory):
    """Настройка без адреса провайдером не считается."""
    await put(session_factory, llm_config_row(LlmConfigKind.CHAT, base_url=None))

    assert (await RuntimeSettings.load(session_factory)).chat is None


async def test_a_provider_without_a_model_is_not_a_provider(session_factory):
    """Настройка без модели провайдером не считается."""
    await put(session_factory, llm_config_row(LlmConfigKind.CHAT, model=None))

    assert (await RuntimeSettings.load(session_factory)).chat is None


async def test_settings_from_the_key_value_table_reach_the_cache(session_factory):
    """Значения из общего словаря доезжают до типизированных свойств."""
    await put(session_factory, app_setting_row("scoring_threshold", "42"))

    assert (await RuntimeSettings.load(session_factory)).scoring_threshold == 42


async def test_a_null_value_reads_as_absent_and_the_default_applies(session_factory):
    """Пустое значение в базе — это «не задано», и работает умолчание."""
    await put(session_factory, app_setting_row("scoring_threshold", None))

    assert (await RuntimeSettings.load(session_factory)).scoring_threshold == 5


async def test_a_reload_picks_up_a_change_made_afterwards(session_factory):
    """Повторное чтение подхватывает то, что записали после первого."""
    settings = await RuntimeSettings.load(session_factory)
    await put(session_factory, app_setting_row("scoring_threshold", "42"))

    assert settings.scoring_threshold == 5
    await settings.reload()
    assert settings.scoring_threshold == 42


async def test_the_mode_defaults_to_off_when_the_row_is_missing(session_factory):
    """Без строки состояния бот считается выключенным."""
    settings = await RuntimeSettings.load(session_factory)

    assert await settings.get_mode() is BotMode.OFF


async def test_the_stored_mode_is_read_back(session_factory):
    """Записанный режим читается обратно."""
    await put(session_factory, bot_state_row(BotMode.FULL))
    settings = await RuntimeSettings.load(session_factory)

    assert await settings.get_mode() is BotMode.FULL
