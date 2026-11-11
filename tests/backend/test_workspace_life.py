"""Жизнь профиля: создание тремя способами, смена, удаление и сброс кэша конвейера.

Исходный профиль 1 активен: анкета, фото, резюме, тумблеры и вакансия.
"""

from datetime import UTC, datetime

from sqlalchemy import event, select
from sqlalchemy.orm import selectinload

from backend.bot.media import MEDIA_DIR, stored_media
from backend.flows import embeddings
from backend.flows.workspaces import create_workspace, delete_active_workspace, switch_workspace
from backend.models import (
    HR,
    CoverLetter,
    Message,
    Profile,
    ProfileExperience,
    ProfileLanguage,
    ProfileProject,
    ProfileSkill,
    TelegramChannel,
    TrashEvent,
    Vacancy,
    Workspace,
    WorkspaceAggregator,
    WorkspaceBlacklist,
    WorkspaceChannel,
)
from backend.repository.workspace_removal import delete_workspace_rows
from backend.repository.workspaces import list_workspaces, make_active
from tests.dbio import active_workspace_ids, all_rows, put, put_other_workspace
from tests.factories import (
    OTHER_WORKSPACE_ID,
    TEST_WORKSPACE_ID,
    aggregator_switch_row,
    blacklist_row,
    blacklist_switch_row,
    channel_row,
    channel_switch_row,
    experience_row,
    hr_row,
    message_row,
    photo_head,
    profile_row,
    profile_skill_row,
    project_row,
    status_history_row,
    trash_event_row,
    vacancy_event_row,
    vacancy_row,
    workspace_row,
)
from tests.factories_aggregators import (
    aggregator_resume_row,
    aggregator_row,
    application_row,
    screening_row,
    vacancy_contact_row,
)

PHOTO = photo_head(".jpg") + b"jpeg"
SWITCHES = (WorkspaceChannel, WorkspaceAggregator, WorkspaceBlacklist)


async def _set_paths(session_factory, cv_path: str, photo_path: str = "") -> None:
    async with session_factory() as session, session.begin():
        workspace = await session.get(Workspace, TEST_WORKSPACE_ID)
        workspace.cv_path, workspace.photo_path = cv_path, photo_path


async def _source(session_factory, cv_path: str = "C:/cv.pdf") -> int:
    """Всё своё у активного профиля; ответ — номер резюме, выбранного на сайте."""
    person = profile_row(
        phone="+79001234567", education="МГУ", about_me="Пишу на Python",
        expected_salary=300000, expected_salary_currency="RUB",
    )
    channel = channel_row()
    site = aggregator_row()
    mark = blacklist_row("company", "Рога")
    await put(session_factory, person, channel, site, mark)
    resume = aggregator_resume_row(site.id)
    skill = profile_skill_row(person.id, "Python")
    await put(
        session_factory,
        resume,
        ProfileLanguage(profile_id=person.id, language="Русский", level="native"),
        experience_row(person.id, company="Контур", skills=[skill]),
        project_row(person.id, name="Бот", skills=[skill]),
    )
    await put(
        session_factory,
        channel_switch_row(channel.id, is_active=True, last_processed_msg_id=50),
        aggregator_switch_row(
            site.id, is_active=True, last_run_at=datetime(2026, 1, 1, tzinfo=UTC),
            chosen_resume_id=resume.id,
        ),
        blacklist_switch_row(mark.id, active=True),
        vacancy_row(),
    )
    (MEDIA_DIR / "profile" / "1").mkdir(parents=True, exist_ok=True)
    (MEDIA_DIR / "profile" / "1" / "photo.jpg").write_bytes(PHOTO)
    await _set_paths(session_factory, cv_path, "profile/1/photo.jpg")
    await put(session_factory, CoverLetter(
        workspace_id=TEST_WORKSPACE_ID, ru="Здравствуйте", ru_short="Коротко",
        en="Hello", en_short="Short",
    ))
    return resume.id


async def _letters(session_factory, workspace_id: int) -> tuple | None:
    """Письма профиля четвёркой; строки писем нет — пусто."""
    async with session_factory() as session:
        row = await session.get(CoverLetter, workspace_id)
    return None if row is None else (row.ru, row.ru_short, row.en, row.en_short)


async def _workspace(session_factory, workspace_id: int) -> Workspace | None:
    async with session_factory() as session:
        return await session.get(Workspace, workspace_id)


async def _profile_of(session_factory, workspace_id: int) -> Profile | None:
    async with session_factory() as session:
        return await session.scalar(select(Profile).where(Profile.workspace_id == workspace_id))


async def _of(session_factory, model, profile_id: int) -> list:
    """Строки анкеты этого рода; у мест работы и проектов — со стеком."""
    query = select(model).where(model.profile_id == profile_id).order_by(model.id)
    if model in (ProfileExperience, ProfileProject):
        query = query.options(selectinload(model.skills))
    async with session_factory() as session:
        return list((await session.scalars(query)).all())


