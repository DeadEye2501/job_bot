"""Следствия отбора в `list_vacancies` по колонкам самой вакансии.

Фильтры складываются через И, и каждый тест держит включённым ровно один:
остальные оставлены пустыми, чтобы отобранное объяснялось единственной
причиной.
"""

from backend.models import VacancyStatus
from tests.dbio import put
from tests.factories import at, hr_row, vacancy_row


async def test_an_unparsed_vacancy_never_reaches_the_list(titles, session_factory):
    """Недоразобранная вакансия в список не попадает."""
    await put(
        session_factory,
        vacancy_row(title="разобрана", is_parsed=True),
        vacancy_row(title="брошена на полпути", is_parsed=False),
    )

    assert await titles() == ["разобрана"]


async def test_a_status_filter_keeps_only_the_named_statuses(titles, session_factory):
    """Отбор по статусу оставляет только названные."""
    await put(
        session_factory,
        vacancy_row(title="новая", status=VacancyStatus.NEW),
        vacancy_row(title="в работе", status=VacancyStatus.IN_PROGRESS),
        vacancy_row(title="отказ", status=VacancyStatus.DECLINE),
    )

    got = await titles(statuses=["in-progress", "decline"])

    assert sorted(got) == ["в работе", "отказ"]


async def test_an_unknown_status_code_is_dropped_without_dropping_the_filter(
    titles, session_factory
):
    """Неизвестный код статуса отбрасывается, известный рядом продолжает работать."""
    await put(
        session_factory,
        vacancy_row(title="новая", status=VacancyStatus.NEW),
        vacancy_row(title="отказ", status=VacancyStatus.DECLINE),
    )

    assert await titles(statuses=["decline", "выдумка"]) == ["отказ"]


async def test_a_filter_of_only_unknown_codes_selects_everything(
    titles, session_factory
):
    """Отбор целиком из неизвестных кодов не отбирает ничего — выдаётся всё.

    Ветка «список кодов был, но после отсева пуст» не добавляет условия
    вовсе, и пользователь получает список без фильтра вместо пустого.
    """
    await put(
        session_factory,
        vacancy_row(title="новая", status=VacancyStatus.NEW),
        vacancy_row(title="отказ", status=VacancyStatus.DECLINE),
    )

    assert sorted(await titles(statuses=["выдумка"])) == ["новая", "отказ"]


async def test_a_score_range_excludes_both_ends_beyond_it(titles, session_factory):
    """Диапазон баллов отсекает и то, что ниже, и то, что выше."""
    await put(
        session_factory,
        vacancy_row(title="слабая", score=20),
        vacancy_row(title="в самый раз", score=60),
        vacancy_row(title="сильная", score=90),
    )

    assert await titles(score_min=50, score_max=80) == ["в самый раз"]


async def test_the_score_range_includes_both_of_its_own_ends(
    titles, session_factory
):
    """Вакансия ровно на границе диапазона в отбор попадает, с обеих сторон.

    Проверено мутацией: без этого теста замена нестрогого сравнения на
    строгое проходила молча — все прочие наборы держали баллы в стороне от
    границ, и разницы между «не меньше» и «больше» не возникало.
    """
    await put(
        session_factory,
        vacancy_row(title="ровно снизу", score=50),
        vacancy_row(title="ровно сверху", score=80),
        vacancy_row(title="на волос ниже", score=49),
        vacancy_row(title="на волос выше", score=81),
    )

    got = await titles(score_min=50, score_max=80)

    assert sorted(got) == sorted(["ровно снизу", "ровно сверху"])


async def test_a_vacancy_without_a_score_never_matches_a_score_range(
    titles, session_factory
):
    """Вакансия без балла не проходит отбор по баллам ни с какой границей."""
    await put(
        session_factory,
        vacancy_row(title="без балла", score=None),
        vacancy_row(title="с баллом", score=60),
    )

    assert await titles(score_min=0) == ["с баллом"]
    assert await titles(score_max=100) == ["с баллом"]


async def test_a_grade_filter_matches_a_substring_regardless_of_case(
    titles, session_factory
):
    """Отбор по грейду ищет подстроку и не различает регистр латиницы."""
    await put(
        session_factory,
        vacancy_row(title="старшая", grade="Senior Python"),
        vacancy_row(title="младшая", grade="Junior"),
    )

    assert await titles(grade="senior") == ["старшая"]


async def test_a_remote_filter_matches_a_substring(titles, session_factory):
    """Отбор по удалённости ищет подстроку."""
    await put(
        session_factory,
        vacancy_row(title="удалённая", remote="Remote (worldwide)"),
        vacancy_row(title="офисная", remote="Office"),
    )

    assert await titles(remote="remote") == ["удалённая"]


async def test_hr_contact_with_and_without_split_the_list_in_two(
    titles, session_factory
):
    """«С контактом» и «без контакта» делят список надвое без пересечения."""
    hr = hr_row()
    await put(session_factory, hr)
    await put(
        session_factory,
        vacancy_row(title="есть HR", hr_id=hr.id),
        vacancy_row(title="нет HR", hr_id=None),
    )

    assert await titles(hr_contact="with") == ["есть HR"]
    assert await titles(hr_contact="without") == ["нет HR"]


async def test_an_unrecognised_hr_contact_value_filters_nothing(
    titles, session_factory
):
    """Неизвестное значение контакта HR не отсекает ни одну из двух сторон.

    Набор нарочно из двух строк по разные стороны фильтра: на одной
    «фильтр не включился» и «фильтр совпал со всем» дали бы один ответ.
    """
    hr = hr_row()
    await put(session_factory, hr)
    await put(
        session_factory,
        vacancy_row(title="есть HR", hr_id=hr.id),
        vacancy_row(title="нет HR", hr_id=None),
    )

    assert sorted(await titles(hr_contact="all")) == ["есть HR", "нет HR"]
    assert sorted(await titles(hr_contact=None)) == ["есть HR", "нет HR"]


async def test_a_limit_cuts_the_page_and_an_offset_moves_it(titles, session_factory):
    """Предел режет страницу, смещение сдвигает её по тому же порядку."""
    await put(
        session_factory,
        vacancy_row(title="первая", created_at=at(30)),
        vacancy_row(title="вторая", created_at=at(20)),
        vacancy_row(title="третья", created_at=at(10)),
    )

    assert await titles(limit=2) == ["первая", "вторая"]
    assert await titles(limit=2, offset=1) == ["вторая", "третья"]


async def test_an_unknown_sort_key_falls_back_to_newest(titles, session_factory):
    """Неизвестный ключ сортировки заменяется на «сначала новые»."""
    await put(
        session_factory,
        vacancy_row(title="старая", created_at=at(10)),
        vacancy_row(title="свежая", created_at=at(20)),
    )

    assert await titles(sort="по-своему") == ["свежая", "старая"]
