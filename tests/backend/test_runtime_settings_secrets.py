"""Следствия шифрования и маскирования в `backend/runtime_settings.py`.

Хранилище ключей подменено стендом на подставное, но сам Fernet настоящий:
шифрование и расшифровка идут по-честному, подменён только источник ключа.
"""

import keyring
import pytest

from backend.runtime_settings import (
    _check_keyring_backend,
    _mask_phone,
    decrypt_bytes,
    decrypt_str,
    encrypt_bytes,
    encrypt_str,
)


def test_an_encrypted_string_comes_back_unchanged():
    """Строка переживает шифрование и расшифровку без потерь."""
    assert decrypt_str(encrypt_str("секрет")) == "секрет"


def test_ciphertext_does_not_contain_the_plaintext():
    """В шифротексте исходной строки не видно."""
    assert "секрет" not in encrypt_str("секрет")


def test_encrypting_twice_gives_different_ciphertexts():
    """Два шифрования одного и того же дают разное — соль не повторяется."""
    assert encrypt_str("секрет") != encrypt_str("секрет")


def test_both_ciphertexts_decrypt_to_the_same_string():
    """При этом расшифровываются оба в одно и то же."""
    first, second = encrypt_str("секрет"), encrypt_str("секрет")

    assert decrypt_str(first) == decrypt_str(second) == "секрет"


def test_encrypted_bytes_come_back_unchanged():
    """Двоичные данные переживают тот же путь."""
    assert decrypt_bytes(encrypt_bytes(b"\x00\xff\x10")) == b"\x00\xff\x10"


def test_an_empty_string_survives_encryption():
    """Пустая строка шифруется и расшифровывается наравне с непустой."""
    assert decrypt_str(encrypt_str("")) == ""


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


def test_a_sound_key_store_passes_the_preflight():
    """Подставное хранилище стенда проверку проходит: оно не в списке отвергаемых."""
    _check_keyring_backend()


def test_an_unsafe_key_store_is_refused_by_name(monkeypatch):
    """Небезопасное хранилище отвергается, и отказ называет его."""

    class PlaintextKeyring:
        pass

    PlaintextKeyring.__module__ = "keyrings.alt.file"
    monkeypatch.setattr(keyring, "get_keyring", lambda: PlaintextKeyring())

    with pytest.raises(RuntimeError, match="PlaintextKeyring"):
        _check_keyring_backend()


def test_a_key_store_that_cannot_be_probed_does_not_stop_startup(monkeypatch):
    """Если опрос хранилища упал, запуск продолжается — отказ не выносится."""

    def explode():
        raise OSError("хранилище недоступно")

    monkeypatch.setattr(keyring, "get_keyring", explode)

    _check_keyring_backend()