async def _switches(session_factory, workspace_id: int) -> list:
    async with session_factory() as session:
        return [
            row for model in SWITCHES
            for row in (await session.scalars(
                select(model).where(model.workspace_id == workspace_id)
            )).all()
        ]


async def _vacancies_of(session_factory, workspace_id: int) -> list[Vacancy]:
    return [v for v in await all_rows(session_factory, Vacancy) if v.workspace_id == workspace_id]


async def test_an_empty_workspace_has_nothing_and_is_active(session_factory):
    await _source(session_factory)

    made = await create_workspace(session_factory, "empty")

    async with session_factory() as session:
        rows = await list_workspaces(session)
    assert [(r.id, r.title, r.is_active) for r in rows] == [
        (TEST_WORKSPACE_ID, "Python-разработчик", False), (made, None, True)
    ]
    assert await _profile_of(session_factory, made) is None
    assert await _switches(session_factory, made) == []
    assert await _letters(session_factory, made) is None
    workspace = await _workspace(session_factory, made)
    assert (workspace.cv_path, workspace.photo_path) == ("", "")


async def test_personal_data_carries_only_the_person(session_factory):
    await _source(session_factory)

    made = await create_workspace(session_factory, "personal")

    person = await _profile_of(session_factory, made)
    assert (person.first_name, person.last_name, person.email, person.phone, person.title) == (
        "Иван", "Петров", "ivan@example.com", "+79001234567", ""
    )
    assert (person.education, person.about_me, person.expected_salary) == (None, None, None)
    assert person.expected_salary_currency is None
    languages = await _of(session_factory, ProfileLanguage, person.id)
    assert [(lang.language, lang.level) for lang in languages] == [("Русский", "native")]
    for model in (ProfileSkill, ProfileExperience, ProfileProject):
        assert await _of(session_factory, model, person.id) == []
    workspace = await _workspace(session_factory, made)
    assert workspace.cv_path == ""
    assert workspace.photo_path == f"profile/{made}/photo.jpg"
    assert stored_media(workspace.photo_path).read_bytes() == PHOTO
    assert await _switches(session_factory, made) == []
    # Письмо пишется под должность, а её личные данные не переносят.
    assert await _letters(session_factory, made) is None


async def test_a_copy_carries_everything_but_vacancies_and_read_marks(session_factory):
    resume_id = await _source(session_factory)

    made = await create_workspace(session_factory, "copy")

    person = await _profile_of(session_factory, made)
    assert (person.title, person.education, person.about_me, person.expected_salary) == (
        "Python-разработчик", "МГУ", "Пишу на Python", 300000
    )
    assert [s.name for s in await _of(session_factory, ProfileSkill, person.id)] == ["Python"]
    places = await _of(session_factory, ProfileExperience, person.id)
    assert [(p.company, [s.name for s in p.skills]) for p in places] == [("Контур", ["Python"])]
    projects = await _of(session_factory, ProfileProject, person.id)
    assert [(p.name, [s.name for s in p.skills]) for p in projects] == [("Бот", ["Python"])]
    workspace = await _workspace(session_factory, made)
    assert workspace.cv_path == "C:/cv.pdf"
    assert stored_media(workspace.photo_path).read_bytes() == PHOTO
    assert workspace.photo_path == f"profile/{made}/photo.jpg"
    channel, site, mark = await _switches(session_factory, made)
    assert (channel.is_active, channel.last_processed_msg_id) == (True, None)
    assert (site.is_active, site.last_run_at, site.chosen_resume_id) == (True, None, resume_id)
    assert mark.active is True
    assert await _vacancies_of(session_factory, made) == []
    assert await _letters(session_factory, made) == ("Здравствуйте", "Коротко", "Hello", "Short")
    assert await _letters(session_factory, TEST_WORKSPACE_ID) == (
        "Здравствуйте", "Коротко", "Hello", "Short"
    )


async def test_copying_a_workspace_without_a_profile_still_copies_the_rest(session_factory):
    channel = channel_row()
    await put(session_factory, channel)
    await put(session_factory, channel_switch_row(channel.id, is_active=True))
    await _set_paths(session_factory, "C:/cv.pdf")

    made = await create_workspace(session_factory, "copy")

    assert await _profile_of(session_factory, made) is None
    assert (await _workspace(session_factory, made)).cv_path == "C:/cv.pdf"
    (switch,) = await _switches(session_factory, made)
    assert switch.is_active is True


async def test_switching_changes_the_active_workspace(session_factory):
    await put_other_workspace(session_factory)

    assert await switch_workspace(session_factory, OTHER_WORKSPACE_ID) is True
    assert await active_workspace_ids(session_factory) == [OTHER_WORKSPACE_ID]

    assert await switch_workspace(session_factory, TEST_WORKSPACE_ID) is True
    assert await active_workspace_ids(session_factory) == [TEST_WORKSPACE_ID]

    assert await switch_workspace(session_factory, 99) is False
    assert await active_workspace_ids(session_factory) == [TEST_WORKSPACE_ID]


