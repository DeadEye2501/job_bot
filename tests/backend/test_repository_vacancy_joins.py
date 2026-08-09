"""Следствия отбора в `list_vacancies` по тому, что лежит в соседних таблицах.

Поиск, каналы и компании тянут за собой стыки, а отбор по датам считает
метку активности из четырёх источников. Всё это работает не по колонке
вакансии, и потому вынесено отдельно от отбора по колонкам.
"""

from tests.dbio import put
from tests.factories import (
    at,
    channel_row,
    company_row,
    hr_row,
    vacancy_row,
)


async def test_search_looks_into_every_column_it_promises(titles, session_factory):
    """Поиск заглядывает в каждую названную колонку, а не только в заголовок."""
    await put(
        session_factory,
        vacancy_row(title="needle in the title"),
        vacancy_row(title="по описанию", description="a needle in the body"),
        vacancy_row(title="по сырой компании", company_name="Needle LLC"),
        vacancy_row(title="по заметке", notes="needle later"),
        vacancy_row(title="по зарплате", salary="needle $3000"),
        vacancy_row(title="по грейду", grade="needle senior"),
        vacancy_row(title="по стеку", stack=["needle", "django"]),
        vacancy_row(title="мимо"),
    )

    got = await titles(search="needle")

    assert "мимо" not in got
    assert len(got) == 7


async def test_search_reaches_the_linked_hr_and_company(titles, session_factory):
    """Поиск достаёт вакансию отдельно по имени HR, по его нику и по компании.

    Имя и ник разведены нарочно: с общей подстрокой в обоих потеря любой из
    двух колонок в запросе осталась бы незамеченной — вакансию вытянула бы
    вторая.
    """
    by_name = hr_row(name="Ekaterina", telegram_username="kat_hr")
    by_username = hr_row(name="Olga", telegram_username="volkova_hr")
    company = company_row(name="Romashka")
    await put(session_factory, by_name, by_username, company)
    await put(
        session_factory,
        vacancy_row(title="по имени HR", hr_id=by_name.id),
        vacancy_row(title="по нику HR", hr_id=by_username.id),
        vacancy_row(title="по компании", company_id=company.id),
        vacancy_row(title="мимо"),
    )

    assert await titles(search="ekaterina") == ["по имени HR"]
    assert await titles(search="volkova") == ["по нику HR"]
    assert await titles(search="romash") == ["по компании"]


async def test_search_cannot_find_a_capital_cyrillic_word_at_all(
    titles, session_factory
):
    """Слово с заглавной кириллицы поиском не находится ни в каком написании.

    Регистр опускают обе стороны, и по-разному: питон опускает образец до
    «питон», а `lower()` у SQLite кириллицу не трогает и оставляет в колонке
    «Питон». Совпасть им не на чем, поэтому промахиваются оба написания
    образца. Строчная кириллица находится: опускать в ней нечего.

    Это главный поиск списка вакансий, и русские названия в нём — норма, а
    не исключение. Тест закрепляет сегодняшнее поведение: при починке
    первые две проверки покраснеют.
    """
    await put(
        session_factory,
        vacancy_row(title="Разработчик Питон"),
        vacancy_row(title="разработчик питон"),
    )

    assert await titles(search="Питон") == ["разработчик питон"]
    assert await titles(search="питон") == ["разработчик питон"]


async def test_search_reaches_a_cyrillic_word_inside_the_stack(
    titles, session_factory
):
    """Кириллица в стеке находится поиском, если написана в том же регистре.

    Стек лежит колонкой JSON, и сериализатор по умолчанию экранирует
    не-ASCII: в базе оказывалось `\\u0442\\u0435...` вместо «тестирование».
    Приведение колонки к строке отдавало эту запись как есть, и подстроки
    в ней не было ни в каком регистре.

    Регистр здесь совпадает нарочно: приведение к нижнему у SQLite кириллицу
    не трогает, и «Тестирование» с заглавной по-прежнему не найдётся. Это
    отдельный пункт роадмапы про `func.lower`, и закрывается он не здесь.
    """
    await put(
        session_factory,
        vacancy_row(title="русский стек", stack=["тестирование"]),
        vacancy_row(title="латинский стек", stack=["testing"]),
    )

    assert await titles(search="тестирование") == ["русский стек"]
    assert await titles(search="testing") == ["латинский стек"]


