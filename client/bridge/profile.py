"""Анкета соискателя: сведения о себе, навыки, места работы и проекты."""

from __future__ import annotations

from backend.domain.salary import currency_sign
from backend.domain.taxonomy import GRADES, WORK_FORMATS
from backend.incoming import (
    amount_or_none,
    date_or_refusal,
    enum_member_or_none,
    normalize_enum_list,
    text_or_none,
)
from backend.models import Gender, SalaryPeriod
from backend.payloads import REQUIRED_PROFILE_FIELDS
from backend.repository import profile as profile_repo
from backend.repository import profile_experience as experience_repo
from backend.repository import profile_languages as languages_repo
from backend.repository import profile_projects as projects_repo
from backend.repository import profile_skills as skills_repo
from backend.repository.profile_records import RowError
from client.bridge.answer import BAD_PAYLOAD, Denied, bad_fields, denied, reply
from client.bridge.choices import _filter_languages
from client.bridge.cv import Cv
from client.bridge.cv_file import _stat_cv
from client.bridge.hub import Hub
from client.bridge.refusals import PROFILE_FIRST
from client.bridge.wire import (
    _exp_to_dict,
    _profile_to_dict,
    _project_to_dict,
    _skill_to_dict,
)


class Profile(Cv):
    """Экран «Профиль» целиком: чем окно спрашивает анкету и чем правит.

    Файл резюме — у примеси рядом: сама анкета и файл, к которому она
    прилагается, живут порознь и правятся порознь, а окно видит их одним
    экраном.

    Секреты: анкета отдаётся окну как есть — почта, телефон, ник в Telegram,
    ссылка на GitHub, город, образование и полный путь к резюме. Это осознанно:
    приложение однопользовательское, а страница живёт в своём окне, не в сети.
    """

    def __init__(self, hub: Hub) -> None:
        self._hub = hub

    def get(self) -> dict:
        """Анкета вместе с путём к резюме и тем, что о нём знает диск."""

        async def run() -> dict:
            async with self._hub.session_factory() as session:
                profile = await profile_repo.get_profile(session)
                languages = (
                    await languages_repo.list_profile_languages(session)
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
        except BAD_PAYLOAD as e:
            return bad_fields("save", e)

        for required in REQUIRED_PROFILE_FIELDS:
            if not fields[required]:
                return denied(f"Поле '{required}' обязательно.")

        async def run() -> dict:
            async with self._hub.session_factory() as session:
                async with session.begin():
                    profile = await profile_repo.upsert_profile(session, **fields)
                    await languages_repo.replace_profile_languages(
                        session, profile.id, languages
                    )
            return {}

        return reply(self._hub.runner, run())

    def skills(self) -> dict:
        """Перечень навыков анкеты."""

        async def run() -> dict:
            async with self._hub.session_factory() as session:
                rows = await skills_repo.list_skills(session)
            return {"skills": [_skill_to_dict(s) for s in rows]}

        return reply(self._hub.runner, run())

    def save_skills(self, payload: dict) -> dict:
        """Заменить перечень навыков присланным."""
        return self._save_rows(payload, "skills", skills_repo.save_skills)

    def experience(self) -> dict:
        """Места работы вместе с указателем навыков."""
        return self._records("experience", experience_repo.list_experience, _exp_to_dict)

    def save_experience(self, payload: dict) -> dict:
        """Заменить перечень мест работы присланным."""
        return self._save_rows(payload, "experience", experience_repo.save_experience)

    def projects(self) -> dict:
        """Проекты вместе с указателем навыков."""
        return self._records("projects", projects_repo.list_projects, _project_to_dict)

    def save_projects(self, payload: dict) -> dict:
        """Заменить перечень проектов присланным."""
        return self._save_rows(payload, "projects", projects_repo.save_projects)

    def _records(self, key: str, listing, to_dict) -> dict:
        """Записи анкеты со стеком вместе с указателем навыков.

        Указатель едет тем же ответом: стек записи ссылается на навыки, и
        вторым запросом окно рисовало бы его с пустыми названиями.
        """

        async def run() -> dict:
            async with self._hub.session_factory() as session:
                records = await listing(session)
                skills = await skills_repo.list_skills(session)
            return {
                key: [to_dict(one) for one in records],
                "skills_index": [_skill_to_dict(s) for s in skills],
            }

        return reply(self._hub.runner, run())

    def _save_rows(self, payload: dict, key: str, saving) -> dict:
        """Прочитать перечень строк анкеты и отдать его сохранению.

        Навыки, места работы и проекты приходят одной формой — списком объектов
        под своим ключом, — и различаются только этим ключом да объявлением записи.

        Отказ «сначала сохраните профайл» стоит внутри сделки нарочно: строки
        анкеты цепляются к её номеру, и без анкеты цеплять их не к чему.
        """
        try:
            rows = (payload or {}).get(key) or []
            if not isinstance(rows, list):
                raise ValueError(f"{key} must be a list")
        except BAD_PAYLOAD as e:
            return bad_fields(f"save_{key}", e)

        async def run() -> dict:
            try:
                async with self._hub.session_factory() as session:
                    async with session.begin():
                        profile = await profile_repo.get_profile(session)
                        if profile is None:
                            raise Denied(PROFILE_FIRST)
                        await saving(session, rows, profile.id)
            except RowError as e:
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
        "phone": text_or_none(payload.get("phone")),
        "location": text_or_none(payload.get("location")),
        "telegram_username": text_or_none(payload.get("telegram_username")),
        "github_url": text_or_none(payload.get("github_url")),
        "education": text_or_none(payload.get("education")),
        "free_preferences": text_or_none(payload.get("free_preferences")),
        "expected_salary": amount_or_none(payload.get("expected_salary")),
        "expected_salary_currency": currency_sign(
            text_or_none(payload.get("expected_salary_currency"))
        ),
        "expected_salary_period": enum_member_or_none(
            payload.get("expected_salary_period"), SalaryPeriod
        ),
        "first_name_latin": text_or_none(payload.get("first_name_latin")),
        "last_name_latin": text_or_none(payload.get("last_name_latin")),
        "gender": enum_member_or_none(payload.get("gender"), Gender),
        "patronymic": text_or_none(payload.get("patronymic")),
        "patronymic_latin": text_or_none(payload.get("patronymic_latin")),
        "birth_date": date_or_refusal(payload.get("birth_date"), "рождения"),
        "citizenship": text_or_none(payload.get("citizenship")),
        "about_me": text_or_none(payload.get("about_me")),
        "resume_url": text_or_none(payload.get("resume_url")),
        "grades": normalize_enum_list(payload.get("grades"), GRADES),
        "work_format": normalize_enum_list(payload.get("work_format"), WORK_FORMATS),
    }
