"""Хранилище ключей в памяти вместо системного.

Отвечает как настоящее хранилище, а не считает вызовы: тесты проверяют, что
зашифрованное читается обратно, а не что кто-то дёрнул `set_password`.
"""

import keyring.backend
import keyring.errors


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
        # Отсутствующую запись настоящее хранилище встречает броском, и
        # боевой код на это ветвится. Прости подделка молчанием — ветка
        # осталась бы непроверенной, а «забыли то, чего нет» выглядело бы
        # как удавшееся забывание.
        if self.store.pop((service, username), None) is None:
            raise keyring.errors.PasswordDeleteError(username)
