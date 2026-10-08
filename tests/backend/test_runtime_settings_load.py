"""Следствия чтения настроек из базы в память.

Строки кладёт сам тест, затем `RuntimeSettings.load` их читает. Закрытые
`_from_tg_row` и `_from_llm_row` видны только тем, что оказалось в кэше.
"""

import pytest
from cryptography.fernet import Fernet

from backend.crypto import encrypt_bytes, encrypt_str
from backend.models import LlmConfigKind
from backend.runtime_settings import RuntimeSettings
from tests.dbio import put
from tests.factories import (
    app_setting_row,
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


async def test_a_secret_no_key_can_open_is_not_credentials(session_factory):
    """Нечитаемый секрет читается как «не настроено», а не роняет чтение.

    Мастер-ключ живёт в связке ключей ОС, а шифротекст — в базе, и разъехаться
    они могут: связку чистят, профиль переносят на другую машину, базу
    восстанавливают из копии. Брошенный отсюда отказ расшифровки не ловит никто
    во всём дереве — приложение падает раньше, чем появится окно, и человек не
    может даже войти заново.
    """
    from_another_keyring = Fernet(Fernet.generate_key()).encrypt(b"hash").decode("ascii")
    await put(session_factory, tg_account_row(
        api_hash_encrypted=from_another_keyring
    ))

    assert (await RuntimeSettings.load(session_factory)).tg is None


async def test_a_broken_key_in_the_os_keyring_is_not_credentials(
    session_factory, monkeypatch
):
    """Испорченный ключ в связке тоже читается как «не настроено».

    Разъехаться связка и база могут не только чистой заменой ключа: запись в
    связке бывает обрезанной или испорченной, и тогда `Fernet` роняет не отказ
    расшифровки, а `ValueError` — совсем другую беду с тем же следствием.
    Ловить надо обе, иначе приложение падает до появления окна, и войти заново
    человек не может.
    """
    await put(session_factory, tg_account_row(api_hash_encrypted=encrypt_str("ш")))
    monkeypatch.setattr(
        "backend.crypto._get_or_create_master_key", lambda: b"cut-short-key"
    )

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


async def test_a_model_file_without_an_address_is_a_provider(session_factory):
    """Эмбеддинги из файла: адреса нет, в модели путь к `.gguf`.

    Не поднимись такая строка, `rs.embed` вышел бы пустым, и бот не стартовал
    бы вовсе, хотя окно показывает выбранный файл.
    """
    path = r"d:\models\model.gguf"
    await put(session_factory, llm_config_row(LlmConfigKind.EMBED, base_url=None, model=path))

    embed = (await RuntimeSettings.load(session_factory)).embed

    assert (embed.base_url, embed.model) == ("", path)


@pytest.mark.parametrize("address", ["https://api.anthropic.com", "claude-code"])
async def test_claude_is_not_an_embeddings_provider(session_factory, address):
    """Claude векторов не считает: строка эмбеддингов с его адресом — не поставщик.

    Поднимись она, каждый пост падал бы как беда одного текста, и обход канала
    уезжал бы мимо постов, не посчитав ни одного.
    """
    await put(session_factory, llm_config_row(LlmConfigKind.EMBED, base_url=address, model="sonnet"))

    assert (await RuntimeSettings.load(session_factory)).embed is None


async def test_a_model_file_is_not_a_chat_provider(session_factory):
    """Чат из файла не говорит: такая строка чата — не поставщик.

    Поднимись она, бот собрал бы клиента файла на месте чата и падал бы на
    каждом разговоре.
    """
    path = r"d:\models\model.gguf"
    await put(session_factory, llm_config_row(LlmConfigKind.CHAT, base_url=None, model=path))

    assert (await RuntimeSettings.load(session_factory)).chat is None


async def test_a_provider_without_a_model_is_not_a_provider(session_factory):
    """Настройка без модели провайдером не считается."""
    await put(session_factory, llm_config_row(LlmConfigKind.CHAT, model=None))

    assert (await RuntimeSettings.load(session_factory)).chat is None


async def test_a_provider_key_no_master_key_can_open_is_not_a_provider(session_factory):
    """Нечитаемый ключ провайдера тоже читается как «не настроено».

    Беда общая с учётной записью Telegram: связка ключей ОС и база разъехались.
    Падение здесь так же не даёт человеку дойти до окна и вписать ключ заново.
    """
    from_another_keyring = Fernet(Fernet.generate_key()).encrypt(b"sk-1").decode("ascii")
    await put(session_factory, llm_config_row(
        LlmConfigKind.CHAT, api_key_encrypted=from_another_keyring
    ))

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
