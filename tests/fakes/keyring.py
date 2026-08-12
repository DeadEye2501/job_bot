"""Хранилище ключей в памяти вместо системного.

Отвечает как настоящее хранилище, а не считает вызовы: тесты проверяют, что
зашифрованное читается обратно, а не что кто-то дёрнул `set_password`.
"""

import keyring.backend


class MemoryKeyring(keyring.backend.KeyringBackend):
    """Пары «служба + имя» в словаре. Живёт один прогон."""

    priority = 1

    def __init__(self) -> None:
        super().__init__()
        self.store: dict[tuple[str, str], str] = {}

    def get_password(self, service: str, username: str) -> str | None:
        return self.store.get((service, username))

    def set_password(self, service: str, username: str, password: str) -> None:
        self.store[(service, username)] = password

    def delete_password(self, service: str, username: str) -> None:
        self.store.pop((service, username), None)
