"""Вход в Telegram, каким его видит окно: три шага и отказ от попытки.

Настоящий `TelegramLogin` на первом же шаге поднимает клиента Pyrogram и идёт
в сеть за кодом. Мост внутрь него не заходит: он зовёт три шага, спрашивает,
чего от человека ждут сейчас, и пересказывает окну исход — а исход у всех
шагов один и тот же тип, `LoginStep`.
"""

from backend.telegram_login import LoginStep


class UiLogin:
    """Отвечает заготовленным шагом и помнит, о чём просили.

    Чего ждут от человека сейчас — мост спрашивает у самого входа, поэтому
    оба признака здесь настоящие поля, а не ответы: тест ставит их так же,
    как их поставила бы предыдущая удачная попытка.
    """

    def __init__(
        self,
        step: LoginStep,
        *,
        awaiting_code: bool = False,
        awaiting_password: bool = False,
    ) -> None:
        self.step = step
        self.awaiting_code = awaiting_code
        self.awaiting_password = awaiting_password
        self.active = True
        self.calls: list[tuple] = []

    async def send_code(self, api_id: int, api_hash: str, phone: str) -> LoginStep:
        self.calls.append(("send_code", api_id, api_hash, phone))
        return self.step

    async def confirm_code(self, code: str) -> LoginStep:
        self.calls.append(("confirm_code", code))
        return self.step

    async def confirm_password(self, password: str) -> LoginStep:
        self.calls.append(("confirm_password", password))
        return self.step

    async def forget(self) -> None:
        self.calls.append(("forget",))
        self.active = False
