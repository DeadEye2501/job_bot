"""Экран «Агрегаторы»: перечень, заведение, удаление, включение, вход и обход."""

from __future__ import annotations

from backend.agent.availability import current_refusal
from backend.repository import aggregators as repo
from client.bridge.answer import BAD_PAYLOAD, Denied, asked_id, bad_fields, denied, launched, reply
from client.bridge.form_payloads import read_toggle
from client.bridge.hub import Hub
from client.bridge.refusals import (
    AGGREGATOR_REFUSALS,
    LOGIN_FIRST,
    LOGIN_REFUSALS,
    NO_AGGREGATOR,
    NO_BOT,
    NOT_A_SITE,
    WEB_SEARCH_KEPT,
)
from client.bridge.wire import _aggregator_row_to_dict


class Aggregators:
    """Источники-агрегаторы: всё, что окно о них знает и что с ними делает."""

    def __init__(self, hub: Hub) -> None:
        self._hub = hub

    def list(self) -> dict:
        """Все источники разом, «Поиск по сети» первым, и подсказка, если агент заперт."""

        async def run() -> dict:
            async with self._hub.session_factory() as session:
                rows = await repo.list_aggregators(session)
            return {"aggregators": [_aggregator_row_to_dict(r) for r in rows],
                    "lock": current_refusal(self._hub.rs.chat)}

        return reply(self._hub.runner, run())

    def create(self, payload: dict | None = None) -> dict:
        """Завести агрегатор по адресу, набранному как угодно; уже заведённый — не отказ."""
        payload = payload if isinstance(payload, dict) else {}
        address = str(payload.get("address") or "")

        async def run() -> dict:
            async with self._hub.session_factory() as session:
                async with session.begin():
                    row, status = await repo.create_aggregator(session, address)
                    if status == "invalid":
                        raise Denied(NOT_A_SITE)
                    return {"aggregator": _aggregator_row_to_dict(row), "status": status}

        return reply(self._hub.runner, run())

    def delete(self, payload: dict | None = None) -> dict:
        """Удалить агрегатор. С откликами — сперва спросить: ответ называет их число."""
        payload = payload if isinstance(payload, dict) else {}
        aggregator_id, refusal = asked_id(payload, "aggregator_id", "aggregators.delete")
        if refusal is not None:
            return refusal
        confirmed = payload.get("confirmed") is True
        bot = self._hub.bot

        async def run() -> dict:
            async with self._hub.session_factory() as session:
                _refuse_deletion(await repo.deletion_block(session, aggregator_id))
                applications = await repo.applications_of(session, aggregator_id)
            if applications and not confirmed:
                return {"confirm": applications}
            if bot is None:
                raise Denied(NO_BOT)
            outcome = await bot.delete_aggregator(aggregator_id)
            _refuse_deletion(None if outcome == "ok" else outcome)
            return {"deleted": True}

        return reply(self._hub.runner, run())

    def set_active(self, payload: dict | None = None) -> dict:
        """Включить или выключить агрегатор; без входа включить нельзя."""
        payload = payload if isinstance(payload, dict) else {}
        try:
            aggregator_id, active = read_toggle(payload, "aggregator_id", "is_active")
            if aggregator_id is None or active is None:
                raise ValueError("нужны aggregator_id и is_active")
        except BAD_PAYLOAD as e:
            return bad_fields("aggregators.set_active", e)

        async def run() -> dict:
            async with self._hub.session_factory() as session:
                async with session.begin():
                    outcome = await repo.set_aggregator_active(session, aggregator_id, active)
            if outcome == "missing":
                raise Denied(NO_AGGREGATOR)
            if outcome == "not_logged_in":
                raise Denied(LOGIN_FIRST)
            return {"aggregator_id": aggregator_id, "is_active": active}

        return reply(self._hub.runner, run())

    def login(self, aggregator_id: int) -> dict:
        """Вход на сайт: видимый браузер, человек входит и закрывает окно, агент проверяет."""
        return self._launch(aggregator_id, "login", "Вход проверен.", LOGIN_REFUSALS)

    def run_now(self, aggregator_id: int) -> dict:
        """Обойти один источник вне очереди."""
        return self._launch(aggregator_id, "run_now", "Обход источника закончен.", AGGREGATOR_REFUSALS)

    def _launch(self, aggregator_id: int, action: str, done: str, refusals: dict) -> dict:
        bot = self._hub.bot
        if bot is None:
            return denied(NO_BOT, aggregator_id=aggregator_id, action=action)
        work = bot.login_aggregator if action == "login" else bot.run_aggregator_now
        return launched(
            self._hub,
            lambda: work(aggregator_id),
            {**refusals, "locked": current_refusal(self._hub.rs.chat) or ""},
            done,
            aggregator_id=aggregator_id,
            action=action,
        )


_DELETION_REFUSALS = {
    "missing": NO_AGGREGATOR,
    "protected": WEB_SEARCH_KEPT,
    "busy": AGGREGATOR_REFUSALS["busy"],
}


def _refuse_deletion(block: str | None) -> None:
    """Исход, мешающий удалению, — словами окну; правило решает репозиторий и бот."""
    if block is not None:
        raise Denied(_DELETION_REFUSALS.get(block, AGGREGATOR_REFUSALS["error"]))
