"""Экран «Вакансии»: список, карточка и правки в них."""

from __future__ import annotations

import json
import logging

from PySide6.QtCore import Signal, Slot

from backend.domain.scoring import build_skill_lookup
from backend.models import Vacancy, VacancyStatus, VacancyStatusHistory
from backend.repository import (
    profile as profile_repo,
    vacancies_card,
    vacancies_life,
    vacancies_list,
)
from client.bridge.answer import _err, _ok
from client.bridge.page import read_page
from client.bridge.payload import _log_invalid_payload
from client.bridge.vacancy_filter import read_vacancy_filter
from client.bridge.wire import _vacancy_detail_to_dict, _vacancy_list_row_to_dict


logger = logging.getLogger(__name__)


class VacancySlots:
    """Вакансия на своём экране: как её показывают и как её правят.

    Подмешивающий обязан держать `_rs`, `_session_factory` и `_dispatch`.
    """

    vacancies_changed = Signal(str)
    vacancy_detail_changed = Signal(str)
    vacancy_notes_saved = Signal(str)
    vacancy_status_saved = Signal(str)
    vacancy_history_explanation_saved = Signal(str)

    @Slot(str)
    def request_vacancies(self, payload_json: str = "") -> None:
        """Push the vacancy list to JS, applying sort + search server-side.

        Форма строки — `wire._vacancy_list_row_to_dict`. Каждый пункт стека
        помечен ``matched``, если он есть в навыках и псевдонимах анкеты: так
        окно подсвечивает нужные чипы, не спрашивая навыки отдельно.

        Нагрузка — объект JSON с полями отбора; пустая или негодная сводится к
        умолчаниям `VacancyFilter`. Списки для выпадающих меню фильтра берутся
        мимо самого фильтра — иначе любой отбор сжимал бы их до того, что
        уцелело в выдаче.
        """
        try:
            payload = json.loads(payload_json) if payload_json else {}
        except (TypeError, ValueError):
            payload = {}
        page = read_page(payload)
        filters = read_vacancy_filter(payload, page)

        async def run() -> str:
            async with self._session_factory() as session:
                rows = await vacancies_list.list_vacancies(session, filters)
                skills = await profile_repo.list_skills(session)
                activity_by_id = await vacancies_list.list_vacancy_last_activity(
                    session, [v.id for v in rows]
                )
                # Filter-popover dropdown sources are intentionally fetched
                # independent of the active filters — otherwise applying any
                # filter would shrink the channels/companies dropdowns to
                # whatever's still in the result set.
                filter_options = await vacancies_list.list_vacancy_filter_options(session)
            matched_set = build_skill_lookup(skills)
            has_more = (page.limit is not None) and (len(rows) == page.limit)
            return _ok({
                "vacancies": [
                    _vacancy_list_row_to_dict(v, matched_set, activity_by_id)
                    for v in rows
                ],
                "filter_options": filter_options,
                "has_more": has_more,
                "mode": page.mode,
                "offset": page.offset,
                "epoch": page.epoch,
                "score_threshold": self._rs.scoring_threshold,
            })

        self._dispatch(self.vacancies_changed, run())

    @Slot(int)
    def request_vacancy_detail(self, vacancy_id: int) -> None:
        """Push the detail-pane payload for one vacancy.

        Отдаётся вся карточка целиком — описание, стек, контакты, история
        статусов, события, — а окно рисует из неё то, что показывает сейчас.
        Так карточка растёт без правок моста.
        """
        async def run() -> str:
            async with self._session_factory() as session:
                detail = await vacancies_card.get_vacancy_detail(session, vacancy_id)
                skills = await profile_repo.list_skills(session)
            if detail is None:
                logger.warning("vacancy_id=%d not found on detail load", vacancy_id)
                return _err("Вакансия не найдена.", id=vacancy_id)
            matched_set = build_skill_lookup(skills)
            return _ok({
                "vacancy": _vacancy_detail_to_dict(
                    detail, matched_set, self._rs.scoring_threshold,
                ),
            })

        self._dispatch(self.vacancy_detail_changed, run())

    @Slot(str)
    def update_vacancy_notes(self, payload_json: str) -> None:
        """Persist a new ``notes`` value for the given vacancy.

        Emits ``vacancy_notes_saved`` with ``{ok, vacancy_id, notes}`` on
        success (UI flashes the textarea border and adopts ``notes`` as the
        save-baseline) or ``{ok: false, error}`` on failure.
        ``vacancies_card.update_vacancy_notes`` normalizes empty/whitespace-only
        ``notes`` to ``NULL`` — we echo back the post-normalization value so
        the JS baseline matches what's actually in the DB.
        """
        try:
            payload = json.loads(payload_json)
            vacancy_id = int(payload["vacancy_id"])
            notes = payload.get("notes")
            if notes is not None:
                notes = str(notes)
        except (ValueError, TypeError, KeyError) as e:
            _log_invalid_payload("update_vacancy_notes", e)
            self.vacancy_notes_saved.emit(_err(f"Неверные поля: {e}"))
            return

        async def run() -> str:
            async with self._session_factory() as session:
                async with session.begin():
                    ok = await vacancies_card.update_vacancy_notes(
                        session, vacancy_id, notes
                    )
                    persisted: str | None = None
                    if ok:
                        # Re-read the post-normalization value (NULL on
                        # whitespace-only input) so the client adopts the
                        # exact DB state as its save-baseline. Without this,
                        # any keystrokes the user typed between sending and
                        # receiving the reply would be silently dropped on
                        # the next debounce.
                        v = await session.get(Vacancy, vacancy_id)
                        if v is not None:
                            persisted = v.notes
            if not ok:
                return _err("Вакансия не найдена.", vacancy_id=vacancy_id)
            return _ok({"vacancy_id": vacancy_id, "notes": persisted})

        self._dispatch(self.vacancy_notes_saved, run())

    @Slot(str)
    def update_status_history_explanation(self, payload_json: str) -> None:
        """Edit the comment on one VacancyStatusHistory row.

        Payload: ``{vacancy_id, history_id, explanation}``. Empty/whitespace
        explanation нормализуется в NULL на бэке. Эмитит на отдельный
        ``vacancy_history_explanation_saved`` (а НЕ на ``vacancy_status_saved``),
        потому что обновление коммента не требует re-fetch detail'а — UI
        обновляет одну строку on-the-fly без потери фокуса в textarea.
        """
        try:
            payload = json.loads(payload_json)
            history_id = int(payload["history_id"])
            vacancy_id = int(payload["vacancy_id"])
            explanation = payload.get("explanation")
            if explanation is not None:
                explanation = str(explanation)
        except (ValueError, TypeError, KeyError) as e:
            _log_invalid_payload("update_status_history_explanation", e)
            self.vacancy_history_explanation_saved.emit(_err(f"Неверные поля: {e}"))
            return

        async def run() -> str:
            saved: str | None = None
            async with self._session_factory() as session:
                async with session.begin():
                    ok = await vacancies_life.update_status_history_explanation(
                        session, history_id, explanation,
                    )
                    if ok:
                        # Re-read post-normalization (NULL для empty/whitespace),
                        # чтобы UI-baseline совпадал с тем, что в DB.
                        row = await session.get(VacancyStatusHistory, history_id)
                        if row is not None:
                            saved = row.explanation
            if not ok:
                logger.warning(
                    "history_id=%d not found (vacancy=%d)",
                    history_id,
                    vacancy_id,
                )
                return _err(
                    "Запись истории не найдена.",
                    history_id=history_id,
                    vacancy_id=vacancy_id,
                )
            return _ok({
                "vacancy_id": vacancy_id,
                "history_id": history_id,
                "explanation": saved,
            })

        self._dispatch(self.vacancy_history_explanation_saved, run())

    @Slot(str)
    def change_vacancy_status(self, payload_json: str) -> None:
        """Insert a manual status-history row and optionally mutate status.

        Payload: ``{vacancy_id, status, explanation?}`` where ``status`` is
        the enum VALUE string (``"New"``, ``"In Progress"``, ...), not a CSS
        class. Emits ``vacancy_status_saved`` with ``{ok, vacancy_id}`` on
        success or ``{ok:false, error}`` on failure.
        """
        try:
            payload = json.loads(payload_json)
            vacancy_id = int(payload["vacancy_id"])
            status_raw = str(payload["status"]).strip()
            explanation = payload.get("explanation")
            if explanation is not None:
                explanation = str(explanation)
            new_status = next(
                s for s in VacancyStatus if s.value == status_raw
            )
        except StopIteration:
            self.vacancy_status_saved.emit(
                _err("Неверный статус.", vacancy_id=payload.get("vacancy_id"))
            )
            return
        except (ValueError, TypeError, KeyError) as e:
            _log_invalid_payload("change_vacancy_status", e)
            self.vacancy_status_saved.emit(_err(f"Неверные поля: {e}"))
            return

        async def run() -> str:
            async with self._session_factory() as session:
                async with session.begin():
                    row = await vacancies_life.change_vacancy_status(
                        session,
                        vacancy_id=vacancy_id,
                        new_status=new_status,
                        explanation=explanation,
                    )
            # repository returns None both for "vacancy missing" and for a true
            # no-op (same status + empty explanation). Distinguish explicitly.
            if row is None:
                async with self._session_factory() as session:
                    v = await session.get(Vacancy, vacancy_id)
                if v is None:
                    return _err("Вакансия не найдена.", vacancy_id=vacancy_id)
            return _ok({"vacancy_id": vacancy_id})

        self._dispatch(self.vacancy_status_saved, run())
