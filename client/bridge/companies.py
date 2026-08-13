"""Компания как запись в контактах: найти, показать, поправить, убрать."""

from __future__ import annotations

import json
import logging

from PySide6.QtCore import Signal, Slot
from sqlalchemy.exc import IntegrityError

from backend.models import Company
from backend.payloads import int_or_none, text_or_none
from backend.repository import (
    blacklist,
    companies_card,
    companies_list,
    hr_list,
    vacancies_mini,
)
from client.bridge.answer import _err, _ok
from client.bridge.media import _avatar_data_url
from client.bridge.page import read_page
from client.bridge.payload import _log_invalid_payload
from client.bridge.wire import _company_picker_row_to_dict, _iso
from client.form_payloads import read_company_spellings, read_new_company_fields


logger = logging.getLogger(__name__)


class CompanySlots:
    """Компания как запись в контактах: найти, показать, поправить, убрать.

    Подмешивающий обязан держать `_session_factory` и `_dispatch`, а сверх того
    — сигнал `contacts_lists_changed`, которым окно узнаёт, что списки надо
    перечитать целиком.
    """

    contacts_company_list_loaded = Signal(str)
    contacts_company_detail_loaded = Signal(str)
    contacts_company_vacancies_loaded = Signal(str)
    contacts_company_hrs_loaded = Signal(str)
    contacts_company_merge_picker_loaded = Signal(str)
    contacts_company_action_done = Signal(str)

    @Slot(str)
    def request_contacts_company_list(self, payload_json: str) -> None:
        """Page of Companies for the Contacts/Companies pane.

        Payload mirrors `request_contacts_hr_list` — search + epoch +
        offset/limit + replace/append/refresh mode. Backend echoes epoch
        so JS can drop stale responses when search/scroll race.
        """
        try:
            payload = json.loads(payload_json) if payload_json else {}
            search = text_or_none(payload.get("search"))
            page = read_page(payload, default_limit=50)
        except (ValueError, TypeError) as e:
            _log_invalid_payload("request_contacts_company_list", e)
            self.contacts_company_list_loaded.emit(_err(f"Неверные поля: {e}"))
            return

        async def run() -> str:
            async with self._session_factory() as session:
                rows = await companies_list.list_companies_with_counts(
                    session, search=search, limit=page.limit, offset=page.offset,
                )
            has_more = (page.limit is not None) and (len(rows) == page.limit)
            return _ok({
                "search": search or "",
                "companies": [_company_picker_row_to_dict(r) for r in rows],
                "has_more": has_more,
                "mode": page.mode,
                "offset": page.offset,
                "epoch": page.epoch,
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
            epoch = int_or_none(payload.get("epoch"))
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
    def request_contacts_company_merge_picker(self, payload_json: str) -> None:
        try:
            payload = json.loads(payload_json)
            absorbed_id = int(payload["absorbed_id"])
            search = text_or_none(payload.get("search"))
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
