"""Следствия перезагрузки настроек перед обходом каналов.

Навыки, чёрный список, профиль и блок сведений о кандидате читаются один раз
на цикл и держатся в памяти: каждое объявление сверяется со всеми навыками, и
ходить за ними в базу на каждый пост значило бы платить сотнями запросов за
один обход.

Отсюда и следствие, которое видит пользователь: правка профиля в окне
подхватится со следующего цикла, а не немедленно.
"""

from backend.models import Profile, ProfileLanguage
from tests.dbio import only_row, put
from tests.factories import blacklist_row, profile_row, profile_skill_row


async def test_the_skills_are_lifted_into_memory(make_pipeline, session_factory):
    """Навыки профиля поднимаются в память.

    С ними сверяется каждое объявление; ходить за ними в базу на каждый
    пост значило бы платить сотнями запросов за один обход.
    """
    await put(session_factory, profile_row())
    profile = await only_row(session_factory, Profile)
    await put(
        session_factory,
        profile_skill_row(profile.id, "Python"),
        profile_skill_row(profile.id, "Docker"),
    )
    pipeline = await make_pipeline()

    await pipeline._reload_resources()

    assert sorted(s.name for s in pipeline._skills_cache) == ["Docker", "Python"]


async def test_the_blacklist_is_lifted_into_memory(make_pipeline, session_factory):
    """Образцы чёрного списка поднимаются в память."""
    await put(
        session_factory,
        blacklist_row("keyword", "казино"),
        blacklist_row("keyword", "ставки"),
    )
    pipeline = await make_pipeline()

    await pipeline._reload_resources()

    assert sorted(pipeline._blacklist_patterns) == ["казино", "ставки"]


async def test_a_switched_off_blacklist_entry_is_not_lifted(
    make_pipeline, session_factory
):
    """Погашенная запись чёрного списка в память не идёт.

    Гашение и значит «пока не отсеивай»; иначе кнопка в окне ничего бы
    не меняла.
    """
    await put(
        session_factory,
        blacklist_row("keyword", "казино", active=False),
        blacklist_row("keyword", "ставки"),
    )
    pipeline = await make_pipeline()

    await pipeline._reload_resources()

    assert pipeline._blacklist_patterns == ["ставки"]


async def test_the_candidate_slice_is_rebuilt(make_pipeline, session_factory):
    """Срез профиля для проверки пригодности собирается заново.

    По нему модель решает, подходит ли вакансия; устаревший срез
    отбраковывал бы по вчерашним ограничениям.
    """
    await put(session_factory, profile_row(title="Python-разработчик", location="Ереван"))
    profile = await only_row(session_factory, Profile)
    await put(
        session_factory,
        ProfileLanguage(profile_id=profile.id, language="Английский", level="B1"),
    )
    pipeline = await make_pipeline()

    await pipeline._reload_resources()

    assert pipeline._profile_cache.title == "Python-разработчик"
    assert pipeline._profile_cache.location == "Ереван"
    assert [(x.name, x.level) for x in pipeline._profile_cache.languages] == [
        ("Английский", "B1")
    ]


async def test_the_letter_block_is_rebuilt(make_pipeline, session_factory):
    """Блок сведений о кандидате для письма собирается заново.

    Он подмешивается в отклик; без перезагрузки письма уходили бы с
    прошлогодним описанием.
    """
    await put(session_factory, profile_row(title="Python-разработчик"))
    pipeline = await make_pipeline()

    await pipeline._reload_resources()

    assert "Python-разработчик" in pipeline._profile_block


async def test_an_empty_base_leaves_empty_caches(make_pipeline):
    """На пустой базе кэши остаются пустыми, а не ломаются.

    Так выглядит первый запуск до заполнения анкеты.
    """
    pipeline = await make_pipeline()

    await pipeline._reload_resources()

    assert pipeline._skills_cache == []
    assert pipeline._blacklist_patterns == []
    assert pipeline._profile_cache.title is None


async def test_the_second_reload_sees_the_edits(make_pipeline, session_factory):
    """Повторная перезагрузка видит правки, сделанные между циклами.

    Ровно так пользователю и достаются его изменения: со следующего
    обхода, а не немедленно.
    """
    pipeline = await make_pipeline()
    await pipeline._reload_resources()

    await put(session_factory, blacklist_row("keyword", "казино"))
    await pipeline._reload_resources()

    assert pipeline._blacklist_patterns == ["казино"]


async def test_an_unset_cv_path_yields_nothing(make_pipeline):
    """Незаданный путь к резюме отдаёт отсутствие.

    Отправка по нему пропускается: приложить нечего.
    """
    pipeline = await make_pipeline()

    assert pipeline._cv_path() is None


async def test_a_set_cv_path_is_handed_over_as_a_path(make_pipeline, tmp_path):
    """Заданный путь к резюме отдаётся как путь, а не строкой."""
    resume = tmp_path / "Резюме.pdf"
    resume.write_bytes(b"%PDF")
    pipeline = await make_pipeline()
    await pipeline._rs.set_app("cv_path", str(resume))

    assert pipeline._cv_path() == resume
