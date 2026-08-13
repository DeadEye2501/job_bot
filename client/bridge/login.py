"""Вход в Telegram: три шага, общие основному окну и мастеру."""

from __future__ import annotations

import json

from PySide6.QtCore import Signal, Slot

from client.bridge.answer import _err, _ok
from client.bridge.payload import _log_invalid_payload


async def _login_json(step_coro) -> str:
    """Дождаться шага входа в Telegram и перевести его исход в ответ окну."""
    step = await step_coro
    return _err(step.error) if step.error is not None else _ok(step.payload)


class TelegramLoginSlots:
    """Три шага входа, подмешиваемые обеим поверхностям окна.

    QWebChannel регистрирует один объект «api»: после первого запуска на
    канале сидит основное окно, и методы мастера ему недоступны. Сам вход у
    обоих один и тот же — поэтому объявлен один раз и подмешивается, а не
    переписывается дважды.

    Подмешивающий обязан держать `_dispatch` и `_login`. Сам `_login` у двоих
    разный, и разница за пределами входа: у мастера это чистый `TelegramLogin`,
    у основного окна — `TelegramLogin` с `on_saved`, который после удачного
    входа запоминает ник и поднимает бота. Шаги входа об этом не знают.
    """

    telegram_send_code_done = Signal(str)
    telegram_confirm_code_done = Signal(str)
    telegram_confirm_password_done = Signal(str)

    @Slot(str)
    def telegram_send_code(self, payload_json: str) -> None:
        try:
            payload = json.loads(payload_json)
            api_id = int(payload["api_id"])
            api_hash = str(payload["api_hash"]).strip()
            phone = str(payload["phone"]).strip()
        except (KeyError, ValueError, TypeError) as e:
            _log_invalid_payload("telegram_send_code", e)
            self.telegram_send_code_done.emit(_err(f"Неверные поля: {e}"))
            return
        self._dispatch(
            self.telegram_send_code_done,
            _login_json(self._login.send_code(api_id, api_hash, phone)),
        )

    @Slot(str)
    def telegram_confirm_code(self, payload_json: str) -> None:
        try:
            code = str(json.loads(payload_json)["code"]).strip()
        except (KeyError, ValueError, TypeError) as e:
            _log_invalid_payload("telegram_confirm_code", e)
            self.telegram_confirm_code_done.emit(_err(f"Неверные поля: {e}"))
            return
        if not self._login.awaiting_code:
            self.telegram_confirm_code_done.emit(
                _err("Сначала запросите код подтверждения.")
            )
            return
        self._dispatch(
            self.telegram_confirm_code_done,
            _login_json(self._login.confirm_code(code)),
        )

    @Slot(str)
    def telegram_confirm_password(self, payload_json: str) -> None:
        try:
            password = str(json.loads(payload_json)["password"])
        except (KeyError, ValueError, TypeError) as e:
            _log_invalid_payload("telegram_confirm_password", e)
            self.telegram_confirm_password_done.emit(_err(f"Неверные поля: {e}"))
            return
        if not self._login.awaiting_password:
            self.telegram_confirm_password_done.emit(
                _err("Сначала пройдите шаг с кодом подтверждения.")
            )
            return
        self._dispatch(
            self.telegram_confirm_password_done,
            _login_json(self._login.confirm_password(password)),
        )