async def test_a_blank_search_is_switched_off_rather_than_matched_as_empty(
    titles, session_factory
):
    """Поиск из одних пробелов выключается, а не превращается в пустой образец.

    Разница видна только на строке, у которой все просматриваемые поиском
    колонки пусты: выключенный поиск её отдаёт, а образец `%%` — нет, потому
    что `NULL LIKE '%%'` в SQL даёт NULL, а не истину. На строке с
    заполненным заголовком оба поведения неразличимы, и тест на ней сторожил
    бы только `.strip()` внутри сборки образца, не саму охрану.
    """
    await put(
        session_factory,
        vacancy_row(title="с заголовком"),
        vacancy_row(title=None),
    )

    assert len(await titles(search="   ")) == 2
    assert len(await titles(search="")) == 2


async def test_a_channel_filter_matches_by_username(titles, session_factory):
    """Отбор по каналу идёт по имени пользователя канала."""
    channel = channel_row(username="pyjobs")
    other = channel_row(username="jsjobs")
    await put(session_factory, channel, other)
    await put(
        session_factory,
        vacancy_row(title="из питона", source_channel_id=channel.id),
        vacancy_row(title="из джаваскрипта", source_channel_id=other.id),
    )

    assert await titles(channels=["pyjobs"]) == ["из питона"]


async def test_a_vacancy_without_a_channel_never_matches_a_channel_filter(
    titles, session_factory
):
    """Вакансия без канала не проходит отбор по каналам ни при каком списке."""
    channel = channel_row(username="pyjobs")
    await put(session_factory, channel)
    await put(
        session_factory,
        vacancy_row(title="с каналом", source_channel_id=channel.id),
        vacancy_row(title="без канала", source_channel_id=None),
    )

    assert await titles(channels=["pyjobs"]) == ["с каналом"]


async def test_a_channel_filter_of_only_blanks_selects_everything(
    titles, session_factory
):
    """Список каналов из одних пустых значений отбор не включает."""
    await put(session_factory, vacancy_row(title="без канала"))

    assert await titles(channels=["", None]) == ["без канала"]


async def test_a_company_filter_matches_both_the_linked_and_the_raw_name(
    titles, session_factory
):
    """Отбор по компании находит и связанную строку, и сырое название."""
    company = company_row(name="Контур")
    await put(session_factory, company)
    await put(
        session_factory,
        vacancy_row(title="привязана", company_id=company.id),
        vacancy_row(title="не привязана", company_name="Контур"),
        vacancy_row(title="мимо", company_name="Другая"),
    )

    got = await titles(companies=["Контур"])

    assert sorted(got) == ["не привязана", "привязана"]


async def test_a_company_filter_is_case_sensitive_on_purpose(titles, session_factory):
    """Отбор по компании сравнивает точно, включая регистр, с обеих сторон.

    Значения выпадающего списка берутся из этих же колонок, поэтому точное
    сравнение попадает всегда, а `lower()` у SQLite промахнулся бы по
    кириллице. Что попадание вообще есть, закрепляет соседний тест; здесь
    предмет — промах в другом регистре, и он проверяется сразу и на
    связанной строке, и на сыром названии.
    """
    company = company_row(name="Контур")
    await put(session_factory, company)
    await put(
        session_factory,
        vacancy_row(title="привязана", company_id=company.id),
        vacancy_row(title="не привязана", company_name="Контур"),
    )

    assert await titles(companies=["контур"]) == []


async def test_a_date_range_cuts_by_the_activity_timestamp(titles, session_factory):
    """Диапазон дат отсекает по метке активности с обеих сторон."""
    await put(
        session_factory,
        vacancy_row(title="рано", created_at=at(0)),
        vacancy_row(title="в окне", created_at=at(60)),
        vacancy_row(title="поздно", created_at=at(120)),
    )

    got = await titles(date_from=at(30), date_to=at(90))

    assert got == ["в окне"]


async def test_a_later_posted_at_moves_the_row_into_the_window(
    titles, session_factory
):
    """Более поздний `posted_at` втягивает строку в окно, хотя создана она раньше."""
    await put(
        session_factory,
        vacancy_row(title="дотянулась", created_at=at(0), posted_at=at(60)),
        vacancy_row(title="осталась снаружи", created_at=at(0), posted_at=None),
    )

    assert await titles(date_from=at(30)) == ["дотянулась"]
