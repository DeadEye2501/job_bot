"""Следствия чтения нагрузки списка — той, что четыре экрана шлют одинаково.

Вакансии, люди, компании и каналы просят страницу одними и теми же полями:
строка поиска, выбранное в фильтрах, потолок, сдвиг, режим и порядковый знак.
Пока каждый слот читал их сам, написания разъехались — и разъехались молча:
окно шлёт одно и то же, а получает разное.
"""

import json

from tests.dbio import put
from tests.factories import company_row, hr_row, vacancy_row


async def test_a_filter_value_with_stray_spaces_still_finds_the_vacancy(
    main_api, watch, session_factory
):
    """Выбранное в фильтре с пробелом по краям всё равно находит вакансию.

    Отбор сравнивает написание точно, и пробел, прилипший при вставке из
    буфера, не совпадает ни с чем: человек видит пустой список там, где
    вакансия есть, и понять по экрану, что дело в невидимом знаке, нельзя.
    """
    caught = watch(main_api.vacancies_changed)
    company = company_row(name="Контур")
    await put(session_factory, company)
    await put(session_factory, vacancy_row(company_id=company.id, title="Питонист"))

    main_api.request_vacancies(json.dumps({"companies": [" Контур "]}))

    titles = [row["title"] for row in (await caught.next())["vacancies"]]
    assert titles == ["Питонист"]


async def test_a_single_choice_filter_with_stray_spaces_still_matches(
    main_api, watch, session_factory
):
    """Одиночный выбор с пробелом по краям находит вакансию так же, как список.

    Грейд, формат работы и наличие HR приходят из тех же полей окна, что и
    списки выбранного, и правило у них одно. Разойдись оно — человек, вставив
    значение из буфера, увидел бы пустой экран на одном фильтре и полный на
    соседнем, ничем эти два случая не различая.
    """
    caught = watch(main_api.vacancies_changed)
    await put(session_factory, vacancy_row(title="Питонист", grade="Junior"))

    main_api.request_vacancies(json.dumps({"grade": " Junior "}))

    titles = [row["title"] for row in (await caught.next())["vacancies"]]
    assert titles == ["Питонист"]


async def test_the_request_ordinal_comes_back_as_a_number(
    main_api, watch, session_factory
):
    """Порядковый знак возвращается числом, каким бы ни пришёл.

    Окно узнаёт свой ответ строгим сравнением знака. Вернись он строкой — ни
    один ответ не совпал бы со своим запросом, и список вакансий компании
    остался бы пустым навсегда.
    """
    caught = watch(main_api.contacts_company_vacancies_loaded)
    company = company_row(name="Контур")
    await put(session_factory, company)

    main_api.request_contacts_company_vacancies(
        json.dumps({"company_id": company.id, "epoch": "7"})
    )

    assert (await caught.next())["epoch"] == 7


async def test_an_unknown_chat_mode_comes_back_as_the_first_one(
    main_api, watch, session_factory
):
    """Незнакомый режим переписки схлопывается в «свежие», а не едет эхом.

    По этому слову окно решает, дописать пришедшее к показанному сверху или
    заменить показанное целиком. Опечатка, вернувшаяся как есть, читается им
    как замена — и уже догруженная история переписки пропадает с экрана.
    """
    caught = watch(main_api.contacts_hr_messages_loaded)
    hr = hr_row(name="Иван")
    await put(session_factory, hr)

    main_api.request_contacts_hr_messages(
        json.dumps({"hr_id": hr.id, "mode": "как-нибудь"})
    )

    assert (await caught.next())["mode"] == "tail"


async def test_a_page_asked_beyond_the_ceiling_comes_back_cut(
    main_api, watch, session_factory
):
    """Страница сверх потолка режется, и окну говорят, что есть продолжение.

    Потолок стоит на границе затем, что отбор дочитывает строки питоном:
    негодная нагрузка с запросом на миллион строк прошла бы его целиком.
    Не скажи мосту про продолжение — окно решит, что показало всё, и
    остальные строки не покажет никогда.
    """
    caught = watch(main_api.vacancies_changed)
    await put(
        session_factory, *[vacancy_row(title=f"Вакансия {i}") for i in range(201)]
    )

    main_api.request_vacancies(json.dumps({"limit": 1000}))

    answer = await caught.next()
    assert len(answer["vacancies"]) == 200
    assert answer["has_more"] is True
