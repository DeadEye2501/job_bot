"""Сборка поверхности основного окна из предметов.

Предметы разъезжаются своими файлами до конца этапа 3; пока часть их
лежит прямо здесь.
"""

from __future__ import annotations

import asyncio
import json
import logging
from concurrent.futures import CancelledError, Future
from typing import Any, Coroutine

from PySide6.QtCore import QObject, QTimer, Signal, Slot
from PySide6.QtWidgets import (
    QMainWindow,
    QWidget,
)
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from adapters import lm_studio
from adapters.lm_studio import LlmProviderConfig
from backend.repository import blacklist, blacklist_candidates, channels as channels_repo, companies_card, companies_list, hr_list, stats_pipeline, stats_summary, vacancies_mini  # два псевдонима: имена заняты локальными переменными
from client.form_payloads import read_company_spellings, read_new_company_fields
from backend.domain.telegram_identity import normalize_username
from backend.models import (
    BLACKLIST_KINDS,
    Company,
    TelegramChannel,
    Vacancy,
)
from backend.telegram_login import TelegramLogin, username_of
from backend.runtime_settings import RuntimeSettings
from client.bridge.answer import _dispatch_json, _err, _ok
from client.bridge.cv import CvSlots
from client.bridge.desktop import DesktopSlots
from client.bridge.llm import _do_list_models_for_creds, _do_llm_probe
from client.bridge.login import TelegramLoginSlots
from client.bridge.media import _avatar_data_url
from client.bridge.payload import _log_invalid_payload
from client.bridge.profile import ProfileSlots
from client.bridge.runner import AsyncRunner
from client.bridge.hr import HrSlots
from client.bridge.hr_chat import HrChatSlots
from client.bridge.vacancies import VacancySlots
from client.bridge.vacancy_actions import VacancyActionSlots
from client.bridge.vacancy_links import VacancyLinkSlots
from client.bridge.state import (
    _HEALTHCHECK_INTERVAL_MS,
    _UNREAD_INTERVAL_MS,
    WindowStateSlots,
)
from client.bridge.wire import (
    _blacklist_row_to_dict,
    _channel_row_to_dict,
    _company_picker_row_to_dict,
    _iso,
)


logger = logging.getLogger(__name__)



