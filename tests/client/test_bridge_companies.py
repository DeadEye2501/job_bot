"""Следствия слотов компании: перечень, карточка, написания, слияние, заслон.

Предмет — карточка компании целиком. Связывание вакансии с компанией лежит с
вакансиями: там его делают из другого окна и по другому поводу.
"""

import json

from tests.dbio import put
from tests.factories import company_row, hr_row, vacancy_row


async def test_the_list_counts_vacancies_and_marks_the_blacklisted(
    main_api, watch, session_factory
):
    """Строка перечня несёт счёт вакансий и отметку заслона.

    По ним в перечне и решают, к кому идти: компания с пятью вакансиями и
    компания, мелькнувшая однажды, — разные, а огороженная не нужна вовсе.
    """
    caught = watch(main_api.contacts_company_list_loaded)
    company = company_row(name="Контур")
    await put(session_factory, company)
    await put(session_factory, vacancy_row(company_id=company.id))

    main_api.request_contacts_company_list(json.dumps({}))

    row = (await caught.next())["companies"][0]
    assert row["vacancy_count"] == 1
    assert row["is_blacklisted"] is False


async def test_a_card_of_a_missing_company_is_refused_with_the_number(main_api, watch):
    """На пропавшую компанию отвечают отказом с её номером.

    Карточку открывают из перечня, а тот мог устареть. Без номера окно не
    поймёт, какую строку убирать с экрана.
    """
    caught = watch(main_api.contacts_company_detail_loaded)

    main_api.request_contacts_company_detail(404)

    answer = await caught.next()
    assert answer["ok"] is False
    assert answer["company_id"] == 404


async def test_spellings_typed_in_one_line_arrive_as_a_list(
    main_api, watch, session_factory
):
    """Написания, набранные строкой через запятую, приезжают списком.

    В форме их набирают одной строкой, а сверяют по одному: одна компания
    называется в объявлениях и «Контур», и «СКБ Контур». Останься это
    строкой — сверка искала бы целиком её, и не совпало бы ни одно.
    """
    done = watch(main_api.contacts_company_action_done)
    shown = watch(main_api.contacts_company_detail_loaded)

    main_api.contacts_create_company(
        json.dumps({"name": "Контур", "aliases": "СКБ Контур, Контур.ру,  "})
    )
    answer = await done.next()
    assert answer["ok"] is True

    main_api.request_contacts_company_detail(answer["created_id"])
    assert (await shown.next())["aliases"] == ["СКБ Контур", "Контур.ру"]


async def test_a_taken_name_is_named_as_taken(main_api, watch, session_factory):
    """Занятое название объясняют словами, а не отказом базы.

    Компании с одинаковым именем считаются одной — это решение записано в
    плане бэкенда. Человек, заводящий вторую, должен узнать про первую.
    """
    caught = watch(main_api.contacts_company_action_done)
    await put(session_factory, company_row(name="Контур"))

    main_api.contacts_create_company(json.dumps({"name": "Контур"}))

    answer = await caught.next()
    assert answer["ok"] is False
    assert "Контур" in answer["error"]


async def test_spellings_of_a_wrong_shape_are_refused_before_the_base(
    main_api, watch, session_factory
):
    """Написания не того вида отбивают до базы, назвав годные виды.

    Форма шлёт то строку, то список — а число или словарь означают, что окно
    и мост разошлись. Молчаливое приведение стёрло бы все написания разом.
    """
    caught = watch(main_api.contacts_company_action_done)
    company = company_row(name="Контур")
    await put(session_factory, company)

    main_api.contacts_update_company(
        json.dumps({"company_id": company.id, "aliases": 42})
    )

    answer = await caught.next()
    assert answer["ok"] is False
    assert answer["error"] == "aliases должен быть list или строка через запятую."


async def test_an_update_without_fields_says_there_is_nothing_to_do(
    main_api, watch, session_factory
):
    """Правку без единого поля отбивают: сохранять нечего.

    Форму отправляют и не тронув в ней ничего. Ответь мост успехом — окно
    показало бы «сохранено» там, где не сохранялось ничего.
    """
    caught = watch(main_api.contacts_company_action_done)
    company = company_row(name="Контур")
    await put(session_factory, company)

    main_api.contacts_update_company(json.dumps({"company_id": company.id}))

    answer = await caught.next()
    assert answer["ok"] is False
    assert answer["error"] == "Нечего обновлять."


async def test_only_this_company_vacancies_are_shown(main_api, watch, session_factory):
    """В карточке видны вакансии только этой компании.

    Список читают, решая, стоит ли иметь с ней дело: пять вакансий за месяц и
    одна за год говорят разное. Попади туда чужая — счёт стал бы враньём, а
    разговор начался бы с вакансии, которой эта компания не давала.
    """
    caught = watch(main_api.contacts_company_vacancies_loaded)
    mine = company_row(name="Контур")
    other = company_row(name="Рога")
    await put(session_factory, mine, other)
    await put(
        session_factory,
        vacancy_row(title="Моя", company_id=mine.id),
        vacancy_row(title="Чужая", company_id=other.id),
    )

    main_api.request_contacts_company_vacancies(json.dumps({"company_id": mine.id}))

    titles = [row["title"] for row in (await caught.next())["vacancies"]]
    assert titles == ["Моя"]


