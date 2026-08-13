"""Анкета соискателя: сведения о себе, навыки и места работы."""

from __future__ import annotations

from backend.domain.taxonomy import GRADES, WORK_FORMATS
from backend.payloads import text_or_none as _none_if_empty
from backend.repository import profile as profile_repo
from client.bridge.answer import Denied, bad_fields, denied, reply
from client.bridge.choices import _filter_languages, _filter_set
from client.bridge.cv import Cv
from client.bridge.cv_file import _stat_cv
from client.bridge.refusals import PROFILE_FIRST
from client.bridge.wire import _exp_to_dict, _profile_to_dict, _skill_to_dict


REQUIRED_FIELDS = ("first_name", "last_name", "title", "email")


class Profile(Cv):
    """Экран «Профиль» целиком: чем окно спрашивает анкету и чем правит.

    Файл резюме — у примеси рядом: сама анкета и файл, к которому она
    прилагается, живут порознь и правятся порознь, а окно видит их одним
    экраном.

    Секреты: анкета отдаётся окну как есть — почта, телефон, ник в Telegram,
    ссылка на GitHub, город, образование и полный путь к резюме. Это осознанно:
    приложение однопользовательское, а страница живёт в своём окне, не в сети.
    """

    def __init__(self, hub) -> None:
        self._hub = hub

    def get(self) -> dict:
        """Анкета вместе с путём к резюме и тем, что о нём знает диск."""

        async def run() -> dict:
            async with self._hub.session_factory() as session:
                profile = await profile_repo.get_profile(session)
                languages = (
                    await profile_repo.list_profile_languages(session)
                    if profile is not None
                    else []
                )
            cv_path = self._hub.rs.cv_path
            return {
                "profile": _profile_to_dict(profile, languages),
                "cv_path": cv_path,
                "cv_meta": _stat_cv(cv_path),
            }

        return reply(self._hub.runner, run())

    def save(self, payload: dict) -> dict:
        """Записать анкету целиком, вместе с языками."""
        try:
            fields = _read_profile_fields(payload)
            languages = _filter_languages(payload.get("languages"))
        except (AttributeError, ValueError, TypeError) as e:
            return bad_fields("save", e)

        for required in REQUIRED_FIELDS:
            if not fields[required]:
                return denied(f"Поле '{required}' обязательно.")

        async def run() -> dict:
            async with self._hub.session_factory() as session:
                async with session.begin():
                    profile = await profile_repo.upsert_profile(session, **fields)
                    await profile_repo.replace_profile_languages(
                        session, profile.id, languages
                    )
            return {}

        return reply(self._hub.runner, run())

    def skills(self) -> dict:
        """Перечень навыков анкеты."""

        async def run() -> dict:
            async with self._hub.session_factory() as session:
                rows = await profile_repo.list_skills(session)
            return {"skills": [_skill_to_dict(s) for s in rows]}

        return reply(self._hub.runner, run())

    def save_skills(self, payload: dict) -> dict:
        """Заменить перечень навыков присланным."""
        return self._save_rows(payload, "skills", profile_repo.save_skills)

    def experience(self) -> dict:
        """Места работы вместе с указателем навыков.

        Указатель едет тем же ответом: строки опыта ссылаются на навыки, и
        вторым запросом окно рисовало бы их с пустыми названиями.
        """

        async def run() -> dict:
            async with self._hub.session_factory() as session:
                exps = await profile_repo.list_experience(session)
                skills = await profile_repo.list_skills(session)
            return {
                "experience": [_exp_to_dict(e) for e in exps],
                "skills_index": [_skill_to_dict(s) for s in skills],
            }

        return reply(self._hub.runner, run())

    def save_experience(self, payload: dict) -> dict:
        """Заменить перечень мест работы присланным."""
        return self._save_rows(payload, "experience", profile_repo.save_experience)

    def _save_rows(self, payload: dict, key: str, saving) -> dict:
        """Прочитать перечень строк анкеты и отдать его сохранению.

        Навыки и места работы приходят одной формой — списком объектов под
        своим ключом, — и различаются только этим ключом да объявлением записи.

        Отказ «сначала сохраните профайл» стоит внутри сделки нарочно: строки
        анкеты цепляются к её номеру, и без анкеты цеплять их не к чему.
        """
        try:
            rows = (payload or {}).get(key) or []
            if not isinstance(rows, list):
                raise ValueError(f"{key} must be a list")
        except (AttributeError, ValueError, TypeError) as e:
            return bad_fields(f"save_{key}", e)

        async def run() -> dict:
            try:
                async with self._hub.session_factory() as session:
                    async with session.begin():
                        profile = await profile_repo.get_profile(session)
                        if profile is None:
                            raise Denied(PROFILE_FIRST)
                        await saving(session, rows, profile.id)
            except profile_repo.SaveExperienceError as e:
                raise Denied(str(e))
            return {}

        return reply(self._hub.runner, run())


def _read_profile_fields(payload: dict) -> dict:
    """Поля анкеты из нагрузки: пустые строки — в пустоту, наборы — по перечням."""
    return {
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
        "work_format": _filter_set(payload.get("work_format"), WORK_FORMATS),
    }
