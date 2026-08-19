"""Следствия сохранения мест работы профиля.

Список проверяется целиком до первой записи в базу: пользователь набирает его
на экране руками, и упасть на середине значило бы стереть половину прежних
записей, не сохранив новых. Ошибка называет номер строки, чтобы экран показал
её на месте.
"""

from datetime import date

import pytest
from sqlalchemy import select

from backend.models import ProfileExperience
from backend.repository.profile import SaveExperienceError, list_experience, save_experience
from tests.dbio import put
from tests.factories import experience_row, profile_row, profile_skill_row


def _row(**overrides) -> dict:
    """Строка списка, какой её присылает экран."""
    fields = {"company": "Контур", "role": "Разработчик", "start_date": "2020-01-01"}
    fields.update(overrides)
    return fields


async def test_places_are_listed_newest_first(session, session_factory):
    """Места работы отдаются от свежего к давнему."""
    profile = profile_row()
    await put(session_factory, profile)
    await put(
        session_factory,
        experience_row(profile.id, company="Давняя", start_date=date(2018, 1, 1)),
        experience_row(profile.id, company="Свежая", start_date=date(2023, 1, 1)),
        experience_row(profile.id, company="Средняя", start_date=date(2020, 1, 1)),
    )

    got = await list_experience(session)

    assert [e.company for e in got] == ["Свежая", "Средняя", "Давняя"]


@pytest.mark.parametrize(
    ("field", "value", "problem"),
    [
        pytest.param("company", "   ", "название компании", id="без компании"),
        pytest.param("role", "", "должность", id="без должности"),
        pytest.param(
            "start_date", None, "не заполнена дата начала", id="без даты начала"
        ),
        pytest.param("start_date", "вчера", "неверная дата начала", id="дата не дата"),
        pytest.param("end_date", "завтра", "неверная дата окончания", id="конец не дата"),
    ],
)
async def test_an_invalid_row_is_named_by_its_number(
    session, session_factory, field, value, problem
):
    """Неверная строка отвергается с её номером и понятной причиной.

    Причина у пустой даты названа целиком, а не общей подстрокой: пустая
    дата иначе попала бы в разбор и вернулась бы с сообщением «неверная
    дата начала», а проверка по общей подстроке этого не отличила бы.
    """
    profile = profile_row()
    await put(session_factory, profile)

    with pytest.raises(SaveExperienceError, match=problem) as failed:
        await save_experience(
            session, [_row(), _row(**{field: value})], profile.id
        )

    assert failed.value.index == 2


async def test_nothing_is_written_when_a_later_row_is_invalid(
    session, session_factory
):
    """Ошибка в поздней строке отменяет запись целиком, а не наполовину.

    Прежние места остаются на месте: пользователь исправит одну строку и
    сохранит заново, не набирая всё сначала.
    """
    profile = profile_row()
    await put(session_factory, profile)
    await put(session_factory, experience_row(profile.id, company="Была раньше"))

    with pytest.raises(SaveExperienceError):
        await save_experience(
            session,
            [_row(company="Первая новая"), _row(company="")],
            profile.id,
        )

    assert [e.company for e in (await session.scalars(select(ProfileExperience))).all()] == [
        "Была раньше"
    ]


async def test_saving_replaces_everything_that_was_there(session, session_factory):
    """Сохранение заменяет весь прежний список, а не дополняет его."""
    profile = profile_row()
    await put(session_factory, profile)
    await put(session_factory, experience_row(profile.id, company="Была раньше"))

    await save_experience(session, [_row(company="Стала теперь")], profile.id)

    assert [e.company for e in (await session.scalars(select(ProfileExperience))).all()] == [
        "Стала теперь"
    ]


async def test_a_place_keeps_everything_it_was_given(session, session_factory):
    """Место работы сохраняется со всем, что при нём прислали."""
    profile = profile_row()
    await put(session_factory, profile)

    await save_experience(
        session,
        [
            _row(
                company="  Контур  ",
                company_url="  https://kontur.ru  ",
                role="  Старший разработчик  ",
                start_date="2020-03-01",
                end_date="2023-06-30",
                achievements=["  ускорил сборку  ", "  ", "", 42, None],
                responsibilities=42,
            )
        ],
        profile.id,
    )

    saved = (await session.scalars(select(ProfileExperience))).all()[0]
    assert saved.company == "Контур"
    assert saved.company_url == "https://kontur.ru"
    assert saved.role == "Старший разработчик"
    assert saved.start_date == date(2020, 3, 1)
    assert saved.end_date == date(2023, 6, 30)
    # Пробелы по краям срезаются, а не-список читается как пустой: пункты
    # приходят из формы окна, и уронить сохранение места они не должны.
    assert saved.achievements == ["ускорил сборку"]
    assert saved.responsibilities == []


