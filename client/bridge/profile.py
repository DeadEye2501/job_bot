"""Анкета соискателя: сведения о себе, навыки и места работы."""

from __future__ import annotations

import json

from PySide6.QtCore import Signal, Slot

from backend.domain.taxonomy import GRADES, WORK_FORMATS
from backend.payloads import text_or_none as _none_if_empty
from backend.repository import profile as profile_repo
from client.bridge.answer import _err, _ok
from client.bridge.choices import _filter_languages, _filter_set
from client.bridge.cv_file import _stat_cv
from client.bridge.payload import _log_invalid_payload
from client.bridge.refusals import PROFILE_FIRST
from client.bridge.wire import _exp_to_dict, _profile_to_dict, _skill_to_dict


class ProfileSlots:
    """Экран «Профиль» целиком: чем окно спрашивает анкету и чем правит.

    Подмешивающий обязан держать `_rs`, `_session_factory` и `_dispatch`.

    SECURITY: `request_profile` отдаёт во фронт PII как есть — почту, телефон,
    ник в Telegram, ссылку на GitHub, город, образование и абсолютный путь к
    резюме. Это осознанно: приложение однопользовательское, а разметка живёт во
    встроенном окне, не в сети.
    """

    profile_changed = Signal(str)
    profile_save_done = Signal(str)
    skills_changed = Signal(str)
    skills_save_done = Signal(str)
    experience_changed = Signal(str)
    experience_save_done = Signal(str)

    @Slot()
    def request_profile(self) -> None:
        """Push the current Profile + CV path to JS."""
        async def run() -> str:
            async with self._session_factory() as session:
                profile = await profile_repo.get_profile(session)
                languages = (
                    await profile_repo.list_profile_languages(session)
                    if profile is not None
                    else []
                )
            cv_path = self._rs.cv_path
            cv_meta = _stat_cv(cv_path)
            return _ok(
                {
                    "profile": _profile_to_dict(profile, languages),
                    "cv_path": cv_path,
                    "cv_meta": cv_meta,
                }
            )

        self._dispatch(self.profile_changed, run())

    @Slot(str)
    def save_profile(self, payload_json: str) -> None:
        try:
            payload = json.loads(payload_json)
            fields = {
                "first_name": str(payload.get("first_name") or "").strip(),
                "last_name": str(payload.get("last_name") or "").strip(),
                "title": str(payload.get("title") or "").strip(),
                "email": str(payload.get("email") or "").strip(),
                "phone": _none_if_empty(payload.get("phone")),
                "location": _none_if_empty(payload.get("location")),
                "telegram_username": _none_if_empty(payload.get("telegram_username")),
                "github_url": _none_if_empty(payload.get("github_url")),
                "education": _none_if_empty(payload.get("education")),
                "free_preferences": _none_if_empty(payload.get("free_preferences")),
                "grades": _filter_set(payload.get("grades"), GRADES),
                "work_format": _filter_set(
                    payload.get("work_format"), WORK_FORMATS
                ),
            }
            languages = _filter_languages(payload.get("languages"))
        except (ValueError, TypeError) as e:
            _log_invalid_payload("save_profile", e)
            self.profile_save_done.emit(_err(f"Неверные поля: {e}"))
            return

        for required in ("first_name", "last_name", "title", "email"):
            if not fields[required]:
                self.profile_save_done.emit(
                    _err(f"Поле '{required}' обязательно.")
                )
                return

        async def run() -> str:
            async with self._session_factory() as session:
                async with session.begin():
                    profile = await profile_repo.upsert_profile(
                        session, **fields
                    )
                    await profile_repo.replace_profile_languages(
                        session, profile.id, languages
                    )
            return _ok()

        self._dispatch(self.profile_save_done, run())

    @Slot()
    def request_skills(self) -> None:
        async def run() -> str:
            async with self._session_factory() as session:
                rows = await profile_repo.list_skills(session)
            return _ok({"skills": [_skill_to_dict(s) for s in rows]})

        self._dispatch(self.skills_changed, run())

    def _save_rows(self, payload_json: str, key: str, signal: Signal, saving):
        """Прочитать перечень строк анкеты и отдать его сохранению.

        Навыки и места работы приходят одной формой — списком объектов под
        своим ключом, — и различаются только этим ключом, объявлением записи
        и сигналом ответа.

        Отказ «сначала сохраните профайл» стоит внутри сделки нарочно: строки
        анкеты цепляются к её номеру, и без анкеты цеплять их не к чему.
        """
        try:
            payload = json.loads(payload_json)
            rows = payload.get(key) or []
            if not isinstance(rows, list):
                raise ValueError(f"{key} must be a list")
        except (AttributeError, ValueError, TypeError) as e:
            _log_invalid_payload(f"save_{key}", e)
            signal.emit(_err(f"Неверные поля: {e}"))
            return

        async def run() -> str:
            try:
                async with self._session_factory() as session:
                    async with session.begin():
                        profile = await profile_repo.get_profile(session)
                        if profile is None:
                            return _err(PROFILE_FIRST)
                        await saving(session, rows, profile.id)
            except profile_repo.SaveExperienceError as e:
                return _err(str(e))
            return _ok()

        self._dispatch(signal, run())

    @Slot(str)
    def save_skills(self, payload_json: str) -> None:
        self._save_rows(
            payload_json, "skills", self.skills_save_done, profile_repo.save_skills
        )

    @Slot()
    def request_experience(self) -> None:
        async def run() -> str:
            async with self._session_factory() as session:
                exps = await profile_repo.list_experience(session)
                skills = await profile_repo.list_skills(session)
            return _ok(
                {
                    "experience": [_exp_to_dict(e) for e in exps],
                    "skills_index": [_skill_to_dict(s) for s in skills],
                }
            )

        self._dispatch(self.experience_changed, run())

    @Slot(str)
    def save_experience(self, payload_json: str) -> None:
        self._save_rows(
            payload_json,
            "experience",
            self.experience_save_done,
            profile_repo.save_experience,
        )
