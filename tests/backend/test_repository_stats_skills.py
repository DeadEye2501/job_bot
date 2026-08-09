"""Следствия подсчёта технологий, встречающихся в вакансиях.

Считается, в скольких вакансиях тег назван, а не сколько раз он там написан:
вакансия, где «Python» упомянут трижды, весит столько же, сколько та, где он
назван один раз. Рядом с каждым тегом стоит отметка «мой» — он есть в профиле
под этим именем или одним из написаний.
"""

from backend.repository.stats_summary import get_stats_skills
from tests.dbio import put
from tests.factories import days_ago, profile_row, profile_skill_row, vacancy_row


async def labels(session, **kwargs) -> list[str]:
    """Названия тегов в порядке выдачи."""
    got = await get_stats_skills(session, **kwargs)
    return [item["label"] for item in got["skills"]]


async def test_an_empty_database_gives_an_empty_list(session):
    """На пустой базе список тегов пуст."""
    got = await get_stats_skills(session, period="all")

    assert got["skills"] == []
    assert got["period"] == "all"
    assert got["min_count"] == 2


async def test_a_tag_counts_once_per_vacancy(session, session_factory):
    """Повтор тега внутри одной вакансии считается один раз.

    Разбор мог выписать «Python» и в обязательное, и в желательное, и
    вакансия весила бы вдвое.
    """
    await put(
        session_factory,
        vacancy_row(stack=["Python", "python", "PYTHON"]),
        vacancy_row(stack=["Python"]),
    )

    got = await get_stats_skills(session, period="all", min_count=1)

    assert [(x["label"], x["count"]) for x in got["skills"]] == [("Python", 2)]


async def test_spellings_of_one_tag_collapse_keeping_the_first_seen(
    session, session_factory
):
    """Разные написания одного тега сливаются, показывается встреченное первым."""
    await put(
        session_factory,
        vacancy_row(stack=["FastAPI"]),
        vacancy_row(stack=["fastapi"]),
        vacancy_row(stack=["FASTAPI"]),
    )

    got = await get_stats_skills(session, period="all", min_count=1)

    assert [(x["label"], x["count"]) for x in got["skills"]] == [("FastAPI", 3)]


async def test_rare_tags_are_hidden_behind_the_threshold(session, session_factory):
    """Редкие теги прячутся за порогом: иначе список утонул бы в шуме."""
    await put(
        session_factory,
        vacancy_row(stack=["Python", "Кобол"]),
        vacancy_row(stack=["Python"]),
    )

    assert await labels(session, period="all") == ["Python"]
    assert sorted(await labels(session, period="all", min_count=1)) == sorted(
        ["Python", "Кобол"]
    )


async def test_the_list_leads_with_the_most_common_tag(session, session_factory):
    """Вперёд идёт самый частый тег, при равенстве — по названию без учёта регистра.

    Порядок заведения обратен ожидаемому, и регистр у равных по частоте
    разный: сравнение по кодам символов поставило бы заглавные впереди.
    """
    await put(
        session_factory,
        vacancy_row(stack=["redis", "Docker", "Python"]),
        vacancy_row(stack=["redis", "Docker", "Python"]),
        vacancy_row(stack=["Python"]),
    )

    assert await labels(session, period="all") == ["Python", "Docker", "redis"]


async def test_the_list_is_cut_to_the_limit(session, session_factory):
    """Список обрезается по пределу, и обрезается после упорядочивания."""
    await put(
        session_factory,
        vacancy_row(stack=["редкий", "частый", "средний"]),
        vacancy_row(stack=["частый", "средний"]),
        vacancy_row(stack=["частый"]),
    )

    assert await labels(session, period="all", min_count=1, limit=2) == [
        "частый",
        "средний",
    ]


async def test_a_tag_of_the_profile_is_marked_as_mine(session, session_factory):
    """Тег, что есть в профиле, помечается своим — по имени или по написанию."""
    profile = profile_row()
    await put(session_factory, profile)
    await put(
        session_factory,
        profile_skill_row(profile.id, "PostgreSQL", aliases=["Postgres"]),
    )
    await put(
        session_factory,
        vacancy_row(stack=["postgres", "PostgreSQL", "Кобол"]),
    )

    got = await get_stats_skills(session, period="all", min_count=1)
    marks = {x["label"]: x["mine"] for x in got["skills"]}

    assert marks == {"postgres": True, "PostgreSQL": True, "Кобол": False}


async def test_an_unparsed_vacancy_contributes_no_tags(session, session_factory):
    """Недоразобранная вакансия своих тегов в счёт не даёт."""
    await put(
        session_factory,
        vacancy_row(stack=["Python"], is_parsed=True),
        vacancy_row(stack=["Кобол"], is_parsed=False),
    )

    assert await labels(session, period="all", min_count=1) == ["Python"]


async def test_the_window_cuts_by_the_creation_date(session, session_factory):
    """Окно отсекает по дате появления вакансии."""
    await put(
        session_factory,
        vacancy_row(stack=["Python"], created_at=days_ago(1)),
        vacancy_row(stack=["Кобол"], created_at=days_ago(40)),
    )

    assert await labels(session, period="week", min_count=1) == ["Python"]
    assert sorted(await labels(session, period="all", min_count=1)) == sorted(
        ["Python", "Кобол"]
    )


async def test_junk_inside_the_stack_is_skipped(session, session_factory):
    """Мусор внутри стека пропускается, а не роняет подсчёт.

    Стек лежит колонкой JSON, и туда могло попасть что угодно — из старых
    данных или чужой правкой базы.
    """
    await put(
        session_factory,
        vacancy_row(stack=["Python", "   ", "", 42, None]),
        vacancy_row(stack=[]),
    )

    assert await labels(session, period="all", min_count=1) == ["Python"]
