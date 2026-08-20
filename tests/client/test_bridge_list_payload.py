"""Следствия чтения нагрузки списка — той, что четыре экрана шлют одинаково.

Вакансии, люди, компании и каналы просят страницу одними и теми же полями:
строка поиска, выбранное в фильтрах, потолок и сдвиг. Пока каждый слот читал
их сам, написания разъехались — и разъехались молча: окно шлёт одно и то же, а
получает разное.
"""

from tests.dbio import put
from tests.factories import company_row, vacancy_row


async def test_a_filter_value_with_stray_spaces_still_finds_the_vacancy(
    api, ask, session_factory
):
    """Выбранное в фильтре с пробелом по краям всё равно находит вакансию.

    Отбор сравнивает написание точно, и пробел, прилипший при вставке из
    буфера, не совпадает ни с чем: человек видит пустой список там, где
    вакансия есть, и понять по экрану, что дело в невидимом знаке, нельзя.
    """
    company = company_row(name="Контур")
    await put(session_factory, company)
    await put(session_factory, vacancy_row(company_id=company.id, title="Питонист"))

    answer = await ask(api.vacancies.list, {"companies": [" Контур "]})

    titles = [row["title"] for row in answer["ok"]["vacancies"]]
    assert titles == ["Питонист"]


async def test_a_single_choice_filter_with_stray_spaces_still_matches(
    api, ask, session_factory
):
    """Одиночный выбор с пробелом по краям находит вакансию так же, как список.

    Грейд, формат работы и наличие HR приходят из тех же полей окна, что и
    списки выбранного, и правило у них одно. Разойдись оно — человек, вставив
    значение из буфера, увидел бы пустой экран на одном фильтре и полный на
    соседнем, ничем эти два случая не различая.
    """
    await put(session_factory, vacancy_row(title="Питонист", grade="Junior"))

    answer = await ask(api.vacancies.list, {"grade": " Junior "})

    titles = [row["title"] for row in answer["ok"]["vacancies"]]
    assert titles == ["Питонист"]


async def test_a_page_asked_beyond_the_ceiling_comes_back_cut(
    api, ask, session_factory
):
    """Страница сверх потолка режется, и окну говорят, что есть продолжение.

    Потолок стоит на границе затем, что отбор дочитывает строки питоном:
    негодная нагрузка с запросом на миллион строк прошла бы его целиком.
    Не скажи мосту про продолжение — окно решит, что показало всё, и
    остальные строки не покажет никогда.
    """
    await put(
        session_factory, *[vacancy_row(title=f"Вакансия {i}") for i in range(201)]
    )

    answer = await ask(api.vacancies.list, {"limit": 1000})

    assert len(answer["ok"]["vacancies"]) == 200
    assert answer["ok"]["has_more"] is True
