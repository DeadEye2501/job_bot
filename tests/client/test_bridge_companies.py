"""Следствия домена компании: перечень, карточка, написания, слияние, заслон.

Предмет — карточка компании целиком. Связывание вакансии с компанией лежит с
вакансиями: там его делают из другого окна и по другому поводу.
"""

from tests.dbio import put
from tests.factories import company_row, hr_row, vacancy_row


async def test_the_list_counts_vacancies_and_marks_the_blacklisted(
    api, ask, session_factory
):
    """Строка перечня несёт счёт вакансий и отметку заслона.

    По ним в перечне и решают, к кому идти: компания с пятью вакансиями и
    компания, мелькнувшая однажды, — разные, а огороженная не нужна вовсе.
    """
    company = company_row(name="Контур")
    await put(session_factory, company)
    await put(session_factory, vacancy_row(company_id=company.id))

    answer = await ask(api.companies.list, {})

    row = answer["ok"]["companies"][0]
    assert row["vacancy_count"] == 1
    assert row["is_blacklisted"] is False


async def test_a_card_of_a_missing_company_is_refused_with_the_number(api, ask):
    """На пропавшую компанию отвечают отказом с её номером.

    Карточку открывают из перечня, а тот мог устареть. Без номера окно не
    поймёт, какую строку убирать с экрана.
    """
    answer = await ask(api.companies.detail, 404)

    assert answer["fail"] == "denied"
    assert answer["company_id"] == 404


async def test_spellings_typed_in_one_line_arrive_as_a_list(
    api, ask, session_factory
):
    """Написания, набранные строкой через запятую, приезжают списком.

    В форме их набирают одной строкой, а сверяют по одному: одна компания
    называется в объявлениях и «Контур», и «СКБ Контур». Останься это
    строкой — сверка искала бы целиком её, и не совпало бы ни одно.
    """
    answer = await ask(
        api.companies.create,
        {"name": "Контур", "aliases": "СКБ Контур, Контур.ру,  "},
    )
    assert "ok" in answer

    shown = await ask(api.companies.detail, answer["ok"]["created_id"])
    assert shown["ok"]["aliases"] == ["СКБ Контур", "Контур.ру"]


async def test_a_taken_name_is_named_as_taken(api, ask, session_factory):
    """Занятое название объясняют словами, а не отказом базы.

    Компании с одинаковым именем считаются одной — это решение записано в
    плане бэкенда. Человек, заводящий вторую, должен узнать про первую.
    """
    await put(session_factory, company_row(name="Контур"))

    answer = await ask(api.companies.create, {"name": "Контур"})

    assert answer["fail"] == "denied"
    assert "Контур" in answer["detail"]
    # Имя действия едет обратно в отказе: карточку заводят из формы, и по нему
    # окно понимает, какую именно форму оставить открытой.
    assert answer["action"] == "create_company"


async def test_renaming_into_a_taken_name_is_named_as_taken(
    api, ask, session_factory
):
    """Правку имени на занятое объясняют теми же словами, что и заведение.

    Руками сводя дубли, человек как раз и переименовывает одну в другую.
    Отказ базы доехал бы до окна текстом исключения SQLite.
    """
    taken = company_row(name="Контур")
    renamed = company_row(name="Ромашка")
    await put(session_factory, taken, renamed)

    answer = await ask(
        api.companies.update, {"company_id": renamed.id, "name": "Контур"}
    )

    assert answer["fail"] == "denied"
    assert "Контур" in answer["detail"]
    assert answer["action"] == "update_company"


async def test_spellings_of_a_wrong_shape_are_refused_before_the_base(
    api, ask, session_factory
):
    """Написания не того вида отбивают до базы, назвав годные виды.

    Форма шлёт то строку, то список — а число или словарь означают, что окно
    и мост разошлись. Молчаливое приведение стёрло бы все написания разом.
    """
    company = company_row(name="Контур")
    await put(session_factory, company)

    answer = await ask(api.companies.update, {"company_id": company.id, "aliases": 42})

    assert answer["fail"] == "denied"
    assert answer["detail"] == "aliases должен быть list или строка через запятую."


async def test_an_update_without_fields_says_there_is_nothing_to_do(
    api, ask, session_factory
):
    """Правку без единого поля отбивают: сохранять нечего.

    Форму отправляют и не тронув в ней ничего. Ответь мост успехом — окно
    показало бы «сохранено» там, где не сохранялось ничего.
    """
    company = company_row(name="Контур")
    await put(session_factory, company)

    answer = await ask(api.companies.update, {"company_id": company.id})

    assert answer["fail"] == "denied"
    assert answer["detail"] == "Нечего обновлять."


