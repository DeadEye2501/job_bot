"""Следствия карточки HR: перечень, правка, слияние, чёрный список.

Предмет — сама карточка. Переписка с тем же человеком лежит своим файлом: там
ответ приходит не из базы, а от бота.
"""

from tests.dbio import put
from tests.factories import hr_row, vacancy_row


async def test_the_list_counts_vacancies_behind_each_hr(api, ask, session_factory):
    """Строка перечня несёт число вакансий этого человека.

    По нему в перечне и выбирают, с кем разговаривать: HR с пятью вакансиями
    и HR, написавший однажды, — разные собеседники, а имена у них одинаково
    ничего не говорят.
    """
    hr = hr_row(name="Мария")
    await put(session_factory, hr)
    await put(session_factory, vacancy_row(hr_id=hr.id), vacancy_row(hr_id=hr.id))

    answer = await ask(api.hr.list, {})

    row = answer["ok"]["hrs"][0]
    assert row["name"] == "Мария"
    assert row["vacancy_count"] == 2


async def test_a_card_of_a_missing_hr_is_refused_with_the_number(api, ask):
    """На пропавшего HR отвечают отказом с его номером.

    Карточку открывают из перечня, а тот мог устареть — человека удалили из
    другого окна. Без номера окно не поймёт, какую строку убирать.
    """
    answer = await ask(api.hr.detail, 404)

    assert answer["fail"] == "denied"
    assert answer["hr_id"] == 404


async def test_only_this_hr_vacancies_are_shown(api, ask, session_factory):
    """В карточке видны вакансии только этого человека.

    Список ведут, чтобы понять, о чём с ним говорить. Попади туда чужая —
    разговор начался бы с вакансии, которую он никогда не присылал.
    """
    mine = hr_row(name="Мария", telegram_username="maria")
    other = hr_row(name="Пётр", telegram_username="petr")
    await put(session_factory, mine, other)
    await put(
        session_factory,
        vacancy_row(title="Моя", hr_id=mine.id),
        vacancy_row(title="Чужая", hr_id=other.id),
    )

    answer = await ask(api.hr.vacancies, {"hr_id": mine.id})

    titles = [row["title"] for row in answer["ok"]["vacancies"]]
    assert titles == ["Моя"]


async def test_merging_moves_the_vacancies_to_the_survivor(api, ask, session_factory):
    """Слияние переносит вакансии на оставшегося, а не теряет их.

    Один человек, написавший с двух учётных записей, заводится дважды —
    слияние затем и делают. Пропади его вакансии вместе с поглощённой
    карточкой, история переписки осталась бы без предмета.
    """
    survivor = hr_row(name="Мария", telegram_username="maria")
    absorbed = hr_row(name="Маша", telegram_username="masha")
    await put(session_factory, survivor, absorbed)
    await put(session_factory, vacancy_row(title="Из второй", hr_id=absorbed.id))

    merged = await ask(
        api.hr.merge, {"absorbed_id": absorbed.id, "survivor_id": survivor.id}
    )
    assert "ok" in merged

    listed = await ask(api.hr.vacancies, {"hr_id": survivor.id})
    titles = [row["title"] for row in listed["ok"]["vacancies"]]
    assert titles == ["Из второй"]


async def test_merging_an_hr_into_himself_is_refused(api, ask, session_factory):
    """Слияние карточки с самой собой отбивают.

    В подборщике оставшегося выбирают из общего перечня, и попасть в него
    может тот же самый. Пройди такое слияние — карточка поглотила бы себя,
    и что стало бы с её вакансиями, не сказал бы никто.
    """
    hr = hr_row()
    await put(session_factory, hr)

    answer = await ask(api.hr.merge, {"absorbed_id": hr.id, "survivor_id": hr.id})

    assert answer["fail"] == "denied"


async def test_a_deleted_hr_leaves_the_list(api, ask, session_factory):
    """Удалённый HR исчезает из перечня, а не только получает ответ."""
    hr = hr_row()
    await put(session_factory, hr)

    assert "ok" in await ask(api.hr.delete, hr.id)

    listed = await ask(api.hr.list, {})
    assert listed["ok"]["hrs"] == []


async def test_an_update_without_fields_says_there_is_nothing_to_do(
    api, ask, session_factory
):
    """Правку без единого поля отбивают словами.

    Форму отправляют по нажатию, и не тронув в ней ничего. Ответь мост
    успехом — окно показало бы «сохранено» там, где не сохранялось ничего.
    """
    hr = hr_row()
    await put(session_factory, hr)

    answer = await ask(api.hr.update, {"hr_id": hr.id})

    assert answer["fail"] == "denied"
    assert answer["detail"] == "Нечего обновлять."


async def test_a_created_person_shows_up_in_the_list(api, ask):
    """Заведённый из контактов человек попадает в перечень, а не только в ответ.

    Заводят его, чтобы потом найти. Не доедь запись до базы, ответ был бы
    успешным, а карточки в перечне не оказалось бы — и человек завёл бы вторую
    такую же.

    Красной фазы у этого сторожа не было: заведение из контактов не сторожил
    никто вовсе, и дописан он по находке ревью слайса А2.9в.
    """
    answer = await ask(api.hr.create, {"name": "Пётр", "telegram_username": "petr"})

    assert "ok" in answer
    listed = await ask(api.hr.list, {})
    assert "Пётр" in [row["name"] for row in listed["ok"]["hrs"]]


