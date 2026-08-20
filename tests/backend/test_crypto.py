"""Следствия шифрования секретов в `backend/crypto.py`.

Хранилище ключей подменено стендом на подставное, но сам Fernet настоящий:
шифрование и расшифровка идут по-честному, подменён только источник ключа.
"""

import keyring
import pytest

from backend.crypto import (
    _check_keyring_backend,
    decrypt_bytes,
    forget_master_key,
    decrypt_str,
    encrypt_bytes,
    encrypt_str,
)


def test_an_encrypted_string_comes_back_unchanged():
    """Строка переживает шифрование и расшифровку без потерь."""
    assert decrypt_str(encrypt_str("секрет")) == "секрет"


def test_ciphertext_does_not_contain_the_plaintext():
    """В шифротексте исходной строки не видно, и это работа настоящего Fernet.

    Отсутствие подстроки само по себе доказывает мало: кириллица не входит
    в алфавит base64, так что и `base64.b64encode` дал бы тот же результат.
    Префикс `gAAAAA` — версионный байт токена Fernet — закрепляет именно
    алгоритм шифрования, а не подмену вроде голого кодирования.
    """
    ciphertext = encrypt_str("секрет")

    assert "секрет" not in ciphertext
    assert ciphertext.startswith("gAAAAA")


def test_encrypting_twice_gives_different_ciphertexts():
    """Два шифрования одного и того же дают разное — соль не повторяется."""
    assert encrypt_str("секрет") != encrypt_str("секрет")


def test_both_ciphertexts_decrypt_to_the_same_string():
    """При этом расшифровываются оба в одно и то же."""
    first, second = encrypt_str("секрет"), encrypt_str("секрет")

    assert decrypt_str(first) == decrypt_str(second) == "секрет"


def test_encrypted_bytes_come_back_unchanged():
    """Двоичные данные переживают тот же путь, и шифрует их тот же Fernet.

    Одного тождества мало: пропускалка, отдающая своё же на вход, прошла бы
    его. Префикс `gAAAAA` закрепляет алгоритм — как и у строкового двойника.
    """
    ciphertext = encrypt_bytes(b"\x00\xff\x10")

    assert decrypt_bytes(ciphertext) == b"\x00\xff\x10"
    assert ciphertext.startswith(b"gAAAAA")


def test_an_empty_string_survives_encryption():
    """Пустая строка шифруется и расшифровывается наравне с непустой."""
    assert decrypt_str(encrypt_str("")) == ""


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


def test_forgetting_the_key_empties_the_store(memory_keyring):
    """Забытый главный ключ из хранилища ОС исчезает, а не перезаписывается.

    Им зашифрована строка сеанса Telegram, и оставшийся после сноса он
    был бы секретом от данных, которых уже нет. Сама связка со сносом стережётся
    не здесь, а там, где снос живёт (`tests/client/test_bridge_wipe.py`): здесь
    зовут только само забывание.
    """
    encrypt_str("строка сеанса")
    assert memory_keyring.store != {}

    forget_master_key()

    assert memory_keyring.store == {}


def test_forgetting_a_key_that_is_not_there_is_not_a_trouble():
    """Забыть несуществующий ключ — не беда, а то же самое состояние.

    Снос данных зовут и на чистой установке, и второй раз подряд.
    """
    forget_master_key()
