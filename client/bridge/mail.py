"""Почта для откликов в настройках: что записано и запись новой."""

from __future__ import annotations

from backend.incoming import int_or_none, text_or_none
from backend.repository.mail_account import MailSettings, read_mail_account, save_mail_account
from client.bridge.answer import reply


class Mail:
    """Почта для откликов письмом. Пароль окну не отдаётся — только признак, что он есть.

    Собирающий обязан держать `_hub`: из него берутся мотор и сессии.
    """

    def mail(self) -> dict:
        """Что записано о почте: адрес, сервер, порт и есть ли пароль."""

        async def run() -> dict:
            async with self._hub.session_factory() as session:
                row = await read_mail_account(session)
            return {
                "address": row.address if row else None,
                "smtp_host": row.smtp_host if row else None,
                "smtp_port": row.smtp_port if row else None,
                "has_password": bool(row and row.password_encrypted),
            }

        return reply(self._hub.runner, run())

    def save_mail(self, payload: dict | None = None) -> dict:
        """Записать почту. Пустой пароль — оставить прежний; у Gmail сервер подставляется сам."""
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