class MainApi(
    CvSlots, DesktopSlots, HrChatSlots, HrSlots, ProfileSlots,
    TelegramLoginSlots, VacancyActionSlots, VacancyLinkSlots, VacancySlots,
    WindowStateSlots,
    QObject,
):
    """Один объект «api», который канал отдаёт основному окну.

    Держит бота, часы общего состояния и предметы окна — своими примесями
    и, пока идёт этап 3, своими слотами прямо здесь.
    """

    contacts_company_list_loaded = Signal(str)
    contacts_company_detail_loaded = Signal(str)
    contacts_company_vacancies_loaded = Signal(str)
    contacts_company_hrs_loaded = Signal(str)
    contacts_company_merge_picker_loaded = Signal(str)
    contacts_company_action_done = Signal(str)
    contacts_blacklist_list_loaded = Signal(str)
    contacts_blacklist_action_done = Signal(str)
    contacts_blacklist_candidates_loaded = Signal(str)
    stats_kpi_loaded = Signal(str)
    stats_status_breakdown_loaded = Signal(str)
    stats_hr_responses_loaded = Signal(str)
    stats_skills_loaded = Signal(str)
    stats_channels_pipeline_loaded = Signal(str)
    system_logs_loaded = Signal(str)
    system_log_record_pushed = Signal(str)
    system_logs_cleared = Signal(str)
    system_settings_loaded = Signal(str)
    system_telegram_logout_done = Signal(str)
    llm_probe_done = Signal(str)
    llm_models_listed = Signal(str)
    settings_save_done = Signal(str)
    delete_all_data_done = Signal(str)
    contacts_channel_list_loaded = Signal(str)
    contacts_channel_detail_loaded = Signal(str)
    contacts_channel_vacancies_loaded = Signal(str)
    contacts_channel_action_done = Signal(str)
    contacts_channels_changed = Signal()
    contacts_lists_changed = Signal()
    vacancies_list_changed = Signal()

    def __init__(
        self,
        rs: RuntimeSettings,
        session_factory: async_sessionmaker,
        runner: AsyncRunner,
        parent_widget: QWidget | None = None,
        window: QMainWindow | None = None,
        engine: AsyncEngine | None = None,
    ) -> None:
        super().__init__()
        self._rs = rs
        self._session_factory = session_factory
        self._runner = runner
        self._parent_widget = parent_widget
        self._window = window
        self._engine = engine  # для dispose() в delete_all_data
        self._bot = None
        self._bot_task: Future | None = None

        self._health_timer = QTimer(self)
        self._health_timer.timeout.connect(self._kick_health)
        self._health_timer.start(_HEALTHCHECK_INTERVAL_MS)

        self._unread_timer = QTimer(self)
        self._unread_timer.timeout.connect(self._kick_unread)
        self._unread_timer.start(_UNREAD_INTERVAL_MS)

        # Hook log-buffer → Qt signal: each new LogRecord pushed (debounce
        # is on the JS side via existing patterns). Emit must be JSON-string
        # for Signal(str), so serialize the entry inline. Push gated на
        # `_logs_subscribed` flag — ставится из JS при заходе на logs-tab,
        # снимается при уходе/выключении auto-refresh, чтобы не сжигать
        # JSON-сериализацию + cross-thread dispatch на чужих экранах.
        # Вход через экран «Настройки» держит свой временный клиент —
        # отдельный от `self._bot._client`, который стартует позже. Имя
        # сессии тоже своё: под общим они делили бы один файл.
        self._login = TelegramLogin(
            "job_bot_relogin", rs, on_saved=self._after_login_saved
        )
        # Кэш TG-username: бот стартует медленно (Pyrogram session-load
        # + connect — секунды), а UI запрашивает settings сразу после
        # логина или открытия таба. Кэш заполняется при успешном get_me()
        # (или сразу после re-login) и переживает несколько запросов
        # пока bot._client не поднимется.
        self._username_cache: str = ""
        self._logs_subscribed = False
        from backend.log_buffer import get_handler
        # Recursion-guard: если внутри _on_record логнуть warning, тот warning
        # снова попадёт в LogBufferHandler.emit → on_record → бесконечная
        # рекурсия. Флаг блокирует повторный вход.
        _on_record_in_flight = {"v": False}
        def _on_record(entry: dict) -> None:
            if not self._logs_subscribed:
                return
            try:
                self.system_log_record_pushed.emit(json.dumps(entry))
            except Exception:
                if _on_record_in_flight["v"]:
                    return
                _on_record_in_flight["v"] = True
                try:
                    logger.warning(
                        "LogBuffer on_record callback failed", exc_info=True,
                    )
                finally:
                    _on_record_in_flight["v"] = False
        get_handler().on_record = _on_record

        # Без session_string Pyrogram свалится в interactive-login на stdin
        # (запрашивает код подтверждения в терминале). Бот стартанём только
        # после того, как пользователь авторизуется через UI («Войти»).
        if rs.tg is not None and rs.tg.session_string:
            self._start_bot()
        else:
            logger.info("No TG session — bot start deferred until user logs in via Settings")

    def _start_bot(self) -> None:
        """Construct AND run the Bot inside the runner loop.

        Constructing on the Qt thread used to crash silently — Pyrogram's
        SQLite session storage is thread-affine, and any exception from
        a coroutine submitted via `submit()` sits in the Future without a
        callback to surface it.
        """
        async def _build_and_run() -> None:
            from backend.bot.client import Bot

            logger.info("Constructing Bot and starting run loop")
            self._bot = Bot(self._rs, self._session_factory)
            def _on_cycle_start() -> None:
                self.ingestion_started.emit()

            def _on_cycle_end() -> None:
                self.ingestion_finished.emit(_ok())
                self._kick_unread()

            self._bot.on_cycle_start = _on_cycle_start
            self._bot.on_cycle_end = _on_cycle_end
            self._bot.on_progress = lambda stage, label, cur, tot: (
                self.progress_update.emit(json.dumps(
                    {"stage": stage, "label": label, "current": cur, "total": tot}
                ))
            )
            def _on_new_msg(hr_id: int) -> None:
                self.contacts_hr_messages_arrived.emit(_ok({"hr_id": hr_id}))
                self._kick_unread()
            self._bot.on_new_message = _on_new_msg

            def _on_hr_read(hr_id: int, max_tg_id: int) -> None:
                self.contacts_hr_read_receipt.emit(_ok({
                    "hr_id": hr_id,
                    "max_tg_id": max_tg_id,
                }))
            self._bot.on_hr_read = _on_hr_read

            def _on_channels_changed() -> None:
                self.contacts_channels_changed.emit()
            self._bot.on_channels_changed = _on_channels_changed

            def _on_contacts_changed() -> None:
                self.contacts_lists_changed.emit()
            self._bot.on_contacts_changed = _on_contacts_changed

            def _on_vacancies_changed() -> None:
                self.vacancies_list_changed.emit()
            self._bot.on_vacancies_changed = _on_vacancies_changed
            await self._bot.run()

        future = self._runner.submit(_build_and_run())

        def _log_if_crashed(f: Future) -> None:
            exc = f.exception()
            if exc is not None:
                logger.critical("Bot crashed — UI is now zombie", exc_info=exc)

        future.add_done_callback(_log_if_crashed)
        self._bot_task = future

    # --- helpers ----------------------------------------------------------

    def _dispatch(self, signal: Signal, coro: Coroutine[Any, Any, Any]) -> None:
        _dispatch_json(self._runner, signal, coro)

    def _dispatch_action(
        self,
        signal: Signal,
        coro: Coroutine[Any, Any, str],
        *,
        action: str,
        **error_extra,
    ) -> None:
        """Like ``_dispatch``, but wraps the coroutine so an unexpected
        exception is converted to a structured ``_err`` payload carrying
        the ``action`` discriminator + caller-provided extras (typically
        ``channel_id``). Without this, an exception lands in ``_dispatch``'s
        outer except and is emitted as a bare ``_err(message)`` without
        ``action`` — the JS handler then can't route it to the right branch
        and the UI ends up stuck (spinner stays / saving=true / popover
        ghost / optimistic flip never rolled back).
        """
        async def safe() -> str:
            try:
                return await coro
            except Exception as e:
                logger.exception("MainApi: action %s failed", action)
                return _err(f"{type(e).__name__}: {e}", action=action, **error_extra)
        self._dispatch(signal, safe())

    def cleanup(self) -> None:
        """Stop timers + the background bot. Runner shutdown is owned by shell.

        Cancels any in-flight poll cycle BEFORE waiting on the bot task so
        shutdown is fast even mid-Full-cycle (otherwise Qt's main thread
        would freeze for the rest of the channel pull).
        """
        self._health_timer.stop()
        self._unread_timer.stop()
        if self._bot is not None and self._bot_task is not None:
            self._bot.cancel_current_poll()
            self._bot.request_stop()
            try:
                self._bot_task.result(timeout=5)
            except TimeoutError:
                logger.warning(
                    "MainApi cleanup: bot task did not stop within 5s"
                )
            except Exception:
                logger.exception("MainApi cleanup: bot task raised on shutdown")

    # === Contacts / Companies (06) =====================================

    @Slot(str)
    def request_contacts_company_list(self, payload_json: str) -> None:
        """Page of Companies for the Contacts/Companies pane.

        Payload mirrors `request_contacts_hr_list` — search + epoch +
        offset/limit + replace/append/refresh mode. Backend echoes epoch
        so JS can drop stale responses when search/scroll race.
        """
        try:
            payload = json.loads(payload_json) if payload_json else {}
            search = payload.get("search")
            if search is not None:
                search = str(search)
            limit = payload.get("limit")
            limit = int(limit) if limit is not None else 50
            if limit > 200:
                limit = 200  # cap; mirrors the HR list slot
            offset = payload.get("offset")
            offset = int(offset) if offset is not None else 0
            mode = payload.get("mode") or "replace"
            if mode not in ("replace", "append", "refresh"):
                mode = "replace"
            epoch = payload.get("epoch")
        except (ValueError, TypeError) as e:
            _log_invalid_payload("request_contacts_company_list", e)
            self.contacts_company_list_loaded.emit(_err(f"Неверные поля: {e}"))
            return

        async def run() -> str:
            async with self._session_factory() as session:
                rows = await companies_list.list_companies_with_counts(
                    session, search=search, limit=limit, offset=offset,
                )
            has_more = (limit is not None) and (len(rows) == limit)
            return _ok({
                "search": search or "",
                "companies": [_company_picker_row_to_dict(r) for r in rows],
                "has_more": has_more,
                "mode": mode,
                "offset": offset,
                "epoch": epoch,
            })

        self._dispatch(self.contacts_company_list_loaded, run())

    @Slot(int)
    def request_contacts_company_detail(self, company_id: int) -> None:
        async def run() -> str:
            async with self._session_factory() as session:
                detail = await companies_card.get_company_detail(session, company_id)
            if detail is None:
                return _err("Компания не найдена.", company_id=company_id)
            return _ok({
                "company_id": detail.company.id,
                "name": detail.company.name,
                "website": detail.company.website,
                "aliases": list(detail.company.aliases or []),
                "notes": detail.company.notes,
                "vacancy_count": detail.vacancy_count,
                "hr_count": detail.hr_count,
                "blacklist_value": detail.blacklist_value,
            })

        self._dispatch(self.contacts_company_detail_loaded, run())

    @Slot(str)
    def request_contacts_company_vacancies(self, payload_json: str) -> None:
        """Push the vacancy mini-list for the Company detail pane.

        Payload: ``{company_id, epoch}``. ``company_id`` фильтрует ответ при
        переключении на другую компанию, ``epoch`` — race на одной и той же
        компании (рапид-флип статуса вакансии). Оба эхо'ятся обратно.
        """
        try:
            payload = json.loads(payload_json)
            company_id = int(payload["company_id"])
            epoch = payload.get("epoch")
        except (ValueError, TypeError, KeyError) as e:
            _log_invalid_payload("request_contacts_company_vacancies", e)
            self.contacts_company_vacancies_loaded.emit(_err(f"Неверные поля: {e}"))
            return

        async def run() -> str:
            async with self._session_factory() as session:
                rows = await vacancies_mini.list_vacancies_for_company(session, company_id)
            return _ok({
                "company_id": company_id,
                "epoch": epoch,
                "vacancies": [
                    {
                        "id": v.id,
                        "title": v.title or "",
                        "status": v.status.value if v.status else "New",
                        "score": v.score,
                        "created_at": _iso(v.created_at),
                    }
                    for v in rows
                ],
            })

        self._dispatch(self.contacts_company_vacancies_loaded, run())

    @Slot(int)
    def request_contacts_company_hrs(self, company_id: int) -> None:
        """HRs that have at least one vacancy at this company, with
        per-HR vacancy count restricted to that company.
        """
        async def run() -> str:
            async with self._session_factory() as session:
                rows = await hr_list.list_hrs_for_company(session, company_id)
            return _ok({
                "company_id": company_id,
                "hrs": [
                    {
                        "id": hr.id,
                        "name": hr.name,
                        "telegram_username": hr.telegram_username,
                        "vacancy_count": cnt,
                        "avatar": _avatar_data_url(hr.avatar),
                    }
                    for hr, cnt in rows
                ],
            })

        self._dispatch(self.contacts_company_hrs_loaded, run())

    @Slot(str)
    def update_blacklist(self, payload_json: str) -> None:
        """Partial update value/reason для одного blacklist-ряда.
        Payload: ``{id, value?, reason?}`` — присылаем только изменённое
        поле, бэкенд игнорит отсутствующие через sentinel.
        """
        blacklist_id = None
        try:
            payload = json.loads(payload_json)
            blacklist_id = int(payload["id"])
            kwargs: dict = {}
            if "value" in payload:
                kwargs["value"] = payload.get("value")
            if "reason" in payload:
                kwargs["reason"] = payload.get("reason")
            if not kwargs:
                raise KeyError("value / reason")
        except (ValueError, TypeError, KeyError) as e:
            _log_invalid_payload("update_blacklist", e)
            self.contacts_blacklist_action_done.emit(_err(
                f"Неверные поля: {e}", action="update", id=blacklist_id,
            ))
            return

        async def run() -> str:
            try:
                async with self._session_factory() as session:
                    async with session.begin():
                        ok = await blacklist.update_blacklist(
                            session, blacklist_id, **kwargs
                        )
            except blacklist.BlacklistUpdateError as e:
                return _err(str(e), id=blacklist_id, action="update")
            if not ok:
                return _err(
                    "Запись не найдена.",
                    id=blacklist_id, action="update",
                )
            # value мог поменяться → `is_blacklisted` в HR/Company может
            # перестать совпадать (или начать) → кросс-таб refresh.
            if "value" in kwargs:
                self.contacts_lists_changed.emit()
            return _ok({
                "id": blacklist_id,
                "fields": list(kwargs.keys()),
                "action": "update",
            })

        self._dispatch_action(
            self.contacts_blacklist_action_done, run(),
            action="update", id=blacklist_id,
        )

    @Slot(str)
    def request_create_blacklist(self, payload_json: str) -> None:
        """Add a new blacklist row from the UI «Добавить» modal.

        Payload: ``{kind, value, reason?}``. Бэк дедуплицирует по
        (kind, value): если ряд уже есть и неактивен — реактивирует, если
        активен — возвращает как есть. В обоих этих случаях ответ:
        ``{ok:true, id, created:false, action:"create"}``. На вставке
        нового — ``created:true``.
        """
        try:
            payload = json.loads(payload_json) if payload_json else {}
            kind = (payload.get("kind") or "").strip()
            value = (payload.get("value") or "").strip()
            reason = payload.get("reason")
        except (ValueError, TypeError) as e:
            _log_invalid_payload("request_create_blacklist", e)
            self.contacts_blacklist_action_done.emit(_err(
                f"Неверные поля: {e}", action="create",
            ))
            return

        if kind not in BLACKLIST_KINDS:
            self.contacts_blacklist_action_done.emit(_err(
                "Неверный тип записи.", action="create",
            ))
            return
        if not value:
            self.contacts_blacklist_action_done.emit(_err(
                "Значение не может быть пустым.", action="create",
            ))
            return

        async def run() -> str:
            try:
                async with self._session_factory() as session:
                    async with session.begin():
                        row, outcome = await blacklist.create_blacklist(
                            session, kind=kind, value=value, reason=reason,
                        )
                        new_id = row.id
                        # kind=channel → автоматически выключаем подходящие
                        # каналы. Без этого канал остался бы is_active=true
                        # после блокировки, и UI-toggle давал бы запутанную
                        # картину (загорелось — но bot всё равно скипает).
                        deactivated = 0
                        if kind == "channel":
                            deactivated = await channels_repo.deactivate_blacklisted_channels(session)
            except blacklist.BlacklistUpdateError as e:
                return _err(str(e), action="create")
            # Новая (или реактивированная) запись блеклиста влияет на
            # `is_blacklisted` HR/Company/Channel list rows — пушим refresh.
            self.contacts_lists_changed.emit()
            return _ok({
                "id": new_id,
                "created": outcome == "created",
                "deactivated_channels": deactivated,
                "action": "create",
            })

        self._dispatch_action(
            self.contacts_blacklist_action_done, run(), action="create",
        )

    @Slot(int)
    def delete_blacklist(self, blacklist_id: int) -> None:
        """Delete a blacklist row by id. UI всегда зовёт после confirm-
        модалки, повторное подтверждение не нужно.
        """
        async def run() -> str:
            async with self._session_factory() as session:
                async with session.begin():
                    ok = await blacklist.delete_blacklist(session, blacklist_id)
            if not ok:
                return _err(
                    "Запись не найдена.",
                    id=blacklist_id,
                    action="delete",
                )
            # `is_blacklisted` запечён в HR/Company list rows — сигналим
            # кросс-таб refresh, чтобы они не показывали удалённую
            # запись как блокирующую.
            self.contacts_lists_changed.emit()
            return _ok({"id": blacklist_id, "action": "delete"})

        self._dispatch_action(
            self.contacts_blacklist_action_done, run(),
            action="delete", id=blacklist_id,
        )

    @Slot(str)
    def set_blacklist_active(self, payload_json: str) -> None:
        """Toggle Blacklist.active для одного ряда. Echoes ``id`` и
        ``active`` чтобы UI откатил optimistic flip на ошибке.
        """
        blacklist_id = None
        active = None
        try:
            payload = json.loads(payload_json)
            raw_id = payload.get("id")
            if raw_id is not None:
                blacklist_id = int(raw_id)
            raw_active = payload.get("active")
            if raw_active is not None:
                active = bool(raw_active)
            if blacklist_id is None or active is None:
                raise KeyError("id / active")
        except (ValueError, TypeError, KeyError) as e:
            _log_invalid_payload("set_blacklist_active", e)
            self.contacts_blacklist_action_done.emit(_err(
                f"Неверные поля: {e}",
                action="set_active",
                id=blacklist_id,
                active=active,
            ))
            return

        async def run() -> str:
            async with self._session_factory() as session:
                async with session.begin():
                    ok = await blacklist.set_blacklist_active(
                        session, blacklist_id, active
                    )
            if not ok:
                return _err(
                    "Запись не найдена.",
                    id=blacklist_id,
                    active=active,
                    action="set_active",
                )
            # См. delete_blacklist — `is_blacklisted` в HR/Company должен
            # синхронизироваться по toggle тоже.
            self.contacts_lists_changed.emit()
            return _ok({
                "id": blacklist_id,
                "active": active,
                "action": "set_active",
            })

        self._dispatch_action(
            self.contacts_blacklist_action_done, run(),
            action="set_active",
            id=blacklist_id,
            active=active,
        )

    @Slot(str)
    def request_system_logs(self, payload_json: str) -> None:
        """Snapshot текущего log-buffer'а с фильтрами по level/source/search.

        Payload: ``{level?, source?, search?, limit?}``. level — точное
        совпадение на levelname, source — startswith (logger 'backend.flows'
        матчит фильтр 'backend'), search — substring case-insensitive по
        msg+details.

        Дешёвая 1-сек защита от auto-fire'а из JS (например, log-poll'а в
        пол-секунды): второй вызов в окне 1 секунды считается избыточным,
        UI всё равно перерендерится через подписку на push-сигнал.
        """
        import time as _time
        last_ts = getattr(self, "_logs_request_last_ts", 0.0)
        now = _time.time()
        if now - last_ts < 1.0:
            logger.debug("request_system_logs: debounced (interval %.2fs)", now - last_ts)
            return
        self._logs_request_last_ts = now
        from backend.log_buffer import get_handler
        try:
            payload = json.loads(payload_json) if payload_json else {}
            level = payload.get("level")
            source = payload.get("source")
            search = payload.get("search")
            limit = int(payload.get("limit") or 1000)
            if limit > 5000:
                limit = 5000
        except (ValueError, TypeError) as e:
            _log_invalid_payload("request_system_logs", e)
            self.system_logs_loaded.emit(_err(f"Неверные поля: {e}"))
            return

        async def run() -> str:
            # Один snapshot для всего: иначе race между среза'ми может
            # дать инконсистентные records vs counts.
            all_records = get_handler().snapshot()
            sources = sorted({r["source"] for r in all_records})
            level_counts: dict[str, int] = {}
            for r in all_records:
                lvl = r["level"]
                # CRITICAL рендерится как ERROR в UI — счётчик объединяем,
                # чтобы ERROR-pill не недоучитывал.
                if lvl == "CRITICAL":
                    lvl = "ERROR"
                level_counts[lvl] = level_counts.get(lvl, 0) + 1

            records = all_records
            if level:
                if level == "ERROR":
                    records = [r for r in records if r["level"] in ("ERROR", "CRITICAL")]
                else:
                    records = [r for r in records if r["level"] == level]
            if source:
                records = [r for r in records if r["source"].startswith(source)]
            if search:
                q = search.casefold()
                records = [
                    r for r in records
                    if q in r["msg"].casefold()
                    or (r.get("details") and q in r["details"].casefold())
                ]
            # Newest-first; UI рендерит сверху-вниз.
            records = list(reversed(records))[:limit]
            return _ok({
                "records": records,
                "sources": sources,
                "level_counts": level_counts,
                "total": len(all_records),
            })

        self._dispatch(self.system_logs_loaded, run())

    @Slot(bool)
    def set_logs_subscribed(self, subscribed: bool) -> None:
        """JS toggle'ит при заходе/уходе с logs-таба и при включении/
        выключении auto-refresh. Когда False, push-сигнал гасится в
        источнике (см. `_on_record` в __init__).
        """
        self._logs_subscribed = bool(subscribed)

    @Slot()
    def request_system_logs_clear(self) -> None:
        """Очищает in-memory ring-buffer. Не трогает файлы/stdout — это
        чисто UI-action для сброса видимого списка.
        """
        from backend.log_buffer import get_handler
        async def run() -> str:
            cleared = get_handler().clear()
            return _ok({"cleared": cleared})

        self._dispatch(self.system_logs_cleared, run())

    @Slot()
    def request_system_settings(self) -> None:
        """Snapshot of current runtime settings for the Settings screen.

        api_hash отправляем — eye-toggle в UI должен уметь показать значение.
        QWebChannel живёт только в локальном Qt-окне, не уезжает в сеть.
        """
        tg = self._rs.tg
        chat = self._rs.chat
        embed = self._rs.embed
        bot = self._bot

        async def run() -> str:
            client = getattr(bot, "_client", None) if bot is not None else None
            # На холодном старте Pyrogram session-load + connect занимает
            # пару секунд; UI запросит settings раньше. Ждём короткий
            # connect-window (до 3 сек).
            if client is not None and not getattr(client, "is_connected", False):
                for _ in range(15):
                    await asyncio.sleep(0.2)
                    if getattr(client, "is_connected", False):
                        break
            asked = None
            connected = client is not None and getattr(client, "is_connected", False)
            if connected:
                asked = await username_of(client)
                if asked is None:
                    logger.warning("get_me() failed for settings", exc_info=True)
            if asked is None:
                # Спросить не вышло или бот ещё не подключился — отдаём кэш.
                username = self._username_cache
            else:
                # Пустая строка — это ответ «ника нет», и он перебивает кэш:
                # снятый ник иначе остался бы на экране прежним.
                username = asked
                self._username_cache = asked
            return _ok({
                "tg": {
                    "api_id": str(tg.api_id) if tg else "",
                    "api_hash": tg.api_hash if tg else "",
                    "phone": tg.phone if tg else "",
                    "has_password": bool(tg and tg.password),
                    "has_session": bool(tg and tg.session_string),
                    "username": username,
                },
                "chat": {
                    "base_url": chat.base_url if chat else "",
                    "api_key": chat.api_key if chat else "",
                    "model": chat.model if chat else "",
                },
                "embed": {
                    "base_url": embed.base_url if embed else "",
                    "api_key": embed.api_key if embed else "",
                    "model": embed.model if embed else "",
                },
                "pipeline": {
                    "scoring_threshold": self._rs.scoring_threshold,
                    "poll_interval_sec": self._rs.poll_interval_sec,
                    "backfill_limit": self._rs.backfill_limit,
                    "dm_backfill_limit": self._rs.dm_backfill_limit,
                    "send_locked": self._rs.send_locked,
                },
            })

        self._dispatch(self.system_settings_loaded, run())

    @Slot(str)
    def request_llm_probe(self, payload_json: str) -> None:
        """Connectivity check for an LLM provider (chat / embed).

        Payload: ``{kind: 'chat'|'embed', base_url, api_key, model}``.
        Использует draft-значения из UI, не текущий rs — чтобы юзер мог
        проверить новые настройки до сохранения. Замеряем latency полного
        check'а (list_models + 1-token ping).
        """
        # Init defaults ДО try, чтобы все error-ветки могли echo'нуть kind
        # обратно — JS использует его для роутинга в нужный *Probe-state.
        kind = ""
        try:
            payload = json.loads(payload_json) if payload_json else {}
            kind = str(payload.get("kind", "")).strip()
            base_url = str(payload.get("base_url", "")).strip().rstrip("/")
            api_key = str(payload.get("api_key", ""))
            model = str(payload.get("model", "")).strip()
            if kind not in ("chat", "embed"):
                raise ValueError(f"bad kind: {kind!r}")
            if not base_url or not model:
                raise ValueError("base_url и model обязательны")
        except (ValueError, TypeError) as e:
            _log_invalid_payload("request_llm_probe", e)
            self.llm_probe_done.emit(_err(f"Неверные поля: {e}", kind=kind))
            return

        cfg = LlmProviderConfig(base_url=base_url, api_key=api_key, model=model)
        check_fn = lm_studio.check_chat if kind == "chat" else lm_studio.check_embed

        async def run() -> str:
            try:
                ok, detail, _models, latency_ms = await _do_llm_probe(cfg, check_fn)
            except Exception as e:
                logger.exception("llm probe failed")
                return _err(f"{type(e).__name__}: {e}", kind=kind)
            if not ok:
                return _err(detail, kind=kind)
            return _ok({"kind": kind, "model": cfg.model, "latency_ms": latency_ms})

        self._dispatch(self.llm_probe_done, run())

    @Slot(str)
    def save_settings(self, payload_json: str) -> None:
        """Apply a partial settings patch — autosave из UI на blur/change.

        Payload — словарь с любыми из ключей:
        - chat: {base_url, api_key, model}
        - embed: {base_url, api_key, model}
        - app: {scoring_threshold, poll_interval_sec, backfill_limit,
          dm_backfill_limit, ...}
        Применяем через rs.set_chat / rs.set_embed / rs.set_app. Ошибки
        возвращаем в payload, UI показывает toast.
        """
        try:
            payload = json.loads(payload_json) if payload_json else {}
        except (ValueError, TypeError) as e:
            _log_invalid_payload("save_settings", e)
            self.settings_save_done.emit(_err(f"Неверные поля: {e}"))
            return

        chat = payload.get("chat") if isinstance(payload.get("chat"), dict) else None
        embed = payload.get("embed") if isinstance(payload.get("embed"), dict) else None
        app = payload.get("app") if isinstance(payload.get("app"), dict) else None

        # Pre-validate: пустой model — почти всегда last-blur'на стерлась
        # в tab-switch'е (см. main.html guards). Раньше уходило в
        # _set_llm как пустая строка, _from_llm_row возвращал None и
        # config «исчезал» — юзер думал «починилось», а LLM-вызовы
        # начинали валиться. Лучше отбить рано с понятной ошибкой.
        for kind_name, payload in (("chat", chat), ("embed", embed)):
            if payload is None:
                continue
            model_val = str(payload.get("model") or "").strip()
            if not model_val:
                logger.warning(
                    "save_settings: empty model for %s — refusing to save",
                    kind_name,
                )
                self.settings_save_done.emit(
                    _err(f"{kind_name}: пустое имя модели — сохранение отклонено")
                )
                return

        async def run() -> str:
            applied: list[str] = []
            try:
                if chat is not None:
                    await self._rs.set_chat(
                        base_url=str(chat.get("base_url") or "").strip().rstrip("/"),
                        api_key=str(chat.get("api_key") or ""),
                        model=str(chat.get("model") or "").strip(),
                    )
                    applied.append("chat")
                if embed is not None:
                    await self._rs.set_embed(
                        base_url=str(embed.get("base_url") or "").strip().rstrip("/"),
                        api_key=str(embed.get("api_key") or ""),
                        model=str(embed.get("model") or "").strip(),
                    )
                    applied.append("embed")
                if app is not None:
                    # Whitelist: чтобы UI не мог по ошибке/опечатке писать
                    # произвольные ключи в app_settings.
                    allowed = {
                        "scoring_threshold", "poll_interval_sec",
                        "backfill_limit", "dm_backfill_limit",
                        "send_locked",
                    }
                    for key, value in app.items():
                        if key not in allowed:
                            logger.warning("save_settings: unknown app key %r ignored", key)
                            continue
                        # Bool → "true"/"false": app_settings хранит строки,
                        # rs.send_locked парсит обратно в lower-case bool
                        # (см. RuntimeSettings.send_locked). True/False через
                        # str() дали бы "True"/"False" — не пройдут .lower()
                        # сравнение с "true".
                        if isinstance(value, bool):
                            value = "true" if value else "false"
                        await self._rs.set_app(str(key), str(value))
                        applied.append(f"app.{key}")
                    # Sync send_locked в adapters.telegram чтобы новое значение
                    # начало действовать без рестарта бота. Авторитет —
                    # rs.send_locked; константа — кеш для горячего пути отправки.
                    if "send_locked" in app:
                        from adapters import telegram as _tg
                        _tg.SEND_LOCKED = self._rs.send_locked
            except Exception as e:
                logger.exception("save_settings failed")
                return _err(f"{type(e).__name__}: {e}", applied=applied)
            return _ok({"applied": applied})

        self._dispatch(self.settings_save_done, run())

    @Slot()
    def request_delete_all_data(self) -> None:
        """Опасная зона → «Удалить всё». Останавливает бота, закрывает
        DB-engine, удаляет файлы (jobbot.db + sidecars, sessions/, media/),
        и завершает приложение через QApplication.quit() (юзер сам
        перезапустит — следующий старт уйдёт в визард, т.к. все настройки
        стерты вместе с БД).
        """
        bot = self._bot
        bot_task = self._bot_task
        # Захватываем сразу, потом null'им — чтобы health-timer не дёрнулся
        # на полу-удалённой БД. И, главное, тут же тушим сами таймеры
        # (health/unread) — иначе после engine.dispose() их следующий тик
        # откроет fresh connection из пула и Windows откажется удалять
        # jobbot.db с открытым handle'ом.
        self._bot = None
        self._bot_task = None
        self._health_timer.stop()
        self._unread_timer.stop()

        async def run() -> str:
            import shutil
            from config import get_data_dir
            errors: list[str] = []

            # 1) Стопаем бота — Pyrogram-сессия закроется, файлы освободятся.
            if bot is not None:
                try:
                    bot.cancel_current_poll()
                except Exception:
                    logger.debug("delete_all: cancel_current_poll failed", exc_info=True)
                try:
                    bot.request_stop()
                except Exception:
                    logger.debug("delete_all: request_stop failed", exc_info=True)
            if bot_task is not None:
                try:
                    await asyncio.wait_for(asyncio.wrap_future(bot_task), timeout=10)
                except asyncio.TimeoutError:
                    logger.warning("delete_all: bot did not stop within 10s")
                except Exception:
                    logger.exception("delete_all: bot task raised")

            # 2) Закрываем engine — иначе Windows не даст удалить jobbot.db.
            if self._engine is not None:
                try:
                    await self._engine.dispose()
                except Exception as e:
                    errors.append(f"engine.dispose: {e}")
                    logger.exception("delete_all: engine.dispose failed")

            # 3) Удаляем файлы.
            data_dir = get_data_dir()
            for name in ("jobbot.db", "jobbot.db-shm", "jobbot.db-wal"):
                p = data_dir / name
                if p.exists():
                    try:
                        p.unlink()
                    except Exception as e:
                        errors.append(f"{name}: {e}")
                        logger.exception("delete_all: failed to remove %s", p)
            for sub in ("sessions", "media"):
                d = data_dir / sub
                if d.exists():
                    try:
                        shutil.rmtree(d)
                    except Exception as e:
                        errors.append(f"{sub}/: {e}")
                        logger.exception("delete_all: failed to remove %s", d)

            # 4) Удаляем Fernet master key из OS-keychain'а. Без этого
            # после reinstall'а у юзера висит мёртвая запись в Windows
            # Credential Manager / macOS Keychain — некритично (новый
            # ключ перегенерится), но «delete all» должно быть «delete
            # all», а не «delete most».
            try:
                import keyring as _keyring
                from backend.crypto import (
                    _KEYRING_SERVICE,
                    _KEYRING_KEY,
                )
                _keyring.delete_password(_KEYRING_SERVICE, _KEYRING_KEY)
            except Exception as e:
                # delete_password может бросить если записи нет — это OK.
                logger.debug("delete_all: keyring entry already absent (%s)", e)

            if errors:
                return _err("Не все файлы удалось удалить: " + "; ".join(errors))
            return _ok({})

        # После завершения корутины (успех/ошибка) — эмитим результат и
        # сразу убиваем процесс через os._exit(0). Штатный QApplication.quit()
        # здесь приводит к зависанию: aboutToQuit → api.cleanup() →
        # runner.stop() → gather отменяемых тасков, и какой-то из них
        # натыкается на удалённую sessions/jobbot.db и блокирует unwind.
        # Для «wipe everything» все нужные действия (бот остановлен,
        # engine disposed, файлы удалены) уже сделаны выше — штатный
        # cleanup нам не нужен.
        future = self._runner.submit(run())

        def _on_done(f: Future) -> None:
            try:
                payload = f.result()
            except Exception as e:
                payload = _err(f"{type(e).__name__}: {e}")
            self.delete_all_data_done.emit(payload)
            import os
            os._exit(0)

        future.add_done_callback(_on_done)

    @Slot(str)
    def request_llm_models(self, payload_json: str) -> None:
        """Background-fetch списка моделей — UI наполняет datalist для
        автокомплита поля «Модель». Под LM Studio предпочтительно
        ``/api/v0/models`` с фильтром по type/state (см. lm_studio.list_models),
        фолбэк на OpenAI-совместимый ``/v1/models``. Best-effort, ошибки в
        payload."""
        try:
            payload = json.loads(payload_json) if payload_json else {}
            kind = str(payload.get("kind") or "")
            base_url = str(payload.get("base_url") or "").strip().rstrip("/")
            api_key = str(payload.get("api_key") or "")
        except (ValueError, TypeError):
            return
        if not base_url or kind not in ("chat", "embed"):
            return

        async def run() -> str:
            result = await _do_list_models_for_creds(base_url, api_key, kind=kind)
            return json.dumps({"kind": kind, **result})

        self._dispatch(self.llm_models_listed, run())

    @Slot()
    def request_telegram_logout(self) -> None:
        """Stop the bot, revoke server-side TG session, clear creds in DB.

        Sequence:
          1. cancel current poll + ask bot to stop (via log_out_session, which
             sends DROP_AUTH then sets stop_event)
          2. wait for the bot run-task to finish (its finally calls
             client.stop() — already disconnected after log_out, no-op)
          3. clear session_string + password in DB so health/UI flip to
             "Нет сессии"
          4. null out _bot/_bot_task — re-login starts a fresh bot
        """
        bot = self._bot
        bot_task = self._bot_task

        async def run() -> str:
            # Если в момент logout открыта модалка re-auth, закрываем её
            # бэкенд-state тоже — иначе при следующем «Войти» налетим на
            # «уже отправили код».
            await self._login.forget()
            if bot is not None:
                bot.cancel_current_poll()
                await bot.log_out_session()
            if bot_task is not None:
                try:
                    await asyncio.wait_for(
                        asyncio.wrap_future(bot_task), timeout=10
                    )
                except asyncio.TimeoutError:
                    logger.warning("logout: bot did not stop within 10s")
                except Exception:
                    logger.exception("logout: bot task raised")
            await self._rs.clear_tg()
            self._username_cache = ""
            return _ok({})

        # Null out before dispatch so concurrent slots don't try to use a
        # half-stopped bot.
        self._bot = None
        self._bot_task = None
        self._dispatch(self.system_telegram_logout_done, run())

    @Slot()
    def cancel_telegram_login(self) -> None:
        """Юзер закрыл модалку re-auth до завершения. Чистим временный
        Pyrogram-клиент и обнуляем OTP-state, чтобы не оставлять открытый
        сокет и не уйти в «уже отправили код» при следующей попытке.
        """
        self._dispatch_noop(self._login.forget())

    def _dispatch_noop(self, coro: Coroutine[Any, Any, Any]) -> None:
        """Fire-and-forget: запускаем корутину на runner'е, ошибки в лог.
        Сигнал обратно не нужен — UI закрывает модалку оптимистично.
        """
        future = self._runner.submit(coro)

        def _on_done(f: Future) -> None:
            try:
                f.result()
            except (CancelledError, asyncio.CancelledError):
                pass
            except Exception:
                logger.warning("noop dispatch failed", exc_info=True)

        future.add_done_callback(_on_done)

    def _after_login_saved(self, username: str | None) -> None:
        """Новая сессия сохранена: запомнить ник и поднять бота, если он лежит.

        Не спросившийся ник (`None`) прежний в кэше не трогает: показать
        старый вернее, чем стереть его до первого удачного `get_me` у бота.
        """
        if username is not None:
            self._username_cache = username
        if self._bot is None:
            self._start_bot()

    @Slot(str)
    def request_stats_status_breakdown(self, period: str) -> None:
        """Counts по 11 статусам за period — для funnel и all-status
        счётчиков. Echoes period для drop'а stale-ответов.
        """
        async def run() -> str:
            async with self._session_factory() as session:
                data = await stats_summary.get_stats_status_breakdown(
                    session, period=period,
                )
            return _ok(data)

        self._dispatch(self.stats_status_breakdown_loaded, run())

    @Slot(str)
    def request_stats_kpi(self, period: str) -> None:
        """Top-row KPIs для экрана Statistics. period ∈
        {today, week, month, quarter, all}.
        """
        async def run() -> str:
            async with self._session_factory() as session:
                data = await stats_summary.get_stats_kpi(session, period=period)
            return _ok(data)

        self._dispatch(self.stats_kpi_loaded, run())

    @Slot(str)
    def request_stats_hr_responses(self, period: str) -> None:
        """HR-response-time + weekday-распределение. Source:
        VacancyStatusHistory (Applied) + Message (incoming) — см.
        get_stats_hr_responses в repository."""
        async def run() -> str:
            async with self._session_factory() as session:
                data = await stats_summary.get_stats_hr_responses(
                    session, period=period,
                )
            return _ok(data)

        self._dispatch(self.stats_hr_responses_loaded, run())

    @Slot(str)
    def request_stats_skills(self, period: str) -> None:
        """Top-N skills (vacancy.stack tags за period) + флаг mine."""
        async def run() -> str:
            async with self._session_factory() as session:
                data = await stats_summary.get_stats_skills(
                    session, period=period,
                )
            return _ok(data)

        self._dispatch(self.stats_skills_loaded, run())

    @Slot(str)
    def request_stats_channels_pipeline(self, period: str) -> None:
        """Per-channel pipeline (Ингест / Воронка отклика / Конверсия)."""
        async def run() -> str:
            async with self._session_factory() as session:
                data = await stats_pipeline.get_stats_channels_pipeline(
                    session, period=period,
                )
            return _ok(data)

        self._dispatch(self.stats_channels_pipeline_loaded, run())

    @Slot(str)
    def request_blacklist_candidates(self, kind: str) -> None:
        """Список options для combobox'а add-modal'а blacklist'а.
        Echoes ``kind`` чтобы JS дропнул stale-ответ если юзер успел
        сменить тип до прихода данных.
        """
        async def run() -> str:
            async with self._session_factory() as session:
                items = await blacklist_candidates.list_blacklist_candidates(
                    session, kind
                )
            return _ok({"kind": kind, "items": items})

        self._dispatch(self.contacts_blacklist_candidates_loaded, run())

    @Slot()
    def request_contacts_blacklist_list(self) -> None:
        """Пуш всех строк blacklist'а — без пагинации/SQL-фильтров,
        размер мал. UI фильтрует локально (kind / search).
        """
        async def run() -> str:
            async with self._session_factory() as session:
                rows = await blacklist.list_blacklist(session)
            return _ok({
                "items": [_blacklist_row_to_dict(r) for r in rows],
            })

        self._dispatch(self.contacts_blacklist_list_loaded, run())

    @Slot(str)
    def request_contacts_channel_list(self, payload_json: str) -> None:
        """Full list of Telegram channels for the Contacts/Channels pane.

        No pagination — channel sets are tiny. Echoes the request epoch so
        the UI can drop stale responses when search races.
        """
        try:
            payload = json.loads(payload_json) if payload_json else {}
            search = payload.get("search")
            if search is not None:
                search = str(search)
            epoch = payload.get("epoch")
        except (ValueError, TypeError) as e:
            _log_invalid_payload("request_contacts_channel_list", e)
            self.contacts_channel_list_loaded.emit(_err(f"Неверные поля: {e}"))
            return

        async def run() -> str:
            async with self._session_factory() as session:
                # Self-heal: тушим каналы, попавшие в blacklist, но всё ещё
                # помеченные is_active=true (исторический дрейф / правки БД
                # мимо UI). Идемпотентно, и держит инвариант «blacklisted
                # ⇒ is_active=false» — иначе bot polling всё ещё трогал бы
                # запрещённые каналы.
                async with session.begin():
                    await channels_repo.deactivate_blacklisted_channels(session)
                rows = await channels_repo.list_telegram_channels(session, search=search)
            return _ok({
                "search": search or "",
                "channels": [_channel_row_to_dict(r) for r in rows],
                "epoch": epoch,
            })

        self._dispatch(self.contacts_channel_list_loaded, run())

    @Slot(int)
    def request_contacts_channel_detail(self, channel_id: int) -> None:
        """Detail-pane payload for one Telegram channel.

        Echoes ``channel_id`` so the UI drops stale responses when the user
        clicks another row mid-flight (mirrors HR/Company detail pattern).
        Includes computed stats (status breakdown + KPI ratios + recent
        ingestion rate) — see ``ChannelStats`` for shape.
        """
        async def run() -> str:
            async with self._session_factory() as session:
                detail = await channels_repo.get_channel_detail(session, channel_id)
            if detail is None:
                return _err("Канал не найден.", channel_id=channel_id)
            ch = detail.channel
            stats = detail.stats
            return _ok({
                "channel_id": ch.id,
                "username": ch.username,
                "title": ch.title,
                "is_active": bool(ch.is_active),
                "avatar": _avatar_data_url(ch.avatar),
                "stats": {
                    "status_counts": stats.status_counts,
                    "total": stats.total,
                    "vacancies_per_day": stats.vacancies_per_day,
                    "fit_percent": stats.fit_percent,
                    "apply_percent": stats.apply_percent,
                    "response_percent": stats.response_percent,
                },
                "blacklist_value": detail.blacklist_value,
            })

        self._dispatch(self.contacts_channel_detail_loaded, run())

    @Slot(str)
    def request_contacts_channel_vacancies(self, payload_json: str) -> None:
        """Pagination-aware vacancies fetch for the channels detail pane.

        Payload: ``{channel_id, limit, offset, mode}``. ``mode`` ∈
        {"replace", "append"} — replace wipes JS-side list, append concat'ит
        к существующему. Backend echoes channel_id + offset + has_more
        чтобы фронт мог дропать stale-ответы при гонке скролла/выбора.
        """
        try:
            payload = json.loads(payload_json) if payload_json else {}
            channel_id = int(payload["channel_id"])
            limit = int(payload.get("limit") or 50)
            if limit > 200:
                limit = 200
            offset = int(payload.get("offset") or 0)
            mode = payload.get("mode") or "replace"
            if mode not in ("replace", "append"):
                mode = "replace"
        except (ValueError, TypeError, KeyError) as e:
            _log_invalid_payload("request_contacts_channel_vacancies", e)
            self.contacts_channel_vacancies_loaded.emit(_err(f"Неверные поля: {e}"))
            return

        async def run() -> str:
            async with self._session_factory() as session:
                rows = await vacancies_mini.list_vacancies_for_channel(
                    session, channel_id, limit=limit, offset=offset,
                )
                # Diagnostic — раз баг проявляется: 0 здесь vs N в stats
                # помогает понять, в репо ли проблема или в bridge-эхо.
                if not rows:
                    total_for_channel = int(
                        (
                            await session.execute(
                                select(func.count(Vacancy.id))
                                .where(Vacancy.source_channel_id == channel_id)
                            )
                        ).scalar_one()
                    )
                    if total_for_channel > 0:
                        logger.warning(
                            "channel %d: list_vacancies_for_channel returned 0 "
                            "but %d rows match source_channel_id (limit=%d offset=%d) "
                            "— investigate query mismatch with stats",
                            channel_id,
                            total_for_channel,
                            limit,
                            offset,
                        )
            return _ok({
                "channel_id": channel_id,
                "offset": offset,
                "mode": mode,
                "has_more": len(rows) == limit,
                "vacancies": [
                    {
                        "id": v.id,
                        "title": v.title or "",
                        "status": v.status.value if v.status else "New",
                        "score": v.score,
                        "created_at": _iso(v.created_at),
                        "posted_at": _iso(v.posted_at),
                    }
                    for v in rows
                ],
            })

        self._dispatch(self.contacts_channel_vacancies_loaded, run())

    @Slot(int)
    def contacts_add_channel_to_blacklist(self, channel_id: int) -> None:
        """Insert kind="channel" blacklist row for this channel.
        Value = `@{username}`. Idempotent (re-activates inactive row).
        Mirrors HR/Company patterns. Pushes contacts_lists_changed so
        cross-tab `is_blacklisted` flags refresh.
        """
        async def run() -> str:
            async with self._session_factory() as session:
                ch = await session.get(TelegramChannel, channel_id)
                if ch is None:
                    return _err("Канал не найден.", channel_id=channel_id, action="blacklist")
                value = channels_repo.channel_blacklist_preferred_value(ch)
                if value is None:
                    return _err(
                        "У канала нет @username.",
                        channel_id=channel_id, action="blacklist",
                    )
                _, outcome = await blacklist.create_blacklist(
                    session, kind="channel", value=value,
                )
                # Канал в blacklist → автоматически выключаем сам канал,
                # чтобы UI-toggle отражал реальное «канал не работает».
                if ch.is_active:
                    ch.is_active = False
                await session.commit()
            self.contacts_lists_changed.emit()
            return _ok({
                "action": "blacklist",
                "channel_id": channel_id,
                "value": value,
                "existed": outcome != "created",
                "was_inactive": outcome == "reactivated",
            })

        self._dispatch(self.contacts_channel_action_done, run())

    @Slot(int)
    def contacts_remove_channel_from_blacklist(self, channel_id: int) -> None:
        """Deactivate any kind="channel" blacklist row for this channel."""
        async def run() -> str:
            async with self._session_factory() as session:
                ch = await session.get(TelegramChannel, channel_id)
                if ch is None:
                    return _err("Канал не найден.", channel_id=channel_id, action="unblacklist")
                candidates = channels_repo.channel_blacklist_candidates(ch)
                if not candidates:
                    return _err(
                        "У канала нет @username.",
                        channel_id=channel_id, action="unblacklist",
                    )
                updated = await blacklist.deactivate_blacklist_values(
                    session, "channel", candidates,
                )
                await session.commit()
            self.contacts_lists_changed.emit()
            return _ok({
                "action": "unblacklist",
                "channel_id": channel_id,
                "updated": updated,
            })

        self._dispatch(self.contacts_channel_action_done, run())

    @Slot(int)
    def request_channel_poll_now(self, channel_id: int) -> None:
        """UI «Прогнать сейчас» — single-channel poll."""
        async def run() -> str:
            if self._bot is None:
                return _err("Бот ещё не готов.", channel_id=channel_id, action="poll_now")
            status = await self._bot.poll_channel_now(channel_id)
            if status == "ok":
                return _ok({
                    "channel_id": channel_id,
                    "action": "poll_now",
                    "status": status,
                })
            messages = {
                "busy": "Уже идёт другой цикл, попробуйте позже.",
                "missing": "Канал не найден или без @username.",
                "cancelled": "Поллинг канала отменён.",
                "error": "Не удалось прогнать канал — см. логи.",
            }
            return _err(
                messages.get(status, "Не удалось прогнать канал."),
                channel_id=channel_id,
                action="poll_now",
                status=status,
            )

        self._dispatch_action(
            self.contacts_channel_action_done, run(),
            action="poll_now", channel_id=channel_id,
        )

    @Slot(int)
    def request_channel_reset_cursor(self, channel_id: int) -> None:
        """UI «Сбросить курсор» — clears last_processed_msg_id."""
        async def run() -> str:
            if self._bot is None:
                return _err("Бот ещё не готов.", channel_id=channel_id, action="reset_cursor")
            ok = await self._bot.reset_channel_cursor(channel_id)
            if not ok:
                return _err(
                    "Канал не найден.",
                    channel_id=channel_id,
                    action="reset_cursor",
                )
            return _ok({"channel_id": channel_id, "action": "reset_cursor"})

        self._dispatch_action(
            self.contacts_channel_action_done, run(),
            action="reset_cursor", channel_id=channel_id,
        )

    @Slot(int)
    def request_channel_delete(self, channel_id: int) -> None:
        """UI «Удалить канал» — nulls vacancy FKs, deletes row."""
        async def run() -> str:
            if self._bot is None:
                return _err("Бот ещё не готов.", channel_id=channel_id, action="delete")
            detached = await self._bot.delete_channel(channel_id)
            if detached is None:
                return _err(
                    "Канал не найден.",
                    channel_id=channel_id,
                    action="delete",
                )
            return _ok({
                "channel_id": channel_id,
                "detached_vacancies": detached,
                "action": "delete",
            })

        self._dispatch_action(
            self.contacts_channel_action_done, run(),
            action="delete", channel_id=channel_id,
        )

    @Slot(str)
    def request_create_channel(self, payload_json: str) -> None:
        """Add a new TelegramChannel from the UI «Добавить канал» modal.

        Accepts raw input — `@username`, plain `username`, or any t.me URL
        — and normalizes via the same parser used for HR contacts. On
        duplicate (channel already exists), returns ``ok=true`` with
        ``created=false`` so the UI selects the existing row instead of
        showing an error. Metadata fetch is opportunistic on the backend.
        """
        try:
            payload = json.loads(payload_json) if payload_json else {}
            raw = (payload.get("input") or "").strip()
        except (ValueError, TypeError) as e:
            _log_invalid_payload("request_create_channel", e)
            self.contacts_channel_action_done.emit(
                _err(f"Неверные поля: {e}", action="create")
            )
            return

        if not raw:
            self.contacts_channel_action_done.emit(
                _err("Укажите @username или ссылку на канал.", action="create")
            )
            return

        username = normalize_username(raw)
        if not username:
            self.contacts_channel_action_done.emit(
                _err(
                    "Не удалось распознать @username канала. "
                    "Поддерживаются форматы: @name, name, t.me/name.",
                    action="create",
                )
            )
            return

        async def run() -> str:
            if self._bot is None:
                return _err("Бот ещё не готов.", action="create")
            channel_id, status = await self._bot.add_channel(username)
            if status == "invalid":
                return _err(
                    f"Telegram не нашёл канал @{username}. Проверьте имя.",
                    action="create",
                    status=status,
                )
            return _ok({
                "channel_id": channel_id,
                "username": username,
                "created": status == "created",
                "action": "create",
                "status": status,
            })

        self._dispatch_action(
            self.contacts_channel_action_done, run(), action="create",
        )

    @Slot(str)
    def set_all_channels_active(self, payload_json: str) -> None:
        """Bulk-flip is_active на всех каналах. Echoes ``is_active`` чтобы
        фронт мог откатить optimistic-update на ошибке.
        """
        try:
            payload = json.loads(payload_json)
            is_active = bool(payload["is_active"])
        except (ValueError, TypeError, KeyError) as e:
            _log_invalid_payload("set_all_channels_active", e)
            self.contacts_channel_action_done.emit(_err(
                f"Неверные поля: {e}", action="set_all_active",
            ))
            return

        async def run() -> str:
            async with self._session_factory() as session:
                async with session.begin():
                    affected = await channels_repo.set_all_channels_active(
                        session, is_active
                    )
            return _ok({
                "is_active": is_active,
                "affected": affected,
                "action": "set_all_active",
            })

        self._dispatch_action(
            self.contacts_channel_action_done, run(),
            action="set_all_active", is_active=is_active,
        )

    @Slot(str)
    def set_channel_active(self, payload_json: str) -> None:
        """Toggle TelegramChannel.is_active for one row.

        Echoes ``channel_id`` and the requested ``is_active`` so the UI can
        rollback its optimistic flip on error without re-querying the list.
        """
        # Парсим осторожно: если payload неполный, тянем сколько смогли,
        # чтобы action+channel_id всё же попали в _err — иначе фронт не
        # знает, какой именно ряд откатывать.
        channel_id = None
        is_active = None
        try:
            payload = json.loads(payload_json)
            raw_id = payload.get("channel_id")
            if raw_id is not None:
                channel_id = int(raw_id)
            raw_active = payload.get("is_active")
            if raw_active is not None:
                is_active = bool(raw_active)
            if channel_id is None or is_active is None:
                raise KeyError("channel_id / is_active")
        except (ValueError, TypeError, KeyError) as e:
            _log_invalid_payload("set_channel_active", e)
            self.contacts_channel_action_done.emit(_err(
                f"Неверные поля: {e}",
                action="set_active",
                channel_id=channel_id,
                is_active=is_active,
            ))
            return

        async def run() -> str:
            async with self._session_factory() as session:
                async with session.begin():
                    # Включить канал, который сейчас в blacklist'е, нельзя —
                    # блокируем на уровне бэка, чтобы любой канал-toggle (в
                    # т.ч. через bulk «Включить все») не оживлял запрещённое.
                    if is_active and await channels_repo.is_channel_blacklisted(
                        session, channel_id
                    ):
                        return _err(
                            "Канал в blacklist — нельзя включить.",
                            channel_id=channel_id,
                            is_active=is_active,
                            action="set_active",
                        )
                    ok = await channels_repo.set_channel_active(
                        session, channel_id, is_active
                    )
            if not ok:
                return _err(
                    "Канал не найден.",
                    channel_id=channel_id,
                    is_active=is_active,
                    action="set_active",
                )
            return _ok({
                "channel_id": channel_id,
                "is_active": is_active,
                "action": "set_active",
            })

        self._dispatch_action(
            self.contacts_channel_action_done, run(),
            action="set_active",
            channel_id=channel_id,
            is_active=is_active,
        )

    @Slot(str)
    def request_contacts_company_merge_picker(self, payload_json: str) -> None:
        try:
            payload = json.loads(payload_json)
            absorbed_id = int(payload["absorbed_id"])
            search = payload.get("search")
            if search is not None:
                search = str(search)
        except (ValueError, TypeError, KeyError) as e:
            _log_invalid_payload("request_contacts_company_merge_picker", e)
            self.contacts_company_merge_picker_loaded.emit(_err(f"Неверные поля: {e}"))
            return

        async def run() -> str:
            async with self._session_factory() as session:
                rows = await companies_list.list_companies_with_counts(session, search=search)
            return _ok({
                "absorbed_id": absorbed_id,
                "search": search or "",
                "companies": [
                    _company_picker_row_to_dict(r) for r in rows
                    if r.company.id != absorbed_id
                ],
            })

        self._dispatch(self.contacts_company_merge_picker_loaded, run())

    @Slot(str)
    def contacts_create_company(self, payload_json: str) -> None:
        try:
            payload = json.loads(payload_json)
            fields = read_new_company_fields(payload)
            name = fields["name"]
        except (ValueError, TypeError) as e:
            _log_invalid_payload("contacts_create_company", e)
            self.contacts_company_action_done.emit(_err(f"Неверные поля: {e}"))
            return
        if not name:
            self.contacts_company_action_done.emit(
                _err("Название обязательно.", action="create_company")
            )
            return

        async def run() -> str:
            try:
                async with self._session_factory() as session:
                    co = await companies_card.create_company(session, **fields)
                    await session.commit()
            except IntegrityError:
                return _err(
                    f"Компания «{name}» уже существует.",
                    action="create_company",
                )
            except Exception as e:
                logger.exception("contacts_create_company failed")
                return _err(f"{type(e).__name__}: {e}", action="create_company")
            return _ok({"action": "create_company", "created_id": co.id})

        self._dispatch(self.contacts_company_action_done, run())

    @Slot(str)
    def contacts_update_company(self, payload_json: str) -> None:
        try:
            payload = json.loads(payload_json)
            company_id = int(payload["company_id"])
        except (ValueError, TypeError, KeyError) as e:
            _log_invalid_payload("contacts_update_company", e)
            self.contacts_company_action_done.emit(_err(f"Неверные поля: {e}"))
            return
        kwargs: dict = {}
        for key in ("name", "website", "notes"):
            if key in payload:
                kwargs[key] = payload[key]
        if "aliases" in payload:
            raw = payload["aliases"]
            if not isinstance(raw, (str, list)):
                self.contacts_company_action_done.emit(
                    _err("aliases должен быть list или строка через запятую.")
                )
                return
            kwargs["aliases"] = read_company_spellings(raw)
        if not kwargs:
            self.contacts_company_action_done.emit(
                _err("Нечего обновлять.", company_id=company_id)
            )
            return

        async def run() -> str:
            async with self._session_factory() as session:
                async with session.begin():
                    ok = await companies_card.update_company_fields(
                        session, company_id, **kwargs,
                    )
            if not ok:
                return _err(
                    "Компания не найдена или название пустое.",
                    company_id=company_id, action="update_company",
                )
            return _ok({
                "action": "update_company",
                "company_id": company_id,
                "fields": list(kwargs.keys()),
            })

        self._dispatch(self.contacts_company_action_done, run())

    @Slot(int)
    def contacts_delete_company(self, company_id: int) -> None:
        async def run() -> str:
            async with self._session_factory() as session:
                ok = await companies_card.delete_company(session, company_id)
                if not ok:
                    return _err(
                        "Компания не найдена.",
                        company_id=company_id, action="delete_company",
                    )
                await session.commit()
            return _ok({"action": "delete_company", "company_id": company_id})

        self._dispatch(self.contacts_company_action_done, run())

    @Slot(str)
    def contacts_merge_company(self, payload_json: str) -> None:
        try:
            payload = json.loads(payload_json)
            absorbed_id = int(payload["absorbed_id"])
            survivor_id = int(payload["survivor_id"])
        except (ValueError, TypeError, KeyError) as e:
            _log_invalid_payload("contacts_merge_company", e)
            self.contacts_company_action_done.emit(_err(f"Неверные поля: {e}"))
            return

        async def run() -> str:
            try:
                async with self._session_factory() as session:
                    async with session.begin():
                        await companies_card.merge_company(
                            session,
                            absorbed_id=absorbed_id,
                            survivor_id=survivor_id,
                        )
            except ValueError as e:
                return _err(str(e), absorbed_id=absorbed_id, action="merge_company")
            except Exception as e:
                logger.exception("contacts_merge_company failed")
                return _err(
                    f"{type(e).__name__}: {e}",
                    absorbed_id=absorbed_id, action="merge_company",
                )
            return _ok({
                "action": "merge_company",
                "absorbed_id": absorbed_id,
                "survivor_id": survivor_id,
            })

        self._dispatch(self.contacts_company_action_done, run())

    @Slot(int)
    def contacts_add_company_to_blacklist(self, company_id: int) -> None:
        """Insert / re-activate a kind="company" blacklist row for this
        company. Value is the company name. Idempotent.
        """
        async def run() -> str:
            async with self._session_factory() as session:
                co = await session.get(Company, company_id)
                if co is None:
                    return _err(
                        "Компания не найдена.",
                        company_id=company_id, action="blacklist",
                    )
                value = companies_card.company_blacklist_preferred_value(co)
                if value is None:
                    return _err(
                        "У компании нет имени.",
                        company_id=company_id, action="blacklist",
                    )
                _, outcome = await blacklist.create_blacklist(
                    session, kind="company", value=value,
                )
                await session.commit()
            self.contacts_lists_changed.emit()
            return _ok({
                "action": "blacklist",
                "company_id": company_id,
                "value": value,
                "existed": outcome != "created",
                "was_inactive": outcome == "reactivated",
            })

        self._dispatch(self.contacts_company_action_done, run())

    @Slot(int)
    def contacts_remove_company_from_blacklist(self, company_id: int) -> None:
        async def run() -> str:
            async with self._session_factory() as session:
                co = await session.get(Company, company_id)
                if co is None:
                    return _err(
                        "Компания не найдена.",
                        company_id=company_id, action="unblacklist",
                    )
                candidates = companies_card.company_blacklist_candidates(co)
                if not candidates:
                    return _err(
                        "У компании нет имени.",
                        company_id=company_id, action="unblacklist",
                    )
                updated = await blacklist.deactivate_blacklist_values(
                    session, "company", candidates,
                )
                await session.commit()
            self.contacts_lists_changed.emit()
            return _ok({
                "action": "unblacklist",
                "company_id": company_id,
                "updated": updated,
            })

        self._dispatch(self.contacts_company_action_done, run())
