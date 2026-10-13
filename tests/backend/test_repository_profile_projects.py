"""Следствия сохранения проектов профиля.

Запись перечня у проектов та же, что у мест работы, и сторожится там; здесь —
разница проекта: одно обязательное поле, перечень «О проекте», порядок без дат,
и то, что два стека живут порознь.
"""

import pytest

from backend.repository.profile_experience import list_experience, save_experience
from backend.repository.profile_projects import list_projects, save_projects
from backend.repository.profile_records import RowError
from tests.dbio import put
from tests.factories import profile_row, profile_skill_row, project_row


async def test_projects_come_back_in_the_order_they_were_sent(session, session_factory):
    """Дат у проекта нет: порядок — тот, в каком человек их расставил."""
    person = profile_row()
    await put(session_factory, person)

    await save_projects(session, [{"name": "Свежий"}, {"name": "Давний"}], person.id)

    assert [p.name for p in await list_projects(session)] == ["Свежий", "Давний"]


async def test_a_nameless_project_is_refused_by_its_number(session, session_factory):
    """Название — единственное обязательное поле; без него перечень не пишется,
    и прежние проекты остаются."""
    person = profile_row()
    await put(session_factory, person)
    await put(session_factory, project_row(person.id, name="Прежний"))

    with pytest.raises(RowError) as refused:
        await save_projects(session, [{"name": "Бот"}, {"name": "  "}], person.id)

    assert refused.value.index == 2
    assert [p.name for p in await list_projects(session)] == ["Прежний"]


async def test_saving_again_replaces_projects_and_keeps_the_places_stack(
    session, session_factory
):
    """Повторная запись снимает связки своего стека, а не чужого: стек мест
    работы цел, и второе сохранение не упирается во внешний ключ."""
    person = profile_row()
    await put(session_factory, person)
    await put(session_factory, profile_skill_row(person.id, "Python"))
    await save_experience(session, [{
        "company": "Контур", "role": "Разработчик", "start_date": "2020-01-01",
        "skill_names": ["Python"],
    }], person.id)
    project = {"name": "Бот", "skill_names": ["Python"]}

    await save_projects(session, [project], person.id)
    await save_projects(session, [project | {"name": "Бот 2"}], person.id)

    assert [(p.name, [s.name for s in p.skills]) for p in await list_projects(session)] == [
        ("Бот 2", ["Python"])
    ]
    [place] = await list_experience(session)
    assert [s.name for s in place.skills] == ["Python"]


async def test_a_project_keeps_its_link_and_points(session, session_factory):
    person = profile_row()
    await put(session_factory, person)

    await save_projects(session, [{
        "name": "Бот", "url": " https://example.org/bot ", "about": ["Описание", " Пункт "],
    }], person.id)

    [project] = await list_projects(session)
    assert (project.url, project.about) == ("https://example.org/bot", ["Описание", "Пункт"])
