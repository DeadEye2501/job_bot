"""Привязка вакансии к человеку и к компании: подборщики и их правки."""

from __future__ import annotations

import json

from PySide6.QtCore import Signal, Slot
from sqlalchemy.exc import IntegrityError

from backend.models import Vacancy
from backend.payloads import text_or_none
from backend.repository import (
    companies_card,
    companies_list,
    hr_identify,
    hr_list,
    vacancies_card,
)
from client.bridge.answer import _err, _ok
from client.bridge.refusals import COMPANY_EXISTS, IDENTITY_REQUIRED, NAME_REQUIRED, NO_VACANCY
from client.bridge.payload import _log_invalid_payload
from client.bridge.wire import _company_picker_row_to_dict, _hr_picker_row_to_dict
from client.form_payloads import (
    hr_is_identified,
    read_new_company_fields,
    read_new_hr_fields,
)


class VacancyLinkSlots:
    """Кого и что окно привязывает к вакансии, и как оно их ищет.

    Подмешивающий обязан держать `_session_factory` и `_dispatch`, а сверх
    того — сигнал `vacancy_action_done` из `VacancyActionSlots`: привязка
    отвечает окну тем же сигналом, что и остальные действия над карточкой,
    потому что окно перерисовывает её одним обработчиком.
    """

    hr_picker_loaded = Signal(str)
    company_picker_loaded = Signal(str)

    @Slot(str)
    def request_hr_picker(self, payload_json: str) -> None:
        """Push the HR-picker payload for the «Связать с HR» modal.

        ``vacancy_id`` is echoed back as ``current_hr_id`` (the HR currently
        linked to that vacancy, NULL if unlinked) so the JS can mark the
        active row without a second round-trip. ``search`` is server-side
        casefold-filtered (Cyrillic-safe) — see ``list_hr_with_counts``.
        """
        try:
            payload = json.loads(payload_json)
            vacancy_id = int(payload["vacancy_id"])
            search = text_or_none(payload.get("search"))
        except (ValueError, TypeError, KeyError) as e:
            _log_invalid_payload("request_hr_picker", e)
            self.hr_picker_loaded.emit(_err(f"Неверные поля: {e}"))
            return

        async def run() -> str:
            async with self._session_factory() as session:
                rows, _ = await hr_list.list_hr_with_counts(session, search=search)
                v = await session.get(Vacancy, vacancy_id)
                if v is None:
                    return _err(NO_VACANCY, vacancy_id=vacancy_id)
                payload = {
                    "vacancy_id": vacancy_id,
                    "current_hr_id": v.hr_id,
                    "search": search or "",
                    "hrs": [_hr_picker_row_to_dict(r) for r in rows],
                }
            return _ok(payload)

        self._dispatch(self.hr_picker_loaded, run())

    @Slot(str)
    def request_company_picker(self, payload_json: str) -> None:
        """Push the Company-picker payload for the «Связать с компанией» modal."""
        try:
            payload = json.loads(payload_json)
            vacancy_id = int(payload["vacancy_id"])
            search = text_or_none(payload.get("search"))
        except (ValueError, TypeError, KeyError) as e:
            _log_invalid_payload("request_company_picker", e)
            self.company_picker_loaded.emit(_err(f"Неверные поля: {e}"))
            return

        async def run() -> str:
            async with self._session_factory() as session:
                rows, _ = await companies_list.list_companies_with_counts(
                    session, search=search
                )
                v = await session.get(Vacancy, vacancy_id)
                if v is None:
                    return _err(NO_VACANCY, vacancy_id=vacancy_id)
                payload = {
                    "vacancy_id": vacancy_id,
                    "current_company_id": v.company_id,
                    "search": search or "",
                    "companies": [_company_picker_row_to_dict(r) for r in rows],
                }
            return _ok(payload)

        self._dispatch(self.company_picker_loaded, run())

    @Slot(str)
    def link_vacancy_hr(self, payload_json: str) -> None:
        """Set / unset ``vacancy.hr_id`` from the HR-picker «Связать» button.

        ``hr_id`` may be null to unlink. Reuses ``vacancy_action_done`` with
        ``action="link_hr"`` so the existing toast/refresh flow lights up.
        """
        try:
            payload = json.loads(payload_json)
            vacancy_id = int(payload["vacancy_id"])
            raw = payload.get("hr_id")
            hr_id = int(raw) if raw is not None else None
        except (ValueError, TypeError, KeyError) as e:
            _log_invalid_payload("link_vacancy_hr", e)
            self.vacancy_action_done.emit(_err(f"Неверные поля: {e}"))
            return

        async def run() -> str:
            try:
                async with self._session_factory() as session:
                    async with session.begin():
                        ok = await vacancies_card.set_vacancy_hr(
                            session, vacancy_id, hr_id
                        )
            except ValueError as e:
                return _err(str(e), vacancy_id=vacancy_id, action="link_hr")
            if not ok:
                return _err(
                    NO_VACANCY,
                    vacancy_id=vacancy_id,
                    action="link_hr",
                )
            return _ok({
                "vacancy_id": vacancy_id,
                "hr_id": hr_id,
                "action": "link_hr",
            })

        self._dispatch(self.vacancy_action_done, run())

    @Slot(str)
    def link_vacancy_company(self, payload_json: str) -> None:
        """Set / unset ``vacancy.company_id`` from the Company-picker «Связать»."""
        try:
            payload = json.loads(payload_json)
            vacancy_id = int(payload["vacancy_id"])
            raw = payload.get("company_id")
            company_id = int(raw) if raw is not None else None
        except (ValueError, TypeError, KeyError) as e:
            _log_invalid_payload("link_vacancy_company", e)
            self.vacancy_action_done.emit(_err(f"Неверные поля: {e}"))
            return

        async def run() -> str:
            try:
                async with self._session_factory() as session:
                    async with session.begin():
                        ok = await vacancies_card.set_vacancy_company(
                            session, vacancy_id, company_id
                        )
            except ValueError as e:
                return _err(str(e), vacancy_id=vacancy_id, action="link_company")
            if not ok:
                return _err(
                    NO_VACANCY,
                    vacancy_id=vacancy_id,
                    action="link_company",
                )
            return _ok({
                "vacancy_id": vacancy_id,
                "company_id": company_id,
                "action": "link_company",
            })

        self._dispatch(self.vacancy_action_done, run())

    @Slot(str)
    def picker_create_hr(self, payload_json: str) -> None:
        """Insert a new HR from the picker's inline-create form.

        On success, re-emits the picker list so the modal can refresh in
        place. ``created_id`` lets JS pre-select the new row; the actual
        ``vacancy.hr_id`` link still requires the user to click «Связать».
        """
        try:
            payload = json.loads(payload_json)
            vacancy_id = int(payload["vacancy_id"])
            fields = read_new_hr_fields(payload)
            search = text_or_none(payload.get("search"))
        except (ValueError, TypeError, KeyError) as e:
            _log_invalid_payload("picker_create_hr", e)
            self.hr_picker_loaded.emit(_err(f"Неверные поля: {e}"))
            return

        if not hr_is_identified(fields):
            self.hr_picker_loaded.emit(
                _err(IDENTITY_REQUIRED, vacancy_id=vacancy_id)
            )
            return

        async def run() -> str:
            async with self._session_factory() as session:
                async with session.begin():
                    new_hr = await hr_identify.create_hr(session, **fields)
                    created_id = new_hr.id
                rows, _ = await hr_list.list_hr_with_counts(session, search=search)
                v = await session.get(Vacancy, vacancy_id)
                current_hr_id = v.hr_id if v is not None else None
                payload = {
                    "vacancy_id": vacancy_id,
                    "current_hr_id": current_hr_id,
                    "search": search or "",
                    "hrs": [_hr_picker_row_to_dict(r) for r in rows],
                    "created_id": created_id,
                }
            return _ok(payload)

        self._dispatch(self.hr_picker_loaded, run())

    @Slot(str)
    def picker_create_company(self, payload_json: str) -> None:
        """Insert a new Company from the picker's inline-create form.

        Catches ``IntegrityError`` from the unique-name constraint and turns
        it into a user-facing message instead of bubbling up a SQL error.
        """
        try:
            payload = json.loads(payload_json)
            vacancy_id = int(payload["vacancy_id"])
            fields = read_new_company_fields(payload)
            name = fields["name"]
            search = text_or_none(payload.get("search"))
        except (ValueError, TypeError, KeyError) as e:
            _log_invalid_payload("picker_create_company", e)
            self.company_picker_loaded.emit(_err(f"Неверные поля: {e}"))
            return

        if not name:
            self.company_picker_loaded.emit(
                _err(NAME_REQUIRED, vacancy_id=vacancy_id)
            )
            return

        async def run() -> str:
            try:
                async with self._session_factory() as session:
                    async with session.begin():
                        new_co = await companies_card.create_company(
                            session, **fields
                        )
                        created_id = new_co.id
                    rows, _ = await companies_list.list_companies_with_counts(
                        session, search=search
                    )
                    v = await session.get(Vacancy, vacancy_id)
                    current_company_id = v.company_id if v is not None else None
                    payload = {
                        "vacancy_id": vacancy_id,
                        "current_company_id": current_company_id,
                        "search": search or "",
                        "companies": [_company_picker_row_to_dict(r) for r in rows],
                        "created_id": created_id,
                    }
            except IntegrityError:
                return _err(
                    COMPANY_EXISTS.format(name=name),
                    vacancy_id=vacancy_id,
                )
            except ValueError as e:
                return _err(str(e), vacancy_id=vacancy_id)
            return _ok(payload)

        self._dispatch(self.company_picker_loaded, run())
