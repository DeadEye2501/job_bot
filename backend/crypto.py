"""Шифрование секретов мастер-ключом из связки ключей ОС.

Ключ — Fernet, лежит в Windows Credential Manager / macOS Keychain / Linux
SecretService и заводится сам при первом обращении. Через этот модуль
проходят TG api_hash и пароль двухфакторной, строка сессии pyrogram и ключи
доступа к моделям: в базе они лежат шифротекстом, наружу отдаются открытыми.
"""

import logging

import keyring
from cryptography.fernet import Fernet

logger = logging.getLogger(__name__)

_KEYRING_SERVICE = "JobBot"
_KEYRING_KEY = "master_key"

# Бэкенды keyring'а, которые мы отказываемся использовать. Все они
# хранят секреты на диске в виде, который не считается «system-grade»
# encryption: либо plaintext (шифрования нет), либо file-based KDF
# с ключом-вне-OS-сейфа, либо вообще no-op fail-stub. Headless /
# minimal Linux без SecretService — типичный кейс.
_REJECTED_KEYRING_BACKENDS = (
    "keyrings.alt.file.PlaintextKeyring",
    "keyrings.alt.file.EncryptedKeyring",      # passphrase-derived KDF, не OS-vault
    "keyrings.alt.file_base.Keyring",          # generic file-based base class
    "keyrings.alt.Windows.RegistryKeyring",    # plaintext в реестре Windows
    "keyring.backends.fail.Keyring",
)


def _check_keyring_backend() -> None:
    """Pre-flight: log активный keyring-бэкенд, raise если небезопасный.

    Идея — fail-fast на старте, до первой попытки сохранить TG/LLM creds.
    Иначе при PlaintextKeyring secrets уходят на диск открытым текстом,
    при fail.Keyring каждый encrypt'ает с новым ключом и старые ciphertexts
    становятся нечитаемыми.
    """
    try:
        backend = keyring.get_keyring()
    except Exception:
        logger.exception("keyring.get_keyring() failed — backend probe error")
        return
    backend_cls = f"{type(backend).__module__}.{type(backend).__name__}"
    if backend_cls in _REJECTED_KEYRING_BACKENDS:
        raise RuntimeError(
            f"Небезопасный keyring-бэкенд: {backend_cls}. Установите "
            "системный keyring (Windows Credential Manager / macOS "
            "Keychain / Linux SecretService) — иначе секреты приложения "
            "нельзя надёжно зашифровать."
        )
    logger.info("keyring backend: %s", backend_cls)


def _get_or_create_master_key() -> bytes:
    existing = keyring.get_password(_KEYRING_SERVICE, _KEYRING_KEY)
    if existing:
        return existing.encode("ascii")
    new_key = Fernet.generate_key()
    keyring.set_password(_KEYRING_SERVICE, _KEYRING_KEY, new_key.decode("ascii"))
    logger.info(
        "generated new master encryption key (stored in OS keyring as %s/%s)",
        _KEYRING_SERVICE, _KEYRING_KEY,
    )
    return new_key


def _cipher() -> Fernet:
    return Fernet(_get_or_create_master_key())


def encrypt_str(plaintext: str) -> str:
    """Encrypt a plain string; returns base64-safe ASCII ciphertext."""
    return _cipher().encrypt(plaintext.encode("utf-8")).decode("ascii")


def decrypt_str(ciphertext: str) -> str:
    return _cipher().decrypt(ciphertext.encode("ascii")).decode("utf-8")


def encrypt_bytes(plaintext: bytes) -> bytes:
    return _cipher().encrypt(plaintext)


def decrypt_bytes(ciphertext: bytes) -> bytes:
    return _cipher().decrypt(ciphertext)