async def _with_children(session_factory, vacancy: Vacancy) -> None:
    """Всё, что лежит на вакансии: отклик со скринингом, контакт, история, событие."""
    reply = application_row(vacancy.id)
    await put(
        session_factory, reply, vacancy_contact_row(vacancy.id, "hr@x.ru"),
        status_history_row(vacancy.id), vacancy_event_row(vacancy.id),
    )
    await put(session_factory, screening_row(reply.id, 0))


async def test_deleting_takes_the_workspace_and_keeps_shared_rows(session_factory, tmp_path):
    cv = tmp_path / "cv.pdf"
    cv.write_bytes(b"%PDF")
    await _source(session_factory, cv_path=str(cv))
    await put(session_factory, workspace_row(id=2), workspace_row(id=3))
    theirs = vacancy_row(workspace_id=3)
    hr = hr_row()
    await put(session_factory, theirs, hr, profile_row(workspace_id=3, first_name="Пётр"))
    (mine,) = await _vacancies_of(session_factory, TEST_WORKSPACE_ID)
    await _with_children(session_factory, mine)
    (channel,) = await all_rows(session_factory, TelegramChannel)
    await put(
        session_factory,
        message_row(hr_id=hr.id, vacancy_id=mine.id, tg_message_id=1),
        trash_event_row(source_key="мусор"),
        trash_event_row(source_key="чужой", workspace_id=3),
        channel_switch_row(channel.id, workspace_id=3, is_active=True),
    )

    assert await delete_active_workspace(session_factory) == "deleted"

    assert [w.id for w in await all_rows(session_factory, Workspace)] == [2, 3]
    assert await active_workspace_ids(session_factory) == [2]
    assert [v.id for v in await all_rows(session_factory, Vacancy)] == [theirs.id]
    (letter,) = await all_rows(session_factory, Message)
    assert letter.vacancy_id is None
    assert len(await all_rows(session_factory, HR)) == 1
    assert len(await all_rows(session_factory, TelegramChannel)) == 1
    assert [t.source_key for t in await all_rows(session_factory, TrashEvent)] == ["чужой"]
    assert [p.first_name for p in await all_rows(session_factory, Profile)] == ["Пётр"]
    assert await all_rows(session_factory, ProfileSkill) == []
    assert await _switches(session_factory, TEST_WORKSPACE_ID) == []
    assert len(await _switches(session_factory, 3)) == 1
    assert await all_rows(session_factory, CoverLetter) == []
    assert stored_media("profile/1/photo.jpg") is None
    assert cv.read_bytes() == b"%PDF"


async def test_the_removal_takes_as_many_queries_for_many_vacancies_as_for_one(
    engine, session_factory
):
    """Удаление не растёт с числом вакансий: всё оно — одна сделка, и пока она
    идёт, запись в базу заперта; на тысячах вакансий по одной письмо HR,
    пришедшее в это время, не дождалось бы своей записи."""
    await put(session_factory, workspace_row(id=2), workspace_row(id=3))
    for workspace_id, count in ((2, 1), (3, 3)):
        for _ in range(count):
            vacancy = vacancy_row(workspace_id=workspace_id)
            await put(session_factory, vacancy)
            await _with_children(session_factory, vacancy)
    queries = []

    def counting(*_args) -> None:
        queries.append(1)

    event.listen(engine.sync_engine, "before_cursor_execute", counting)
    try:
        counts = []
        for workspace_id in (2, 3):
            queries.clear()
            async with session_factory() as session:
                async with session.begin():
                    await delete_workspace_rows(session, workspace_id)
            counts.append(len(queries))
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", counting)

    assert counts[0] == counts[1]
    assert await all_rows(session_factory, Vacancy) == []


async def test_a_deleted_workspace_number_is_not_given_again(session_factory):
    """Разбор резюме пишет анкету в запомненный номер профиля; достанься номер
    удалённого новому — анкета легла бы не туда, а не упала бы на ключе."""
    first = await create_workspace(session_factory, "empty")
    assert await delete_active_workspace(session_factory) == "deleted"

    second = await create_workspace(session_factory, "empty")

    assert second != first


async def test_the_last_workspace_is_not_deleted(session_factory):
    await _source(session_factory)

    assert await delete_active_workspace(session_factory) == "last"

    assert await active_workspace_ids(session_factory) == [TEST_WORKSPACE_ID]
    assert len(await all_rows(session_factory, Vacancy)) == 1
    assert await _profile_of(session_factory, TEST_WORKSPACE_ID) is not None
    assert stored_media("profile/1/photo.jpg") is not None


async def test_forgetting_caches_drops_vectors_of_the_old_workspace(
    make_pipeline, session_factory
):
    await put_other_workspace(session_factory)
    mine = vacancy_row(embedding=[0.1, 0.2])
    await put(session_factory, mine)
    pipeline = await make_pipeline()
    assert await embeddings.similar_vacancy_id(pipeline, [0.1, 0.2]) == mine.id

    async with session_factory() as session, session.begin():
        await make_active(session, OTHER_WORKSPACE_ID)
    pipeline.forget_caches()

    assert await embeddings.similar_vacancy_id(pipeline, [0.1, 0.2]) is None
