"""Экран «Контакты / Чёрный список»: чем окно правит отсев."""

from __future__ import annotations

import json

from PySide6.QtCore import Signal, Slot

from backend.models import BLACKLIST_KINDS
from backend.repository import (
    blacklist as blacklist_repo,
    blacklist_candidates,
    channels as channels_repo,
)
from client.bridge.answer import _err, _ok
from client.bridge.payload import _log_invalid_payload
from client.bridge.refusals import NO_ENTRY
from client.form_payloads import read_toggle
from client.bridge.wire import _blacklist_row_to_dict


class BlacklistSlots:
    """Запись отсева: показать, завести, поправить, погасить, убрать.

    Подмешивающий обязан держать `_session_factory`, `_dispatch` и
    `_dispatch_action`, а сверх того — сигнал `contacts_lists_changed`,
    которым окно узнаёт, что списки надо перечитать целиком.
    """

    contacts_blacklist_list_loaded = Signal(str)
    contacts_blacklist_action_done = Signal(str)
    contacts_blacklist_candidates_loaded = Signal(str)

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
                        ok = await blacklist_repo.update_blacklist(
                            session, blacklist_id, **kwargs
                        )
            except blacklist_repo.BlacklistUpdateError as e:
                return _err(str(e), id=blacklist_id, action="update")
            if not ok:
                return _err(
                    NO_ENTRY,
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
                        row, outcome = await blacklist_repo.create_blacklist(
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
            except blacklist_repo.BlacklistUpdateError as e:
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
                    ok = await blacklist_repo.delete_blacklist(session, blacklist_id)
            if not ok:
                return _err(
                    NO_ENTRY,
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
            blacklist_id, active = read_toggle(payload, "id", "active")
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
                    ok = await blacklist_repo.set_blacklist_active(
                        session, blacklist_id, active
                    )
            if not ok:
                return _err(
                    NO_ENTRY,
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
                rows = await blacklist_repo.list_blacklist(session)
            return _ok({
                "items": [_blacklist_row_to_dict(r) for r in rows],
            })

        self._dispatch(self.contacts_blacklist_list_loaded, run())
