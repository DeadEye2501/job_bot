"""Сопроводительные письма профиля, которые окно правит на вкладке Letters."""

from __future__ import annotations

from backend.incoming import text_or_none
from backend.repository import cover_letters as letters_repo
from client.bridge.answer import BAD_PAYLOAD, bad_fields, reply


class Letters:
    """Письма как четыре текста профиля, без анкеты.

    Примесь к `Profile`; собирающий обязан держать `_hub`. Анкеты письма не
    ждут: их пишут и тогда, когда имени и почты в ней ещё нет.
    """

    def letters(self) -> dict:
        """Письма активного профиля — все четыре, ненаписанные пустыми."""

        async def run() -> dict:
            async with self._hub.session_factory() as session:
                row = await letters_repo.get_letters(session)
            return {
                "letters": {
                    name: None if row is None else getattr(row, name)
                    for name in letters_repo.LETTER_FIELDS
                }
            }

        return reply(self._hub.runner, run())

    def save_letters(self, payload: dict) -> dict:
        """Записать все четыре письма разом: окно шлёт их вместе."""
        try:
            letters = {
                name: text_or_none(payload.get(name)) for name in letters_repo.LETTER_FIELDS
            }
        except BAD_PAYLOAD as e:
            return bad_fields("save_letters", e)

        async def run() -> dict:
            async with self._hub.session_factory() as session:
                async with session.begin():
                    await letters_repo.save_letters(session, **letters)
            return {}

        return reply(self._hub.runner, run())