async def test_a_place_without_an_end_is_still_going(session, session_factory):
    """Место без даты окончания сохраняется как текущее, а не как ошибка."""
    profile = profile_row()
    await put(session_factory, profile)

    await save_experience(session, [_row(end_date="   ")], profile.id)

    saved = (await session.scalars(select(ProfileExperience))).all()[0]
    assert saved.end_date is None


async def test_an_empty_company_url_becomes_absence(session, session_factory):
    """Пустая ссылка на компанию записывается как отсутствие."""
    profile = profile_row()
    await put(session_factory, profile)

    await save_experience(session, [_row(company_url="   ")], profile.id)

    saved = (await session.scalars(select(ProfileExperience))).all()[0]
    assert saved.company_url is None


async def test_named_skills_are_linked_ignoring_case(session, session_factory):
    """Названные навыки привязываются к месту, регистр при этом не важен."""
    profile = profile_row()
    await put(session_factory, profile)
    python = profile_skill_row(profile.id, "Python")
    docker = profile_skill_row(profile.id, "Docker")
    await put(session_factory, python, docker)

    await save_experience(
        session, [_row(skill_names=["PYTHON", "docker"])], profile.id
    )

    got = await list_experience(session)
    assert sorted(s.name for s in got[0].skills) == ["Docker", "Python"]


async def test_two_skills_sharing_one_key_do_not_swallow_each_other(
    session, session_factory
):
    """Из двух навыков с одним ключом сравнения побеждает заведённый первым.

    «Node.js» и «Node JS» сводятся к одному ключу, и раньше место работы
    привязывалось к последнему по номеру строки: пользователь называл один
    навык, а после перечитывания видел другой. Первый — то же правило, что
    у разбора резюме, и оно единственное, которое не зависит от порядка
    выдачи базы.
    """
    profile = profile_row()
    await put(session_factory, profile)
    first = profile_skill_row(profile.id, "Node.js")
    second = profile_skill_row(profile.id, "Node JS")
    await put(session_factory, first, second)

    await save_experience(session, [_row(skill_names=["Node.js"])], profile.id)

    got = await list_experience(session)
    assert [s.name for s in got[0].skills] == ["Node.js"]


async def test_two_names_of_one_skill_link_it_once(session, session_factory):
    """Два названия одного навыка связываются с местом работы один раз.

    «Node.js» и «Node JS» сводятся к одному ключу, а значит и к одной строке
    навыка. Свяжи её дважды — и запись места работы падает на первичном ключе
    связи, унося с собой всю правку вкладки.
    """
    profile = profile_row()
    await put(session_factory, profile)
    await put(session_factory, profile_skill_row(profile.id, "Node.js"))

    await save_experience(
        session, [_row(skill_names=["Node.js", "Node JS"])], profile.id
    )

    got = await list_experience(session)
    assert [s.name for s in got[0].skills] == ["Node.js"]


async def test_an_unknown_skill_name_is_dropped_silently(session, session_factory):
    """Неизвестное имя навыка молча выбрасывается.

    Выбирать навык можно только из уже заведённых, поэтому чужое имя —
    признак рассинхрона экрана, а не повод отменить сохранение.

    Второй заведённый навык, в списке не названный, отличает «связались
    названные» от «связались все подряд».
    """
    profile = profile_row()
    await put(session_factory, profile)
    python = profile_skill_row(profile.id, "Python")
    docker = profile_skill_row(profile.id, "Docker")
    await put(session_factory, python, docker)

    await save_experience(
        session, [_row(skill_names=["Python", "Кобол"])], profile.id
    )

    got = await list_experience(session)
    assert [s.name for s in got[0].skills] == ["Python"]


async def test_saving_an_empty_list_clears_everything(session, session_factory):
    """Пустой список стирает все места работы."""
    profile = profile_row()
    await put(session_factory, profile)
    await put(session_factory, experience_row(profile.id))

    await save_experience(session, [], profile.id)

    assert (await session.scalars(select(ProfileExperience))).all() == []