async def test_only_this_company_vacancies_are_shown(api, ask, session_factory):
    """В карточке видны вакансии только этой компании.

    Список читают, решая, стоит ли иметь с ней дело: пять вакансий за месяц и
    одна за год говорят разное. Попади туда чужая — счёт стал бы враньём, а
    разговор начался бы с вакансии, которой эта компания не давала.
    """
    mine = company_row(name="Контур")
    other = company_row(name="Рога")
    await put(session_factory, mine, other)
    await put(
        session_factory,
        vacancy_row(title="Моя", company_id=mine.id),
        vacancy_row(title="Чужая", company_id=other.id),
    )

    answer = await ask(api.companies.vacancies, {"company_id": mine.id})

    titles = [row["title"] for row in answer["ok"]["vacancies"]]
    assert titles == ["Моя"]


async def test_the_people_of_a_company_are_found_through_its_vacancies(
    api, ask, session_factory
):
    """Люди компании находятся через её вакансии, а не через свою ссылку.

    Прямой связи «HR — компания» в записях нет: человек привязан к вакансии,
    вакансия — к компании. Пропади этот переход, карточка компании осталась
    бы без единого собеседника.
    """
    company = company_row(name="Контур")
    hr = hr_row(name="Мария")
    await put(session_factory, company, hr)
    await put(session_factory, vacancy_row(company_id=company.id, hr_id=hr.id))

    answer = await ask(api.companies.people, company.id)

    assert [row["name"] for row in answer["ok"]["hrs"]] == ["Мария"]


async def test_the_absorbed_company_is_not_offered_as_its_own_survivor(
    api, ask, session_factory
):
    """Поглощаемой компании не предлагают слиться с самой собой.

    Оставшуюся выбирают из общего перечня, и попади туда она же — человек
    выбрал бы её не глядя, а слияние отбилось бы отказом на ровном месте.
    """
    absorbed = company_row(name="Контур")
    survivor = company_row(name="СКБ Контур")
    await put(session_factory, absorbed, survivor)

    answer = await ask(api.companies.merge_picker, {"absorbed_id": absorbed.id})

    offered = [row["id"] for row in answer["ok"]["companies"]]
    assert offered == [survivor.id]


async def test_merging_moves_vacancies_and_keeps_the_old_name_as_a_spelling(
    api, ask, session_factory
):
    """Слияние переносит вакансии и сохраняет прежнее имя написанием.

    Имя поглощённой продолжает приходить в новых объявлениях — источник о
    слиянии не знает. Потеряй его карточка, следующая вакансия завела бы
    компанию заново, и разнобой вернулся бы.
    """
    survivor = company_row(name="Контур")
    absorbed = company_row(name="СКБ Контур")
    await put(session_factory, survivor, absorbed)
    await put(session_factory, vacancy_row(title="Из второй", company_id=absorbed.id))

    merged = await ask(
        api.companies.merge,
        {"absorbed_id": absorbed.id, "survivor_id": survivor.id},
    )
    assert "ok" in merged

    shown = await ask(api.companies.detail, survivor.id)
    assert "СКБ Контур" in shown["ok"]["aliases"]

    listed = await ask(api.companies.vacancies, {"company_id": survivor.id})
    titles = [row["title"] for row in listed["ok"]["vacancies"]]
    assert titles == ["Из второй"]


async def test_merging_a_company_into_itself_is_refused(api, ask, session_factory):
    """Слияние карточки с самой собой отбивают.

    Пройди оно — карточка поглотила бы себя, и что стало бы с её вакансиями
    и написаниями, не сказал бы никто.
    """
    company = company_row(name="Контур")
    await put(session_factory, company)

    answer = await ask(
        api.companies.merge, {"absorbed_id": company.id, "survivor_id": company.id}
    )

    assert answer["fail"] == "denied"


async def test_a_deleted_company_leaves_the_list(api, ask, session_factory):
    """Удалённая компания исчезает из перечня, а не только получает ответ."""
    company = company_row(name="Контур")
    await put(session_factory, company)

    assert "ok" in await ask(api.companies.delete, company.id)

    listed = await ask(api.companies.list, {})
    assert listed["ok"]["companies"] == []


async def test_blacklisting_a_company_writes_its_name(api, ask, session_factory):
    """Заслон компании ставится по имени — другого значения у неё нет.

    У человека есть ник и номер учётной записи, у компании только имя, и
    именно его сверяет заслон отправки. В ответ оно приходит затем, чтобы
    карточка показала, по чему именно поставлен заслон.
    """
    company = company_row(name="Контур")
    await put(session_factory, company)

    answer = await ask(api.companies.block, company.id)
    assert answer["ok"]["value"] == "Контур"
    assert answer["ok"]["existed"] is False

    shown = await ask(api.companies.detail, company.id)
    assert shown["ok"]["blacklist_value"] == "Контур"


async def test_removing_a_company_blacklist_clears_the_card(
    api, ask, session_factory
):
    """Снятый заслон виден в карточке: значения там больше нет."""
    company = company_row(name="Контур")
    await put(session_factory, company)

    await ask(api.companies.block, company.id)

    removed = await ask(api.companies.unblock, company.id)
    assert removed["ok"]["updated"] == 1

    shown = await ask(api.companies.detail, company.id)
    assert shown["ok"]["blacklist_value"] is None
