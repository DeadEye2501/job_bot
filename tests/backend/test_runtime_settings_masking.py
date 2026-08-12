"""Следствия сокрытия секретов от журнала в `backend/runtime_settings.py`."""

import logging

import pytest

from backend.runtime_settings import (
    LlmProviderConfig,
    RuntimeSettings,
    TgAccountConfig,
    _mask_phone,
)


@pytest.mark.parametrize(
    "raw, expected",
    [
        (None, "***"),
        ("", "***"),
        ("12345", "***"),
        ("1234567", "***4567"),
        ("+79991234567", "***4567"),
    ],
)
def test_a_phone_shows_only_its_last_four_digits(raw, expected):
    """В журнал попадают только последние четыре цифры, короткое — целиком скрыто."""
    assert _mask_phone(raw) == expected


async def test_the_saved_phone_reaches_the_log_masked(session_factory, caplog):
    """Записанный номер попадает в журнал только хвостом, а не целиком.

    Сокрытие проверено у самого помощника, но помощника можно и не позвать:
    замени `_mask_phone(phone)` на `phone` в записи об обновлении учётных
    данных — и мобильный уедет в журнал открытым текстом, а весь набор
    останется зелёным.
    """
    settings = await RuntimeSettings.load(session_factory)

    with caplog.at_level(logging.INFO, logger="backend.runtime_settings"):
        await settings.set_tg(api_id=1, api_hash="шифр", phone="+79991234567")

    written = [
        record.getMessage()
        for record in caplog.records
        if record.name == "backend.runtime_settings"
    ]
    assert written, "запись об обновлении учётных данных не появилась вовсе"
    assert not any("+79991234567" in line for line in written)
    assert any("***4567" in line for line in written)


def test_tg_account_config_repr_hides_secrets_but_shows_the_rest():
    """repr() учётной записи Telegram не содержит секретов, но показывает остальное."""
    cfg = TgAccountConfig(
        api_id=1, api_hash="шифр", phone="+79991234567",
        password="пароль", session_string="сессия",
    )

    r = repr(cfg)

    assert "шифр" not in r
    assert "пароль" not in r
    assert "сессия" not in r
    assert "api_id=1" in r
    assert "+79991234567" in r


def test_llm_provider_config_repr_hides_the_key_but_shows_the_rest():
    """repr() настройки провайдера не содержит ключа, но показывает остальное."""
    cfg = LlmProviderConfig(base_url="http://a.test", api_key="sk-секрет", model="qwen")

    r = repr(cfg)

    assert "sk-секрет" not in r
    assert "http://a.test" in r
    assert "qwen" in r