async def test_a_person_without_a_name_and_without_a_nick_is_refused(api, ask):
    """Карточку без имени и без ника не заводят и из контактов тоже.

    Такая карточка не отличима от любой другой: следующий раз человек завёл бы
    вторую такую же вместо того, чтобы найти эту. Заслон один на оба окна — и
    на контакты, и на подборщик при вакансии, — и разойдись они, одно и то же
    отбивалось бы в одном месте и проходило в другом.

    Красной фазы не было — дописан по той же находке.
    """
    answer = await ask(api.hr.create, {"name": "  ", "notes": "без имени"})

    assert answer["fail"] == "denied"
    assert answer["detail"] == "Укажите хотя бы имя или @username."


async def test_a_nick_that_is_not_a_telegram_one_is_refused(api, ask, session_factory):
    """Ник, не похожий на телеграмовский, до карточки не доходит.

    По нику потом и пишут. Запишись туда телефон или ссылка — отправка
    сорвалась бы позже и в другом месте, где причину уже не видно.
    """
    hr = hr_row()
    await put(session_factory, hr)

    answer = await ask(
        api.hr.update, {"hr_id": hr.id, "telegram_username": "+7 900 000-00-00"}
    )

    assert answer["fail"] == "denied"
    assert "ник" in answer["detail"]


async def test_an_updated_name_reaches_the_card(api, ask, session_factory):
    """Изменённое имя видно в карточке при следующем открытии."""
    hr = hr_row(name="Мария")
    await put(session_factory, hr)

    saved = await ask(api.hr.update, {"hr_id": hr.id, "name": "Мария Иванова"})
    assert "ok" in saved

    shown = await ask(api.hr.detail, hr.id)
    assert shown["ok"]["name"] == "Мария Иванова"


async def test_an_hr_without_a_nick_cannot_be_blacklisted(api, ask, session_factory):
    """Безымянного в чёрный список не заносят: заносить нечего.

    Список ведут по нику или по номеру учётной записи — только их сверяет
    заслон отправки. Заведись запись без значения, она молча не сработала бы
    ни разу, а человек считал бы, что оградился.
    """
    hr = hr_row(name="Без ника", telegram_username=None)
    await put(session_factory, hr)

    answer = await ask(api.hr.block, hr.id)

    assert answer["fail"] == "denied"
    assert answer["detail"] == "У HR нет ни @username, ни telegram_user_id."


async def test_blacklisting_names_the_value_that_was_written(api, ask, session_factory):
    """В ответ приходит то самое значение, которое легло в список.

    Его показывают в карточке: человек должен видеть, по чему именно
    поставлен заслон, — ник и номер учётной записи ведут себя по-разному.
    """
    hr = hr_row(name="Мария", telegram_username="maria")
    await put(session_factory, hr)

    answer = await ask(api.hr.block, hr.id)

    assert answer["ok"]["value"] == "@maria"


async def test_a_second_blacklisting_says_it_was_already_there(
    api, ask, session_factory
):
    """Повторный заслон не заводит вторую запись, а признаётся в первой.

    Кнопку жмут дважды, не заметив первого раза. Заведи мост вторую запись —
    снятие заслона убрало бы одну, и человек остался бы огорожен без
    видимой причины.
    """
    hr = hr_row(name="Мария", telegram_username="maria")
    await put(session_factory, hr)

    assert (await ask(api.hr.block, hr.id))["ok"]["existed"] is False

    assert (await ask(api.hr.block, hr.id))["ok"]["existed"] is True


async def test_removing_a_blacklist_reaches_the_card(api, ask, session_factory):
    """Снятый заслон виден в карточке: значения там больше нет."""
    hr = hr_row(name="Мария", telegram_username="maria")
    await put(session_factory, hr)

    await ask(api.hr.block, hr.id)
    assert "ok" in await ask(api.hr.unblock, hr.id)

    shown = await ask(api.hr.detail, hr.id)
    assert shown["ok"]["blacklist_value"] is None


async def test_a_deleted_person_tells_the_counters_to_reread_themselves(
    api, ask, session_factory, hub
):
    """Снос карточки кладёт в очередь весть для списков и для непрочитанного.

    Переписка уходит вместе с человеком, и счётчик непрочитанного, собранный по
    ней же, остался бы завышенным до перезапуска окна.

    Красной фазы у этого сторожа не было — оповещение дописано вместе с
    переездом домена, и доверие оно заслужит итоговым проходом.
    """
    hr = hr_row()
    await put(session_factory, hr)

    await ask(api.hr.delete, hr.id)
    news = await hub.events.take(after=0, timeout=0.01)

    assert [one["kind"] for one in news["events"]] == [
        "contacts_lists_changed",
        "unread_changed",
    ]
