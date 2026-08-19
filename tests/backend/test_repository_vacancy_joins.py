"""Следствия отбора в `list_vacancies` по тому, что лежит в соседних таблицах.

Поиск, каналы и компании тянут за собой стыки, а отбор по датам считает
метку активности из четырёх источников. Всё это работает не по колонке
вакансии, и потому вынесено отдельно от отбора по колонкам.

Список вариантов фильтра проверяется своим файлом; здесь его зовут лишь
затем, чтобы отбор сверялся с тем, что окно действительно предлагает.
"""

from backend.repository.vacancies_list import list_vacancy_filter_options
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


async def test_search_finds_a_cyrillic_word_in_either_case(titles, session_factory):
    """Слово с заглавной кириллицы находится любым написанием образца.

    Регистр опускают обе стороны, и раньше по-разному: питон опускал образец
    до «питон», а `lower()` у SQLite кириллицу не трогал и оставлял в колонке
    «Питон». Совпасть им было не на чем, и вакансия с русским названием не
    находилась ни одним написанием образца — при том, что это главный поиск
    списка вакансий, а русские названия в нём норма.
    """
    await put(
        session_factory,
        vacancy_row(title="Разработчик Питон"),
        vacancy_row(title="разработчик питон"),
        vacancy_row(title="Разработчик Джава"),
    )

    both = ["Разработчик Питон", "разработчик питон"]
    assert sorted(await titles(search="Питон")) == both
    assert sorted(await titles(search="питон")) == both


async def test_search_reaches_a_cyrillic_word_inside_the_stack(
    titles, session_factory
):
    """Кириллица в стеке находится поиском, если написана в том же регистре.

    Стек лежит колонкой JSON, и сериализатор по умолчанию экранирует
    не-ASCII: в базе оказывалось `\\u0442\\u0435...` вместо «тестирование».
    Приведение колонки к строке отдавало эту запись как есть, и подстроки
    в ней не было ни в каком регистре.

    Названия навыков записываются с заглавной, поэтому регистр здесь ещё и
    складывается — и складывается на стороне базы, через `cast` колонки к
    строке. Другой такой искомой колонки нет: остальные приходят к
    приведению регистра сами.
    """
    await put(
        session_factory,
        vacancy_row(title="русский стек", stack=["Тестирование"]),
        vacancy_row(title="латинский стек", stack=["Testing"]),
    )

    assert await titles(search="тестирование") == ["русский стек"]
    assert await titles(search="testing") == ["латинский стек"]


async def test_a_percent_in_the_search_is_a_letter_not_a_wildcard(
    titles, session_factory
):
    """Процент в строке поиска ищется как знак, а не как «что угодно».

    Незакрытым он превращает любой запрос в «выдать всё»: человек набирает
    «50%», а получает всю базу и решает, что поиск сломан.
    """
    await put(
        session_factory,
        vacancy_row(title="с процентом", salary="бонус 50% от оклада"),
        vacancy_row(title="без процента", salary="200000"),
    )

    assert await titles(search="50%") == ["с процентом"]
    assert await titles(search="%") == ["с процентом"]


async def test_an_underscore_in_the_search_is_a_letter_too(titles, session_factory):
    """Подчёркивание в строке поиска ищется как знак, а не как «любая буква».

    В никах Telegram оно попадается через раз, и без обезвреживания «job_bot»
    находит ещё и «jobXbot».
    """
    await put(
        session_factory,
        vacancy_row(title="с подчёркиванием", notes="канал job_bot"),
        vacancy_row(title="без подчёркивания", notes="канал jobXbot"),
    )

    assert await titles(search="job_bot") == ["с подчёркиванием"]


async def test_a_percent_in_the_grade_filter_is_a_letter_too(
    titles, session_factory
):
    """Отбор по грейду и формату держится того же правила, что и поиск.

    Строку туда кладёт то же окно, и знак образца в ней значит ровно то же
    самое: ничего.
    """
    await put(
        session_factory,
        vacancy_row(title="со знаком", grade="senior%"),
        vacancy_row(title="без знака", grade="senior"),
    )

    assert await titles(grade="senior%") == ["со знаком"]


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


async def test_a_company_option_finds_every_spelling_it_was_folded_from(
    titles, session, session_factory
):
    """Вариант из выпадающего списка находит все написания, что в него слились.

    Список сводит «Контур» и «контур» в одну строку и показывает первое
    встреченное написание. Сравнивай отбор точно — вакансия со вторым
    написанием молча выпадала бы из выдачи, и добраться до неё через фильтр
    было бы нельзя вовсе: её собственного написания список не предлагает.
    """
    company = company_row(name="Контур")
    await put(session_factory, company)
    await put(
        session_factory,
        vacancy_row(title="привязана", company_id=company.id),
        vacancy_row(title="сырое строчное", company_name="контур"),
        vacancy_row(title="мимо", company_name="Ромашка"),
    )
    both = ["привязана", "сырое строчное"]

    options = await list_vacancy_filter_options(session)
    assert sorted(options["companies"]) == ["Контур", "Ромашка"]

    assert sorted(await titles(companies=["Контур"])) == both
    # Написание, которого нет ни в одной колонке: регистр обязаны складывать
    # обе стороны сравнения. Какое из двух написаний попадёт в список,
    # решает порядок выдачи базы, и опираться на него нельзя.
    assert sorted(await titles(companies=["КОНТУР"])) == both


async def test_a_company_option_finds_the_name_with_edges_it_was_trimmed_of(
    titles, session, session_factory
):
    """Вариант из списка находит название и с пробелами по краям.

    Список обрезает края, а отбор сравнивал как есть: название, приехавшее
    из поста с висячим пробелом, показывалось в списке подстриженным и не
    находило собственную вакансию. Своего написания список не предлагает, и
    добраться до неё через фильтр было нельзя вовсе.
    """
    await put(
        session_factory,
        vacancy_row(title="с пробелом", company_name="Контур "),
        vacancy_row(title="с переносом", company_name="\nКонтур"),
        vacancy_row(title="с неразрывным", company_name="Контур\u00a0"),
        vacancy_row(title="мимо", company_name="Ромашка"),
    )

    options = await list_vacancy_filter_options(session)
    assert sorted(options["companies"]) == ["Контур", "Ромашка"]

    assert sorted(await titles(companies=["Контур"])) == sorted(
        ["с пробелом", "с переносом", "с неразрывным"]
    )


async def test_a_channel_option_finds_every_spelling_it_was_folded_from(
    titles, session, session_factory
):
    """То же у каналов: одна строка списка находит оба написания имени.

    Имя канала в Telegram регистронезависимо, и «@PyJobs» с «@pyjobs» — один
    и тот же канал. Отбор обязан складывать регистр с обеих сторон: своё
    написание одна из двух строк справочника в списке не получает.
    """
    upper = channel_row(username="PyJobs")
    lower = channel_row(username="pyjobs")
    other = channel_row(username="jsjobs")
    await put(session_factory, upper, lower, other)
    await put(
        session_factory,
        vacancy_row(title="через заглавное", source_channel_id=upper.id),
        vacancy_row(title="через строчное", source_channel_id=lower.id),
        vacancy_row(title="мимо", source_channel_id=other.id),
    )
    both = ["через заглавное", "через строчное"]

    options = await list_vacancy_filter_options(session)
    assert len(options["channels"]) == 2

    assert sorted(await titles(channels=["PYJOBS"])) == both
    assert sorted(await titles(channels=["pyjobs"])) == both


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
