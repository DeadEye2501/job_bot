"""Следствия слотов карточки HR: перечень, правка, слияние, чёрный список.

Предмет — сама карточка. Переписка с тем же человеком лежит своим файлом: там
ответ приходит не из базы, а от бота.
"""

import json

from tests.dbio import put
from tests.factories import hr_row, vacancy_row


async def test_the_list_counts_vacancies_behind_each_hr(
    main_api, watch, session_factory
):
    """Строка перечня несёт число вакансий этого человека.

    По нему в перечне и выбирают, с кем разговаривать: HR с пятью вакансиями
    и HR, написавший однажды, — разные собеседники, а имена у них одинаково
    ничего не говорят.
    """
    caught = watch(main_api.contacts_hr_list_loaded)
    hr = hr_row(name="Мария")
    await put(session_factory, hr)
    await put(session_factory, vacancy_row(hr_id=hr.id), vacancy_row(hr_id=hr.id))

    main_api.request_contacts_hr_list(json.dumps({}))

    row = (await caught.next())["hrs"][0]
    assert row["name"] == "Мария"
    assert row["vacancy_count"] == 2


async def test_a_card_of_a_missing_hr_is_refused_with_the_number(main_api, watch):
    """На пропавшего HR отвечают отказом с его номером.

    Карточку открывают из перечня, а тот мог устареть — человека удалили из
    другого окна. Без номера окно не поймёт, какую строку убирать.
    """
    caught = watch(main_api.contacts_hr_detail_loaded)

    main_api.request_contacts_hr_detail(404)

    answer = await caught.next()
    assert answer["ok"] is False
    assert answer["hr_id"] == 404


async def test_only_this_hr_vacancies_are_shown(main_api, watch, session_factory):
    """В карточке видны вакансии только этого человека.

    Список ведут, чтобы понять, о чём с ним говорить. Попади туда чужая —
    разговор начался бы с вакансии, которую он никогда не присылал.
    """
    caught = watch(main_api.contacts_hr_vacancies_loaded)
    mine = hr_row(name="Мария", telegram_username="maria")
    other = hr_row(name="Пётр", telegram_username="petr")
    await put(session_factory, mine, other)
    await put(
        session_factory,
        vacancy_row(title="Моя", hr_id=mine.id),
        vacancy_row(title="Чужая", hr_id=other.id),
    )

    main_api.request_contacts_hr_vacancies(json.dumps({"hr_id": mine.id}))

    titles = [row["title"] for row in (await caught.next())["vacancies"]]
    assert titles == ["Моя"]


async def test_merging_moves_the_vacancies_to_the_survivor(
    main_api, watch, session_factory
):
    """Слияние переносит вакансии на оставшегося, а не теряет их.

    Один человек, написавший с двух учётных записей, заводится дважды —
    слияние затем и делают. Пропади его вакансии вместе с поглощённой
    карточкой, история переписки осталась бы без предмета.
    """
    done = watch(main_api.contacts_hr_action_done)
    listed = watch(main_api.contacts_hr_vacancies_loaded)
    survivor = hr_row(name="Мария", telegram_username="maria")
    absorbed = hr_row(name="Маша", telegram_username="masha")
    await put(session_factory, survivor, absorbed)
    await put(session_factory, vacancy_row(title="Из второй", hr_id=absorbed.id))

    main_api.contacts_merge_hr(
        json.dumps({"absorbed_id": absorbed.id, "survivor_id": survivor.id})
    )
    assert (await done.next())["ok"] is True

    main_api.request_contacts_hr_vacancies(json.dumps({"hr_id": survivor.id}))
    titles = [row["title"] for row in (await listed.next())["vacancies"]]
    assert titles == ["Из второй"]


async def test_merging_an_hr_into_himself_is_refused(main_api, watch, session_factory):
    """Слияние карточки с самой собой отбивают.

    В подборщике оставшегося выбирают из общего перечня, и попасть в него
    может тот же самый. Пройди такое слияние — карточка поглотила бы себя,
    и что стало бы с её вакансиями, не сказал бы никто.
    """
    caught = watch(main_api.contacts_hr_action_done)
    hr = hr_row()
    await put(session_factory, hr)

    main_api.contacts_merge_hr(
        json.dumps({"absorbed_id": hr.id, "survivor_id": hr.id})
    )

    assert (await caught.next())["ok"] is False


async def test_a_deleted_hr_leaves_the_list(main_api, watch, session_factory):
    """Удалённый HR исчезает из перечня, а не только получает ответ."""
    done = watch(main_api.contacts_hr_action_done)
    listed = watch(main_api.contacts_hr_list_loaded)
    hr = hr_row()
    await put(session_factory, hr)

    main_api.contacts_delete_hr(hr.id)
    assert (await done.next())["ok"] is True

    main_api.request_contacts_hr_list(json.dumps({}))
    assert (await listed.next())["hrs"] == []


