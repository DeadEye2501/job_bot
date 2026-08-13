"""Экран «Контакты / HR»: список людей, их карточка и правки в ней."""

from __future__ import annotations

import json
import logging

from PySide6.QtCore import Signal, Slot

from backend.models import HR
from backend.repository import (
    blacklist,
    hr_card,
    hr_identify,
    hr_list,
    vacancies_mini,
)
from client.bridge.answer import _err, _ok
from client.bridge.media import _avatar_data_url
from client.bridge.payload import _log_invalid_payload
from client.bridge.wire import _hr_picker_row_to_dict, _iso
from client.form_payloads import hr_is_identified, read_new_hr_fields


logger = logging.getLogger(__name__)


class HrSlots:
    """Человек как запись в контактах: найти, показать, поправить, убрать.

    Подмешивающий обязан держать `_session_factory` и `_dispatch`, а сверх того
    — сигнал `contacts_lists_changed`, которым окно узнаёт, что списки надо
    перечитать целиком, и `_kick_unread` из `WindowStateSlots`: правка чёрного
    списка меняет счётчик непрочитанного.
    """

    contacts_hr_list_loaded = Signal(str)
    contacts_hr_detail_loaded = Signal(str)
    contacts_hr_action_done = Signal(str)
    contacts_hr_vacancies_loaded = Signal(str)
    contacts_hr_merge_picker_loaded = Signal(str)

    @Slot(str)
    def request_contacts_hr_list(self, payload_json: str) -> None:
        """Push the HR-list payload for Contacts / HR (05).

        Same backing query as the picker (``list_hr_with_counts``) but with
        infinite-scroll: ``mode``/``offset``/``limit`` mirror the vacancies
        list. ``epoch`` is echoed back so the JS can drop stale responses
        when filters/search/sort change mid-flight.
        """
        try:
            payload = json.loads(payload_json) if payload_json else {}
            search = payload.get("search")
            if search is not None:
                search = str(search)

            def _int(key: str) -> int | None:
                raw = payload.get(key)
                if raw in (None, ""):
                    return None
                try:
                    return int(raw)
                except (TypeError, ValueError):
                    return None

            limit = _int("limit")
            # Sanity cap — JS uses 30 / 200, but a malformed payload could
            # request millions; the post-filter slice walks all rows in
            # Python, so we want a hard ceiling at the boundary.
            if limit is not None and limit > 200:
                limit = 200
            offset = _int("offset") or 0
            mode_raw = str(payload.get("mode") or "replace")
            mode = (
                mode_raw if mode_raw in {"replace", "append", "refresh"}
                else "replace"
            )
            epoch = _int("epoch")
        except (ValueError, TypeError) as e:
            _log_invalid_payload("request_contacts_hr_list", e)
            self.contacts_hr_list_loaded.emit(_err(f"Неверные поля: {e}"))
            return

        async def run() -> str:
            async with self._session_factory() as session:
                rows = await hr_list.list_hr_with_counts(
                    session,
                    search=search,
                    limit=limit,
                    offset=offset,
                    sort_by="last_activity",
                )
            has_more = (limit is not None) and (len(rows) == limit)
            return _ok({
                "search": search or "",
                "hrs": [_hr_picker_row_to_dict(r) for r in rows],
                "has_more": has_more,
                "mode": mode,
                "offset": offset,
                "epoch": epoch,
            })

        self._dispatch(self.contacts_hr_list_loaded, run())
    @Slot(str)
    def request_contacts_hr_vacancies(self, payload_json: str) -> None:
        """Push the vacancy mini-list for the HR detail pane.

        Payload: ``{hr_id, epoch}``. ``hr_id`` фильтрует ответ от другого
        выбранного HR, ``epoch`` — от race'а двух подряд request'ов на ОДНОГО
        и того же HR (например, рапид-флип статуса вакансии). Оба эхо'ятся
        обратно в ответе, JS дропает stale.
        """
        try:
            payload = json.loads(payload_json)
            hr_id = int(payload["hr_id"])
            epoch = payload.get("epoch")
        except (ValueError, TypeError, KeyError) as e:
            _log_invalid_payload("request_contacts_hr_vacancies", e)
            self.contacts_hr_vacancies_loaded.emit(_err(f"Неверные поля: {e}"))
            return

        async def run() -> str:
            async with self._session_factory() as session:
                rows = await vacancies_mini.list_vacancies_for_hr(session, hr_id)
            return _ok({
                "hr_id": hr_id,
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

        self._dispatch(self.contacts_hr_vacancies_loaded, run())
    @Slot(int)
    def request_contacts_hr_detail(self, hr_id: int) -> None:
        """Push the HR-detail payload for the Contacts / HR pane (05).

        Returns ``hr_id`` in the payload so JS can drop stale responses
        when the user clicks a different row mid-flight.
        """
        async def run() -> str:
            async with self._session_factory() as session:
                detail = await hr_card.get_hr_detail(session, hr_id)
            if detail is None:
                return _err("HR не найден.", hr_id=hr_id)
            return _ok({
                "hr_id": detail.hr.id,
                "name": detail.hr.name,
                "telegram_username": detail.hr.telegram_username,
                "telegram_user_id": detail.hr.telegram_user_id,
                "notes": detail.hr.notes,
                "vacancy_count": detail.vacancy_count,
                "last_company_id": detail.last_company_id,
                "last_company_name": detail.last_company_name,
                "unread_count": detail.unread_count,
                "blacklist_value": detail.blacklist_value,
                "avatar": _avatar_data_url(detail.hr.avatar),
            })

        self._dispatch(self.contacts_hr_detail_loaded, run())
    @Slot(str)
    def request_contacts_hr_merge_picker(self, payload_json: str) -> None:
        """List of HRs eligible to absorb the current HR. Same row shape as
        the vacancies HR-picker, minus the absorbed HR itself.
        """
        try:
            payload = json.loads(payload_json)
            absorbed_id = int(payload["absorbed_id"])
            search = payload.get("search")
            if search is not None:
                search = str(search)
        except (ValueError, TypeError, KeyError) as e:
            _log_invalid_payload("request_contacts_hr_merge_picker", e)
            self.contacts_hr_merge_picker_loaded.emit(_err(f"Неверные поля: {e}"))
            return

        async def run() -> str:
            async with self._session_factory() as session:
                rows = await hr_list.list_hr_with_counts(session, search=search)
            return _ok({
                "absorbed_id": absorbed_id,
                "search": search or "",
                "hrs": [
                    _hr_picker_row_to_dict(r) for r in rows
                    if r.hr.id != absorbed_id
                ],
            })

        self._dispatch(self.contacts_hr_merge_picker_loaded, run())
    @Slot(str)
    def contacts_merge_hr(self, payload_json: str) -> None:
        """Merge ``absorbed`` HR into ``survivor``: vacancies + messages get
        repointed, absorbed row is deleted. Backed by ``hr_card.merge_hr``.
        """
        try:
            payload = json.loads(payload_json)
            absorbed_id = int(payload["absorbed_id"])
            survivor_id = int(payload["survivor_id"])
        except (ValueError, TypeError, KeyError) as e:
            _log_invalid_payload("contacts_merge_hr", e)
            self.contacts_hr_action_done.emit(_err(f"Неверные поля: {e}"))
            return

        async def run() -> str:
            try:
                async with self._session_factory() as session:
                    async with session.begin():
                        await hr_card.merge_hr(
                            session,
                            absorbed_id=absorbed_id,
                            survivor_id=survivor_id,
                        )
            except ValueError as e:
                return _err(str(e), absorbed_id=absorbed_id, action="merge_hr")
            except Exception as e:
                logger.exception("contacts_merge_hr failed")
                return _err(
                    f"{type(e).__name__}: {e}",
                    absorbed_id=absorbed_id,
                    action="merge_hr",
                )
            self._kick_unread()
            return _ok({
                "action": "merge_hr",
                "absorbed_id": absorbed_id,
                "survivor_id": survivor_id,
            })

        self._dispatch(self.contacts_hr_action_done, run())
    @Slot(int)
    def contacts_delete_hr(self, hr_id: int) -> None:
        """Cascade-delete the HR row via ``hr_card.delete_hr``."""
        async def run() -> str:
            async with self._session_factory() as session:
                ok = await hr_card.delete_hr(session, hr_id)
                if not ok:
                    return _err("HR не найден.", hr_id=hr_id, action="delete_hr")
                await session.commit()
            self._kick_unread()
            return _ok({"action": "delete_hr", "hr_id": hr_id})

        self._dispatch(self.contacts_hr_action_done, run())
    @Slot(int)
    def contacts_remove_hr_from_blacklist(self, hr_id: int) -> None:
        """Deactivate any kind="hr" blacklist row matching this HR.

        Sets ``active=False`` rather than deleting — the blacklist screen
        keeps inactive rows visible with the toggle off, which is the
        expected UX for a «убрать из blacklist» from this screen.
        """
        async def run() -> str:
            async with self._session_factory() as session:
                hr = await session.get(HR, hr_id)
                if hr is None:
                    return _err("HR не найден.", hr_id=hr_id, action="unblacklist")
                candidates = hr_card.hr_blacklist_candidates(hr)
                if not candidates:
                    return _err(
                        "У HR нет ни @username, ни telegram_user_id.",
                        hr_id=hr_id, action="unblacklist",
                    )
                updated = await blacklist.deactivate_blacklist_values(
                    session, "hr", candidates,
                )
                await session.commit()
            self.contacts_lists_changed.emit()
            return _ok({
                "action": "unblacklist",
                "hr_id": hr_id,
                "updated": updated,
            })

        self._dispatch(self.contacts_hr_action_done, run())
    @Slot(int)
    def contacts_add_hr_to_blacklist(self, hr_id: int) -> None:
        """Insert a kind="hr" row into the blacklist for this HR.

        Value is ``@{username}`` if the HR has one, else ``user_id:{id}``.
        Idempotent: if a matching row already exists it is re-activated;
        if active already, no-op (returns ok with ``existed=True``).
        Reason left NULL — the blacklist screen lets the user fill it later.
        Does NOT delete the HR — that's a separate action.
        """
        async def run() -> str:
            async with self._session_factory() as session:
                hr = await session.get(HR, hr_id)
                if hr is None:
                    return _err("HR не найден.", hr_id=hr_id, action="blacklist")
                value = hr_card.hr_blacklist_preferred_value(hr)
                if value is None:
                    return _err(
                        "У HR нет ни @username, ни telegram_user_id.",
                        hr_id=hr_id, action="blacklist",
                    )
                _, outcome = await blacklist.create_blacklist(
                    session, kind="hr", value=value,
                )
                await session.commit()
            self.contacts_lists_changed.emit()
            return _ok({
                "action": "blacklist",
                "hr_id": hr_id,
                "value": value,
                "existed": outcome != "created",
                "was_inactive": outcome == "reactivated",
            })

        self._dispatch(self.contacts_hr_action_done, run())
    @Slot(str)
    def contacts_update_hr(self, payload_json: str) -> None:
        """Patch one or more HR columns from inline form fields (slice 3+).

        Payload shape: ``{"hr_id": int, "name"?: str, "telegram_username"?:
        str, "notes"?: str}``. Missing keys mean «leave unchanged» (sentinel
        on the repo side). Empty strings collapse to NULL.

        Re-emits the contacts list so the row's name/username refresh, and
        the detail payload so the head + form pick up canonicalised values
        (e.g. stripped «@»).
        """
        try:
            payload = json.loads(payload_json)
            hr_id = int(payload["hr_id"])
        except (ValueError, TypeError, KeyError) as e:
            _log_invalid_payload("contacts_update_hr", e)
            self.contacts_hr_action_done.emit(_err(f"Неверные поля: {e}"))
            return

        # Только присланные поля: отсутствие ключа значит «не трогать».
        kwargs = {
            key: payload[key]
            for key in ("name", "telegram_username", "notes")
            if key in payload
        }
        if not kwargs:
            self.contacts_hr_action_done.emit(
                _err("Нечего обновлять.", hr_id=hr_id)
            )
            return

        async def run() -> str:
            try:
                async with self._session_factory() as session:
                    async with session.begin():
                        ok = await hr_card.update_hr_fields(session, hr_id, **kwargs)
            except ValueError as e:  # негодный ник — ответ формы, а не сбой
                return _err(f"Неверные поля: {e}", hr_id=hr_id, action="update_hr")
            if not ok:
                return _err("HR не найден.", hr_id=hr_id, action="update_hr")
            return _ok({
                "action": "update_hr",
                "hr_id": hr_id,
                "fields": list(kwargs.keys()),
            })

        self._dispatch(self.contacts_hr_action_done, run())
    @Slot(str)
    def contacts_create_hr(self, payload_json: str) -> None:
        """Insert a new HR from the «Добавить HR» modal in Contacts / HR.

        On success returns ``created_id`` so JS can pre-select the new row,
        and the caller is expected to re-issue ``request_contacts_hr_list``
        to refresh.
        """
        try:
            payload = json.loads(payload_json)
            fields = read_new_hr_fields(payload)
        except (ValueError, TypeError, KeyError) as e:
            _log_invalid_payload("contacts_create_hr", e)
            self.contacts_hr_action_done.emit(_err(f"Неверные поля: {e}"))
            return

        if not hr_is_identified(fields):
            self.contacts_hr_action_done.emit(
                _err("Укажите хотя бы имя или @username.")
            )
            return

        async def run() -> str:
            async with self._session_factory() as session:
                async with session.begin():
                    new_hr = await hr_identify.create_hr(session, **fields)
                    created_id = new_hr.id
            return _ok({"action": "create_hr", "created_id": created_id})

        self._dispatch(self.contacts_hr_action_done, run())
