"""Экран «Агрегаторы»: перечень, заведение, удаление, включение, вход и обход."""

from __future__ import annotations

from backend.agent.availability import current_refusal
from backend.flows.aggregator_name import create_named_aggregator
from backend.repository import aggregators as repo
from backend.repository.aggregator_resumes import choose_resume, resumes_of
from client.bridge.answer import (
    BAD_PAYLOAD,
    Denied,
    asked_id,
    bad_fields,
    launched_on_bot,
    read_toggle,
    reply,
)
from client.bridge.hub import Hub
from client.bridge.mark import AGGREGATOR_MARK, marked, unmarked
from client.bridge.page import read_search
from client.bridge.refusals import (
    AGGREGATOR_REFUSALS,
    BLACKLISTED_STAYS_OFF,
    LOGIN_FIRST,
    LOGIN_REFUSALS,
    NO_AGGREGATOR,
    NO_BOT,
    WEB_SEARCH_KEPT,
    agent_refusals,
)
from client.bridge.source_page import AGGREGATOR, source_vacancies
from client.bridge.source_switch import switch_all
from client.bridge.wire import (
    _aggregator_list_row_to_dict,
    _aggregator_row_to_dict,
    _source_stats_to_dict,
)


class Aggregators:
    """Источники-агрегаторы: всё, что окно о них знает и что с ними делает."""

    def __init__(self, hub: Hub) -> None:
        self._hub = hub

    def list(self, payload: dict | None = None) -> dict:
        """Источники со счётом вакансий и отметкой отсева, «Поиск по сети» первым,
        общий выключатель и подсказка, если агент заперт.

        Строка поиска едет обратно, как у каналов: по ней окно рисует поле.
        """
        search = read_search(payload)

        async def run() -> dict:
            async with self._hub.session_factory() as session:
                rows = await repo.list_aggregators_with_counts(session, search)
            return {"search": search or "",
                    "enabled": self._hub.rs.aggregators_enabled,
                    "aggregators": [_aggregator_list_row_to_dict(*one) for one in rows],
                    "lock": current_refusal(self._hub.rs.chat)}

        return reply(self._hub.runner, run())

    def detail(self, aggregator_id: int) -> dict:
        """Карточка агрегатора с числами его вакансий и резюме человека на сайте в
        порядке сайта; номер едет и в отказе, как у канала."""

        async def run() -> dict:
            async with self._hub.session_factory() as session:
                found = await repo.get_aggregator_detail(session, aggregator_id)
                resumes = await resumes_of(session, aggregator_id)
            if found is None:
                raise Denied(NO_AGGREGATOR, aggregator_id=aggregator_id)
            row, stats, blacklist_value = found
            card = _aggregator_row_to_dict(row)
            return {"aggregator_id": card.pop("id"), **card,
                    "stats": _source_stats_to_dict(stats),
                    "blacklist_value": blacklist_value,
                    "resumes": [_resume_to_dict(one) for one in resumes],
                    "can_add_resume": bool(row.can_add_resume)}

        return reply(self._hub.runner, run())

    def vacancies(self, payload: dict) -> dict:
        """Страница вакансий этого агрегатора — для его карточки; см. `source_page`."""
        return source_vacancies(self._hub, AGGREGATOR, payload)

    def set_all_active(self, payload: dict) -> dict:
        """Общий выключатель агрегаторов; строки не трогает — см. `source_switch`."""
        return switch_all(self._hub, "aggregators_enabled", "aggregators.set_all_active", payload)

    def block(self, aggregator_id: int) -> dict:
        """Занести агрегатор в чёрный список по его хосту; агрегатор гаснет сразу.

        Повторное нажатие второй записи не заводит: погашенная оживает. У
        «Поиска по сети» хоста нет — отказ.
        """
        return reply(self._hub.runner, marked(self._hub, AGGREGATOR_MARK, aggregator_id))

    def unblock(self, aggregator_id: int) -> dict:
        """Убрать агрегатор из чёрного списка: запись гасится, а не сносится."""
        return reply(self._hub.runner, unmarked(self._hub, AGGREGATOR_MARK, aggregator_id))

    def create(self, payload: dict | None = None) -> dict:
        """Завести агрегатор по адресу, набранному как угодно; уже заведённый — не отказ.

        Имя сервиса ищется тем же зовом — окно держит «Добавляю…», пока оно
        ищется, — см. `aggregator_name`.
        """
        payload = payload if isinstance(payload, dict) else {}
        address = str(payload.get("address") or "")

        async def run() -> dict:
            row, status = await create_named_aggregator(
                self._hub.session_factory, address, self._hub.rs.chat
            )
            if status == "invalid":
                raise Denied(repo.NOT_A_SITE)
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
        """Включить или выключить агрегатор; без входа и в отсеве включить нельзя."""
        payload = payload if isinstance(payload, dict) else {}
        aggregator_id, active, refusal = read_toggle(
            payload, "aggregator_id", "is_active", "aggregators.set_active"
        )
        if refusal is not None:
            return refusal

        async def run() -> dict:
            async with self._hub.session_factory() as session:
                async with session.begin():
                    outcome = await repo.set_aggregator_active(session, aggregator_id, active)
            if outcome == "missing":
                raise Denied(NO_AGGREGATOR)
            if outcome == "not_logged_in":
                raise Denied(LOGIN_FIRST)
            if outcome == "blacklisted":
                raise Denied(BLACKLISTED_STAYS_OFF)
            return {"aggregator_id": aggregator_id, "is_active": active}

        return reply(self._hub.runner, run())

    def choose_resume(self, payload: dict | None = None) -> dict:
        """Отметить резюме, которым откликаться на этом сайте; прежняя отметка снимается."""
        payload = payload if isinstance(payload, dict) else {}
        try:
            aggregator_id = int(payload["aggregator_id"])
            resume_id = int(payload["resume_id"])
        except BAD_PAYLOAD as e:
            return bad_fields("aggregators.choose_resume", e)

        async def run() -> dict:
            async with self._hub.session_factory() as session:
                async with session.begin():
                    await choose_resume(session, aggregator_id, resume_id)
            return {"aggregator_id": aggregator_id, "resume_id": resume_id}

        return reply(self._hub.runner, run())

    def login(self, aggregator_id: int) -> dict:
        """Вход на сайт: видимый браузер, человек входит и закрывает окно, агент проверяет."""
        return self._launch(aggregator_id, "login", lambda bot: bot.login_aggregator(aggregator_id),
                            "Вход проверен.", LOGIN_REFUSALS)

    def run_now(self, aggregator_id: int) -> dict:
        """Обойти один источник вне очереди."""
        return self._launch(aggregator_id, "run_now", lambda bot: bot.run_aggregator_now(aggregator_id),
                            "Обход источника закончен.", AGGREGATOR_REFUSALS)

    def scan(self, aggregator_id: int) -> dict:
        """Перечислить резюме на сайте заново."""
        return self._launch(aggregator_id, "scan", lambda bot: bot.scan_aggregator(aggregator_id),
                            "Резюме обновлены.", LOGIN_REFUSALS)

    def _launch(self, aggregator_id: int, action: str, start, done: str, refusals: dict) -> dict:
        """Пустить работу бота на источнике. Зов бота приходит готовым: имя зова
        пишется литералом у каждого действия, иначе шов имён моста его не видит."""
        return launched_on_bot(
            self._hub,
            start,
            agent_refusals(refusals, self._hub.rs.chat),
            done,
            aggregator_id=aggregator_id,
            action=action,
        )


def _resume_to_dict(row) -> dict:
    """Резюме человека на сайте — строка блока резюме в карточке."""
    return {"id": row.id, "title": row.title, "url": row.url, "chosen": bool(row.is_chosen)}


_DELETION_REFUSALS = {
    "missing": NO_AGGREGATOR,
    "protected": WEB_SEARCH_KEPT,
    "busy": AGGREGATOR_REFUSALS["busy"],
}


def _refuse_deletion(block: str | None) -> None:
    """Исход, мешающий удалению, — словами окну; правило решает репозиторий и бот."""
    if block is not None:
        raise Denied(_DELETION_REFUSALS.get(block, AGGREGATOR_REFUSALS["error"]))