async def test_an_update_without_fields_says_there_is_nothing_to_do(
    main_api, watch, session_factory
):
    """Правку без единого поля отбивают словами.

    Форму отправляют по нажатию, и не тронув в ней ничего. Ответь мост
    успехом — окно показало бы «сохранено» там, где не сохранялось ничего.
    """
    caught = watch(main_api.contacts_hr_action_done)
    hr = hr_row()
    await put(session_factory, hr)

    main_api.contacts_update_hr(json.dumps({"hr_id": hr.id}))

    answer = await caught.next()
    assert answer["ok"] is False
    assert answer["error"] == "Нечего обновлять."


async def test_a_nick_that_is_not_a_telegram_one_is_refused(
    main_api, watch, session_factory
):
    """Ник, не похожий на телеграмовский, до карточки не доходит.

    По нику потом и пишут. Запишись туда телефон или ссылка — отправка
    сорвалась бы позже и в другом месте, где причину уже не видно.
    """
    caught = watch(main_api.contacts_hr_action_done)
    hr = hr_row()
    await put(session_factory, hr)

    main_api.contacts_update_hr(
        json.dumps({"hr_id": hr.id, "telegram_username": "+7 900 000-00-00"})
    )

    answer = await caught.next()
    assert answer["ok"] is False
    assert "ник" in answer["error"]


async def test_an_updated_name_reaches_the_card(main_api, watch, session_factory):
    """Изменённое имя видно в карточке при следующем открытии."""
    done = watch(main_api.contacts_hr_action_done)
    shown = watch(main_api.contacts_hr_detail_loaded)
    hr = hr_row(name="Мария")
    await put(session_factory, hr)

    main_api.contacts_update_hr(json.dumps({"hr_id": hr.id, "name": "Мария Иванова"}))
    assert (await done.next())["ok"] is True

    main_api.request_contacts_hr_detail(hr.id)
    assert (await shown.next())["name"] == "Мария Иванова"


async def test_an_hr_without_a_nick_cannot_be_blacklisted(
    main_api, watch, session_factory
):
    """Безымянного в чёрный список не заносят: заносить нечего.

    Список ведут по нику или по номеру учётной записи — только их сверяет
    заслон отправки. Заведись запись без значения, она молча не сработала бы
    ни разу, а человек считал бы, что оградился.
    """
    caught = watch(main_api.contacts_hr_action_done)
    hr = hr_row(name="Без ника", telegram_username=None)
    await put(session_factory, hr)

    main_api.contacts_add_hr_to_blacklist(hr.id)

    answer = await caught.next()
    assert answer["ok"] is False
    assert answer["error"] == "У HR нет ни @username, ни telegram_user_id."


async def test_blacklisting_names_the_value_that_was_written(
    main_api, watch, session_factory
):
    """В ответ приходит то самое значение, которое легло в список.

    Его показывают в карточке: человек должен видеть, по чему именно
    поставлен заслон, — ник и номер учётной записи ведут себя по-разному.
    """
    caught = watch(main_api.contacts_hr_action_done)
    hr = hr_row(name="Мария", telegram_username="maria")
    await put(session_factory, hr)

    main_api.contacts_add_hr_to_blacklist(hr.id)

    answer = await caught.next()
    assert answer["ok"] is True
    assert answer["value"] == "@maria"


async def test_a_second_blacklisting_says_it_was_already_there(
    main_api, watch, session_factory
):
    """Повторный заслон не заводит вторую запись, а признаётся в первой.

    Кнопку жмут дважды, не заметив первого раза. Заведи мост вторую запись —
    снятие заслона убрало бы одну, и человек остался бы огорожен без
    видимой причины.
    """
    caught = watch(main_api.contacts_hr_action_done)
    hr = hr_row(name="Мария", telegram_username="maria")
    await put(session_factory, hr)

    main_api.contacts_add_hr_to_blacklist(hr.id)
    assert (await caught.next())["existed"] is False

    main_api.contacts_add_hr_to_blacklist(hr.id)
    assert (await caught.next())["existed"] is True


async def test_removing_a_blacklist_reaches_the_card(main_api, watch, session_factory):
    """Снятый заслон виден в карточке: значения там больше нет."""
    done = watch(main_api.contacts_hr_action_done)
    shown = watch(main_api.contacts_hr_detail_loaded)
    hr = hr_row(name="Мария", telegram_username="maria")
    await put(session_factory, hr)

    main_api.contacts_add_hr_to_blacklist(hr.id)
    await done.next()

    main_api.contacts_remove_hr_from_blacklist(hr.id)
    assert (await done.next())["ok"] is True

    main_api.request_contacts_hr_detail(hr.id)
    assert (await shown.next())["blacklist_value"] is None
