"""Почта для откликов в настройках: что записано и запись новой."""

from __future__ import annotations

from backend.domain.mail_servers import known_server
from backend.incoming import int_or_none, text_or_none
from backend.repository.mail_account import MailSettings, read_mail_account, save_mail_account
from client.bridge.answer import reply


class Mail:
    """Почта для откликов письмом. Пароль окну отдаётся открытым, как ключи моделей.

    Собирающий обязан держать `_hub`: из него берутся мотор и сессии.
    """

    def mail(self) -> dict:
        """Что записано о почте: адрес, пароль, сервер, порт и подставлен ли сервер по
        адресу — окно держит поля сервера, пока он не подставлен."""

        async def run() -> dict:
            async with self._hub.session_factory() as session:
                saved = await read_mail_account(session)
            return {
                "address": saved.address or None if saved else None,
                "password": saved.password if saved else "",
                "smtp_host": saved.host if saved else None,
                "smtp_port": saved.port if saved else None,
                "server_by_address": known_server(saved.address if saved else None) is not None,
            }

        return reply(self._hub.runner, run())

    def save_mail(self, payload: dict | None = None) -> dict:
        """Записать почту. Пустой пароль — оставить прежний; у популярной почты сервер подставляется сам."""
        payload = payload if isinstance(payload, dict) else {}
        settings = MailSettings(
            address=text_or_none(payload.get("address")) or "",
            password=text_or_none(payload.get("password")),
            host=text_or_none(payload.get("smtp_host")),
            port=int_or_none(payload.get("smtp_port")),
        )

        async def run() -> dict:
            async with self._hub.session_factory() as session:
                async with session.begin():
                    await save_mail_account(session, settings)
            return {"saved": True}

        return reply(self._hub.runner, run())
