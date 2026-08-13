"""Следствия связывания вакансии с HR и компанией — вместе с подборщиками.

Предмет отделён от чтения вакансии: здесь окно не показывает вакансию, а
привязывает к ней чужую карточку, и заводит недостающую прямо из подборщика.
"""

import json

from tests.dbio import put
from tests.factories import company_row, hr_row, vacancy_row


async def test_the_picker_says_which_hr_is_linked_right_now(
    main_api, watch, session_factory
):
    """Подборщик приезжает вместе с уже связанным, а не одним списком.

    Окно отмечает им нынешний выбор. Не приди он — человек не увидел бы,
    к кому вакансия привязана, и связал бы её заново с тем же самым.
    """
    caught = watch(main_api.hr_picker_loaded)
    hr = hr_row(name="Мария")
    await put(session_factory, hr)
    vacancy = vacancy_row(hr_id=hr.id)
    await put(session_factory, vacancy)

    main_api.request_hr_picker(json.dumps({"vacancy_id": vacancy.id}))

    answer = await caught.next()
    assert answer["current_hr_id"] == hr.id
    assert [row["name"] for row in answer["hrs"]] == ["Мария"]


async def test_a_picker_for_a_missing_vacancy_is_refused(main_api, watch):
    """Подборщик к пропавшей вакансии не открывается.

    Открывают его из карточки, а карточка могла устареть. Отдай мост список
    молча — человек выбрал бы HR, и связывать его было бы уже не с чем.
    """
    caught = watch(main_api.company_picker_loaded)

    main_api.request_company_picker(json.dumps({"vacancy_id": 404}))

    answer = await caught.next()
    assert answer["ok"] is False
    assert answer["vacancy_id"] == 404


async def test_a_linked_hr_shows_up_in_the_list_row(main_api, watch, session_factory):
    """Связанный HR виден в строке списка, а не только в ответе на связывание.

    Строка показывает имя и ник того, с кем переписываться. Останься связь
    только в ответе — список после перерисовки показал бы вакансию ничьей.
    """
    done = watch(main_api.vacancy_action_done)
    listed = watch(main_api.vacancies_changed)
    hr = hr_row(name="Мария", telegram_username="maria")
    await put(session_factory, hr)
    vacancy = vacancy_row()
    await put(session_factory, vacancy)

    main_api.link_vacancy_hr(json.dumps({"vacancy_id": vacancy.id, "hr_id": hr.id}))
    answer = await done.next()
    assert answer["ok"] is True
    assert answer["action"] == "link_hr"

    main_api.request_vacancies()
    row = (await listed.next())["vacancies"][0]
    assert row["hr_name"] == "Мария"
    assert row["hr_username"] == "maria"


async def test_a_linked_company_replaces_the_raw_name_in_the_row(
    main_api, watch, session_factory
):
    """После связывания в строке появляется имя компании, а не из объявления.

    Ради этого связывание и делают: одна компания под пятью написаниями
    перестаёт выглядеть пятью разными.
    """
    done = watch(main_api.vacancy_action_done)
    listed = watch(main_api.vacancies_changed)
    company = company_row(name="Контур")
    await put(session_factory, company)
    vacancy = vacancy_row(company_name="ООО «Рога»")
    await put(session_factory, vacancy)

    main_api.link_vacancy_company(
        json.dumps({"vacancy_id": vacancy.id, "company_id": company.id})
    )
    assert (await done.next())["ok"] is True

    main_api.request_vacancies()
    assert (await listed.next())["vacancies"][0]["company"] == "Контур"


async def test_an_hr_without_a_name_and_without_a_nick_is_refused(
    main_api, watch, session_factory
):
    """Карточку HR не заводят пустой.

    Заводят её прямо из подборщика, на ходу, — и карточка без имени и без
    ника не отличима от любой другой: следующий раз человек завёл бы вторую
    такую же вместо того, чтобы найти эту.
    """
    caught = watch(main_api.hr_picker_loaded)
    vacancy = vacancy_row()
    await put(session_factory, vacancy)

    main_api.request_hr_picker(json.dumps({"vacancy_id": vacancy.id}))
    await caught.next()

    main_api.picker_create_hr(
        json.dumps({"vacancy_id": vacancy.id, "name": "  ", "notes": "без имени"})
    )

    answer = await caught.next()
    assert answer["ok"] is False
    assert answer["error"] == "Укажите хотя бы имя или @username."


async def test_a_created_hr_comes_back_named_and_listed(
    main_api, watch, session_factory
):
    """Заведённый HR приходит и номером, и строкой в списке.

    Номер окно ставит выбранным сразу, не переспрашивая; список тем же
    ответом обновляется. Приди одно без другого — выбор указывал бы на
    карточку, которой в списке нет.
    """
    caught = watch(main_api.hr_picker_loaded)
    vacancy = vacancy_row()
    await put(session_factory, vacancy)

    main_api.picker_create_hr(
        json.dumps({"vacancy_id": vacancy.id, "name": "Пётр", "telegram_username": "petr"})
    )

    answer = await caught.next()
    assert answer["created_id"] is not None
    assert answer["created_id"] in [row["id"] for row in answer["hrs"]]


async def test_a_company_without_a_name_is_refused(main_api, watch, session_factory):
    """Компанию без названия не заводят: искать её потом будет нечем."""
    caught = watch(main_api.company_picker_loaded)
    vacancy = vacancy_row()
    await put(session_factory, vacancy)

    main_api.picker_create_company(json.dumps({"vacancy_id": vacancy.id, "name": "   "}))

    answer = await caught.next()
    assert answer["ok"] is False
    assert answer["error"] == "Название обязательно."


async def test_a_second_company_with_the_same_name_is_named_as_existing(
    main_api, watch, session_factory
):
    """О занятом названии говорят словами, а не поломкой записи.

    Компании с одинаковым именем считаются одной — это решение записано в
    плане бэкенда. Человек, заводящий вторую, должен узнать, что первая уже
    есть, а не увидеть отказ базы.
    """
    caught = watch(main_api.company_picker_loaded)
    await put(session_factory, company_row(name="Контур"))
    vacancy = vacancy_row()
    await put(session_factory, vacancy)

    main_api.picker_create_company(
        json.dumps({"vacancy_id": vacancy.id, "name": "Контур"})
    )

    answer = await caught.next()
    assert answer["ok"] is False
    assert "Контур" in answer["error"]
