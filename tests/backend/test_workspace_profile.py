"""Анкета своя у профиля: читатели видят анкету активного, писатели не задевают чужую.

Анкеты лежат в профилях 1 и 2, активен 1.
"""

from datetime import date

from backend.flows.dm_classify import classify_and_apply
from backend.models import (
    Profile,
    ProfileExperience,
    ProfileLanguage,
    ProfileProject,
    ProfileSkill,
    VacancyStatus,
    Workspace,
    profile_experience_skills,
    profile_project_skills,
)
from backend.repository.agent_profile import build_agent_profile
from backend.repository.profile import get_profile, get_profile_in
from backend.repository.profile_cv import save_parsed_cv
from backend.repository.profile_experience import list_experience, save_experience
from backend.repository.profile_languages import (
    list_profile_languages,
    read_reply_language,
    read_search_languages,
    read_user_language,
)
from backend.repository.profile_projects import list_projects, save_projects
from backend.repository.profile_skills import list_skills, save_skills
from tests.dbio import all_rows, put, put_other_workspace
from tests.factories import (
    OTHER_WORKSPACE_ID,
    TEST_WORKSPACE_ID,
    experience_row,
    profile_row,
    profile_skill_row,
    project_row,
    vacancy_row,
)
from tests.factories_cv import parsed_cv, parsed_cv_profile


async def _two_profiles(session_factory) -> None:
    """Анкета в каждом профиле: язык, навык, место работы и проект со стеком.

    Своя анкета — «Иван», русский, Python; чужая — «Пётр», английский, Haskell.
    Чужая заведена первой: читатель первой строки и путаница номера анкеты с
    номером профиля (у своей анкеты номер 2, у чужой — 1) тогда видны.
    """
    await put_other_workspace(session_factory)
    for workspace_id, name, language, skill_name, company, project in (
        (OTHER_WORKSPACE_ID, "Пётр", "English", "Haskell", "Чужая", "Чужой"),
        (TEST_WORKSPACE_ID, "Иван", "Русский", "Python", "Своя", "Свой"),
    ):
        person = profile_row(workspace_id=workspace_id, first_name=name)
        await put(session_factory, person)
        skill = profile_skill_row(person.id, skill_name)
        await put(
            session_factory,
            ProfileLanguage(profile_id=person.id, language=language, level="native"),
            experience_row(person.id, company=company, skills=[skill]),
            project_row(person.id, name=project, skills=[skill]),
        )


async def test_readers_see_only_the_active_profile(session, session_factory):
    await _two_profiles(session_factory)

    agent = await build_agent_profile(session, date(2026, 1, 1), photo=False, salary=[], slot="main")

    assert (await get_profile(session)).first_name == "Иван"
    assert [lang.language for lang in await list_profile_languages(session)] == ["Русский"]
    assert await read_user_language(session) == "Русский"
    assert await read_search_languages(session) == ["Русский"]
    assert [s.name for s in await list_skills(session)] == ["Python"]
    assert [e.company for e in await list_experience(session)] == ["Своя"]
    assert [p.name for p in await list_projects(session)] == ["Свой"]
    assert "Python" in agent
    theirs = ("Пётр", "English", "Haskell", "Чужая", "Чужой")
    assert [word for word in theirs if word in agent] == []


async def test_editing_skills_leaves_the_other_profile_alone(session, session_factory):
    await _two_profiles(session_factory)

    async with session.begin():
        await save_skills(session, [], (await get_profile(session)).id)

    assert [s.name for s in await all_rows(session_factory, ProfileSkill)] == ["Haskell"]
    assert len(await all_rows(session_factory, profile_experience_skills)) == 1
    assert len(await all_rows(session_factory, profile_project_skills)) == 1


async def test_saving_records_leaves_the_other_profile_alone(session, session_factory):
    await _two_profiles(session_factory)

    async with session.begin():
        mine = (await get_profile(session)).id
        await save_experience(session, [], mine)
        await save_projects(session, [], mine)

    assert [e.company for e in await all_rows(session_factory, ProfileExperience)] == ["Чужая"]
    assert [p.name for p in await all_rows(session_factory, ProfileProject)] == ["Чужой"]
    assert len(await all_rows(session_factory, profile_experience_skills)) == 1
    assert len(await all_rows(session_factory, profile_project_skills)) == 1


async def test_writers_edit_the_named_profile_even_if_it_is_not_active(
    session, session_factory
):
    await _two_profiles(session_factory)
    place = {"company": "Новая", "role": "Разработчик", "start_date": "2024-01-01"}

    async with session.begin():
        theirs = (await get_profile_in(session, OTHER_WORKSPACE_ID)).id
        await save_experience(session, [{**place, "skill_names": ["Haskell"]}], theirs)

    # Своя «Своя — Python» и новая «Новая — Haskell»: стек найден в чужой анкете.
    assert len(await all_rows(session_factory, profile_experience_skills)) == 2

    async with session.begin():
        await save_skills(session, [], theirs)

    assert [s.name for s in await all_rows(session_factory, ProfileSkill)] == ["Python"]
    async with session_factory() as fresh:
        mine = await list_experience(fresh)
    assert [(e.company, [s.name for s in e.skills]) for e in mine] == [("Своя", ["Python"])]


async def test_a_parsed_cv_lands_in_the_named_workspace(session, session_factory):
    await _two_profiles(session_factory)

    async with session.begin():
        await save_parsed_cv(
            session, parsed_cv(profile=parsed_cv_profile(first_name="Новый")),
            workspace_id=OTHER_WORKSPACE_ID, cv_path="cv/второе.pdf",
        )

    people = {p.workspace_id: p.first_name for p in await all_rows(session_factory, Profile)}
    assert people == {TEST_WORKSPACE_ID: "Иван", OTHER_WORKSPACE_ID: "Новый"}
    assert [s.name for s in await all_rows(session_factory, ProfileSkill)] == ["Python"]
    assert [lang.language for lang in await all_rows(session_factory, ProfileLanguage)] == [
        "Русский"
    ]
    assert [e.company for e in await all_rows(session_factory, ProfileExperience)] == ["Своя"]
    assert [p.name for p in await all_rows(session_factory, ProfileProject)] == ["Свой"]
    paths = {w.id: w.cv_path for w in await all_rows(session_factory, Workspace)}
    assert paths == {TEST_WORKSPACE_ID: "", OTHER_WORKSPACE_ID: "cv/второе.pdf"}


async def test_an_hr_letter_is_read_in_the_language_of_the_vacancy_profile(
    session_factory, monkeypatch
):
    await _two_profiles(session_factory)
    vacancy = vacancy_row(status=VacancyStatus.APPLIED, workspace_id=OTHER_WORKSPACE_ID)
    await put(session_factory, vacancy)
    asked = []

    async def classify_hr_reply(ask, client, model):
        asked.append(ask.language)
        return None, None

    monkeypatch.setattr("backend.flows.dm_classify.classify_hr_reply", classify_hr_reply)

    await classify_and_apply(
        session_factory, None, "model", "давайте созвонимся",
        (vacancy.id, 1, VacancyStatus.APPLIED),
    )

    assert asked == ["English"]


async def test_a_reply_is_written_in_the_language_of_the_vacancy_profile(
    session, session_factory
):
    await _two_profiles(session_factory)
    vacancy = vacancy_row(language=None, workspace_id=OTHER_WORKSPACE_ID)
    await put(session_factory, vacancy)

    assert await read_reply_language(session, vacancy.id) == "English"
