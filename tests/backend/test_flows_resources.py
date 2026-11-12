"""Следствия перезагрузки настроек перед обходом каналов.

Навыки, чёрный список, профиль и блок сведений о кандидате читаются один раз
на цикл и держатся в памяти: каждое объявление сверяется со всеми навыками, и
ходить за ними в базу на каждый пост значило бы платить сотнями запросов за
один обход.

Отсюда и следствие, которое видит пользователь: правка профиля в окне
подхватится со следующего цикла, а не немедленно.
"""

from backend.domain.named_salary import SalaryAsk
from backend.models import PreferenceKind, Profile, ProfileLanguage, ProfilePreference, SalaryPeriod
from tests.dbio import only_row, put
from tests.fakes.exchange_rates import RATES, rates_answer, serve_rates
from tests.factories import (
    blacklist_row,
    blacklist_switch_row,
    profile_row,
    profile_skill_row,
    resume_file,
)


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

    await pipeline.reload_resources()

    assert sorted(s.name for s in pipeline.skills_cache) == ["Docker", "Python"]


async def test_the_blacklist_is_lifted_into_memory(make_pipeline, session_factory):
    """Образцы чёрного списка поднимаются в память."""
    marks = [blacklist_row("keyword", "казино"), blacklist_row("keyword", "ставки")]
    await put(session_factory, *marks)
    await put(session_factory, *(blacklist_switch_row(m.id, active=True) for m in marks))
    pipeline = await make_pipeline()

    await pipeline.reload_resources()

    assert sorted(pipeline.blacklist_patterns) == ["казино", "ставки"]


async def test_a_switched_off_blacklist_entry_is_not_lifted(
    make_pipeline, session_factory
):
    """Погашенная запись чёрного списка в память не идёт.

    Гашение и значит «пока не отсеивай»; иначе кнопка в окне ничего бы
    не меняла.
    """
    off, on = blacklist_row("keyword", "казино"), blacklist_row("keyword", "ставки")
    await put(session_factory, off, on)
    await put(
        session_factory,
        blacklist_switch_row(off.id, active=False),
        blacklist_switch_row(on.id, active=True),
    )
    pipeline = await make_pipeline()

    await pipeline.reload_resources()

    assert pipeline.blacklist_patterns == ["ставки"]


async def test_the_candidate_slice_is_rebuilt(make_pipeline, session_factory):
    """Срез профиля для проверки пригодности собирается заново.

    По нему модель решает, подходит ли вакансия; устаревший срез
    отбраковывал бы по вчерашним ограничениям.
    """
    await put(session_factory, profile_row(title="Python-разработчик", location="Тверь"))
    profile = await only_row(session_factory, Profile)
    await put(
        session_factory,
        ProfileLanguage(profile_id=profile.id, language="Английский", level="B1"),
    )
    pipeline = await make_pipeline()

    await pipeline.reload_resources()

    assert pipeline.profile_cache.title == "Python-разработчик"
    assert pipeline.profile_cache.location == "Тверь"
    assert [(x.name, x.level) for x in pipeline.profile_cache.languages] == [
        ("Английский", "B1")
    ]


async def test_bans_and_info_are_lifted_each_to_its_own_place(make_pipeline, session_factory):
    """Запреты судит один зов, сведения читает другой, а пожелания до
    проверки вакансии не доходят вовсе: они только для откликов."""
    await put(session_factory, profile_row())
    profile = await only_row(session_factory, Profile)
    await put(
        session_factory,
        ProfilePreference(profile_id=profile.id, kind=PreferenceKind.BAN, text="без гемблинга"),
        ProfilePreference(profile_id=profile.id, kind=PreferenceKind.WISH, text="продукт"),
        ProfilePreference(profile_id=profile.id, kind=PreferenceKind.INFO, text="есть права"),
        ProfilePreference(profile_id=profile.id, kind=PreferenceKind.BAN, text="без крипты"),
    )
    pipeline = await make_pipeline()

    await pipeline.reload_resources()

    assert pipeline.profile_cache.bans == ["без гемблинга", "без крипты"]
    assert pipeline.profile_cache.info == ["есть права"]


async def test_an_empty_base_leaves_empty_caches(make_pipeline):
    """На пустой базе кэши остаются пустыми, а не ломаются.

    Так выглядит первый запуск до заполнения анкеты.
    """
    pipeline = await make_pipeline()

    await pipeline.reload_resources()

    assert pipeline.skills_cache == []
    assert pipeline.blacklist_patterns == []
    assert pipeline.profile_cache.title is None
    assert pipeline.salary_ask == SalaryAsk()


async def test_the_salary_and_the_rates_are_lifted_into_memory(make_pipeline, session_factory, monkeypatch):
    """Зарплата анкеты и курсы поднимаются в память для отсева по зарплате;
    курсы — уже обновлённые от источника: засеянный рубль — 80, источник — 70."""
    await put(session_factory, profile_row(
        minimum_salary=2000, expected_salary=4000,
        expected_salary_currency="€", expected_salary_period=SalaryPeriod.YEAR,
    ))
    serve_rates(monkeypatch, rates_answer({**RATES, "RUB": 70.0}))
    pipeline = await make_pipeline()

    await pipeline.reload_resources()

    assert pipeline.salary_ask == SalaryAsk(2000, 4000, "€", SalaryPeriod.YEAR)
    assert pipeline.rates["₽"] == 70.0


async def test_the_second_reload_sees_the_edits(make_pipeline, session_factory):
    """Повторная перезагрузка видит правки, сделанные между циклами.

    Ровно так пользователю и достаются его изменения: со следующего
    обхода, а не немедленно.
    """
    pipeline = await make_pipeline()
    await pipeline.reload_resources()

    mark = blacklist_row("keyword", "казино")
    await put(session_factory, mark)
    await put(session_factory, blacklist_switch_row(mark.id, active=True))
    await pipeline.reload_resources()

    assert pipeline.blacklist_patterns == ["казино"]


async def test_an_unset_cv_path_yields_nothing(make_pipeline):
    """Незаданный путь к резюме отдаёт отсутствие.

    Отправка по нему пропускается: приложить нечего.
    """
    pipeline = await make_pipeline()

    assert pipeline.cv_path() is None


async def test_a_set_cv_path_is_handed_over_as_a_path(make_pipeline, tmp_path):
    """Заданный путь к резюме отдаётся как путь, а не строкой."""
    resume = resume_file(tmp_path)
    pipeline = await make_pipeline()
    await pipeline.rs.set_cv_path(str(resume))

    assert pipeline.cv_path() == resume