async def test_the_people_of_a_company_are_found_through_its_vacancies(
    main_api, watch, session_factory
):
    """Люди компании находятся через её вакансии, а не через свою ссылку.

    Прямой связи «HR — компания» в записях нет: человек привязан к вакансии,
    вакансия — к компании. Пропади этот переход, карточка компании осталась
    бы без единого собеседника.
    """
    caught = watch(main_api.contacts_company_hrs_loaded)
    company = company_row(name="Контур")
    hr = hr_row(name="Мария")
    await put(session_factory, company, hr)
    await put(session_factory, vacancy_row(company_id=company.id, hr_id=hr.id))

    main_api.request_contacts_company_hrs(company.id)

    assert [row["name"] for row in (await caught.next())["hrs"]] == ["Мария"]


async def test_the_absorbed_company_is_not_offered_as_its_own_survivor(
    main_api, watch, session_factory
):
    """Поглощаемой компании не предлагают слиться с самой собой.

    Оставшуюся выбирают из общего перечня, и попади туда она же — человек
    выбрал бы её не глядя, а слияние отбилось бы отказом на ровном месте.
    """
    caught = watch(main_api.contacts_company_merge_picker_loaded)
    absorbed = company_row(name="Контур")
    survivor = company_row(name="СКБ Контур")
    await put(session_factory, absorbed, survivor)

    main_api.request_contacts_company_merge_picker(
        json.dumps({"absorbed_id": absorbed.id})
    )

    offered = [row["id"] for row in (await caught.next())["companies"]]
    assert offered == [survivor.id]


async def test_merging_moves_vacancies_and_keeps_the_old_name_as_a_spelling(
    main_api, watch, session_factory
):
    """Слияние переносит вакансии и сохраняет прежнее имя написанием.

    Имя поглощённой продолжает приходить в новых объявлениях — источник о
    слиянии не знает. Потеряй его карточка, следующая вакансия завела бы
    компанию заново, и разнобой вернулся бы.
    """
    done = watch(main_api.contacts_company_action_done)
    shown = watch(main_api.contacts_company_detail_loaded)
    listed = watch(main_api.contacts_company_vacancies_loaded)
    survivor = company_row(name="Контур")
    absorbed = company_row(name="СКБ Контур")
    await put(session_factory, survivor, absorbed)
    await put(session_factory, vacancy_row(title="Из второй", company_id=absorbed.id))

    main_api.contacts_merge_company(
        json.dumps({"absorbed_id": absorbed.id, "survivor_id": survivor.id})
    )
    assert (await done.next())["ok"] is True

    main_api.request_contacts_company_detail(survivor.id)
    assert "СКБ Контур" in (await shown.next())["aliases"]

    main_api.request_contacts_company_vacancies(json.dumps({"company_id": survivor.id}))
    titles = [row["title"] for row in (await listed.next())["vacancies"]]
    assert titles == ["Из второй"]


async def test_merging_a_company_into_itself_is_refused(
    main_api, watch, session_factory
):
    """Слияние карточки с самой собой отбивают.

    Пройди оно — карточка поглотила бы себя, и что стало бы с её вакансиями
    и написаниями, не сказал бы никто.
    """
    caught = watch(main_api.contacts_company_action_done)
    company = company_row(name="Контур")
    await put(session_factory, company)

    main_api.contacts_merge_company(
        json.dumps({"absorbed_id": company.id, "survivor_id": company.id})
    )

    assert (await caught.next())["ok"] is False


async def test_a_deleted_company_leaves_the_list(main_api, watch, session_factory):
    """Удалённая компания исчезает из перечня, а не только получает ответ."""
    done = watch(main_api.contacts_company_action_done)
    listed = watch(main_api.contacts_company_list_loaded)
    company = company_row(name="Контур")
    await put(session_factory, company)

    main_api.contacts_delete_company(company.id)
    assert (await done.next())["ok"] is True

    main_api.request_contacts_company_list(json.dumps({}))
    assert (await listed.next())["companies"] == []


async def test_blacklisting_a_company_writes_its_name(
    main_api, watch, session_factory
):
    """Заслон компании ставится по имени — другого значения у неё нет.

    У человека есть ник и номер учётной записи, у компании только имя, и
    именно его сверяет заслон отправки. В ответ оно приходит затем, чтобы
    карточка показала, по чему именно поставлен заслон.
    """
    done = watch(main_api.contacts_company_action_done)
    shown = watch(main_api.contacts_company_detail_loaded)
    company = company_row(name="Контур")
    await put(session_factory, company)

    main_api.contacts_add_company_to_blacklist(company.id)
    answer = await done.next()
    assert answer["value"] == "Контур"
    assert answer["existed"] is False

    main_api.request_contacts_company_detail(company.id)
    assert (await shown.next())["blacklist_value"] == "Контур"


async def test_removing_a_company_blacklist_clears_the_card(
    main_api, watch, session_factory
):
    """Снятый заслон виден в карточке: значения там больше нет."""
    done = watch(main_api.contacts_company_action_done)
    shown = watch(main_api.contacts_company_detail_loaded)
    company = company_row(name="Контур")
    await put(session_factory, company)

    main_api.contacts_add_company_to_blacklist(company.id)
    await done.next()

    main_api.contacts_remove_company_from_blacklist(company.id)
    assert (await done.next())["updated"] == 1

    main_api.request_contacts_company_detail(company.id)
    assert (await shown.next())["blacklist_value"] is None
