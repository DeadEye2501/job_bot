"""Следствия заведения вакансии руками: что после него видно в списке и в карточке.

Предмет — форма «Добавить вакансию» на экране вакансий. Заведение конвейером
проверяется со своим потоком: там строка собирается из поста канала, и общего
у двух заведений нет ничего, кроме таблицы.
"""

from tests.dbio import put
from tests.factories import company_row, hr_row, profile_row, profile_skill_row


async def created(ask, api, **fields) -> int:
    """Завести вакансию формой и назвать её номер.

    Своим телом, потому что зовут это все проверки ниже: набор полей у формы
    один, и переписанный в каждой он разъехался бы с тем, что читает мост.
    """
    answer = await ask(api.vacancies.create, {"title": "Python-разработчик", **fields})
    assert "ok" in answer, answer
    return answer["ok"]["created_id"]


async def profile_knowing(session_factory, name: str, level: int) -> None:
    """Анкета, знающая один навык названного уровня.

    Своим телом по тому же доводу, что и `created` выше: балл считают почти
    все проверки ниже, и завод анкеты, переписанный в каждой, разъехался бы с
    тем, что читает подсчёт.
    """
    profile = profile_row()
    await put(session_factory, profile)
    await put(session_factory, profile_skill_row(profile.id, name, level=level))


async def test_a_hand_made_vacancy_shows_up_in_the_list(api, ask):
    """Заведённая руками вакансия видна в списке сразу.

    Список показывает только разобранные строки, а у набранной руками разбора
    не было вовсе: не отметь её мост разобранной, человек завёл бы вакансию и
    не нашёл её на том же экране.
    """
    await created(ask, api)

    answer = await ask(api.vacancies.list, {})

    titles = [row["title"] for row in answer["ok"]["vacancies"]]
    assert titles == ["Python-разработчик"]


async def test_a_typed_salary_becomes_a_range_the_filter_can_see(api, ask):
    """Набранная вилка попадает в отбор по зарплате.

    Отбор ищет по числам колонок, а не по написанию: не лягте они, вакансия
    с названной суммой не нашлась бы отбором «от 3000», хотя глазами
    подходит.
    """
    await created(ask, api, salary_min=4000, salary_max=4500, salary_currency="$")

    answer = await ask(api.vacancies.list, {"salary_min": 3000})

    assert len(answer["ok"]["vacancies"]) == 1


async def test_a_vacancy_without_a_title_is_refused(api, ask):
    """Вакансию без названия не заводят.

    В списке такая строка выглядит пустой: название — единственное, чем её
    там называют, и найти её потом нечем ни поиском, ни глазами.
    """
    answer = await ask(api.vacancies.create, {"source_url": "https://job"})

    assert answer["fail"] == "denied"


async def test_a_stack_collected_by_chips_arrives_as_a_list(api, ask):
    """Стек, собранный пилюлями, доезжает до карточки списком.

    Рядов в форме два, а колонка одна: карточка, поиск и статистика читают
    стек целиком, и делить его им незачем. Пустые пилюли выпадают по дороге:
    их набирают и бросают, а в карточке пустой чип выглядел бы потерянным
    названием. Пустым бывает не только пробел: у «///» и «-» пусто выходит
    имя навыка, которым его сравнивают, и такая пилюля в карточке ничего не
    говорит, а отбору по стеку врёт.
    """
    vacancy_id = await created(
        ask,
        api,
        stack_required=["Python", "  ", "///"],
        stack_preferred=["FastAPI", " ", "-"],
    )

    answer = await ask(api.vacancies.detail, vacancy_id)

    assert [one["name"] for one in answer["ok"]["vacancy"]["stack"]] == ["Python", "FastAPI"]


async def test_a_hand_made_vacancy_is_scored_by_the_profile(api, ask, session_factory):
    """Заведённой руками вакансии балл считают так же, как найденной ботом.

    Список сортируют и отбирают по баллу, и строка без него оседает в хвосте
    рядом с теми, у кого разбор не удался: человек завёл бы вакансию и не
    нашёл её там, где ищет подходящие.
    """
    await profile_knowing(session_factory, "Python", 3)

    vacancy_id = await created(ask, api, stack_required=["Python"])

    answer = await ask(api.vacancies.detail, vacancy_id)
    assert answer["ok"]["vacancy"]["score"] == 3


async def test_the_second_row_of_chips_weighs_less_than_the_first(
    api, ask, session_factory
):
    """Незнакомое в дополнительных не наказывает, а в основных — наказывает.

    Ради этого различия рядов в форме и два: требование незнакомого опускает
    вакансию ниже той, что не требует ничего, а названное плюсом о пригодности
    не говорит вовсе.
    """
    await profile_knowing(session_factory, "Python", 3)

    lenient = await created(ask, api, stack_preferred=["Rust"])
    strict = await created(ask, api, stack_required=["Rust"])
    known = await created(ask, api, stack_preferred=["Python"])

    assert (await ask(api.vacancies.detail, lenient))["ok"]["vacancy"]["score"] == 0
    assert (await ask(api.vacancies.detail, strict))["ok"]["vacancy"]["score"] == -1
    # Знакомый навык в дополнительных стоит на балл меньше: не будь этой
    # проверки, потерянная по дороге вторая половина осталась бы незамеченной —
    # у незнакомого и у потерянного балл одинаковый.
    assert (await ask(api.vacancies.detail, known))["ok"]["vacancy"]["score"] == 2


async def test_a_skill_typed_into_both_rows_counts_once(api, ask, session_factory):
    """Навык, набранный в оба ряда, считается один раз и чипом рисуется один.

    Ряды стоят рядом, подписи у них короткие, и один и тот же навык попадает в
    оба легко. Засчитайся он дважды — вакансия с одним знакомым инструментом
    получила бы балл, будто их два, и перепрыгнула бы порог раньше тех, кто
    его заслужил. У найденной ботом от этого стоит заслон в наставлении, и
    правило здесь то же: повтор остаётся в обязательных. Одинаковыми при этом
    считаются написания, а не буквы: «python» и «PYTHON» — тот же навык.
    """
    await profile_knowing(session_factory, "Python", 3)

    vacancy_id = await created(
        ask, api, stack_required=["Python", "python"], stack_preferred=["PYTHON"]
    )

    answer = await ask(api.vacancies.detail, vacancy_id)
    assert [one["name"] for one in answer["ok"]["vacancy"]["stack"]] == ["Python"]
    assert answer["ok"]["vacancy"]["score"] == 3


async def test_pasted_text_goes_to_the_bot_without_waiting_for_the_parser(
    api, ask, with_bot, told
):
    """Вставленный текст уходит боту, а окно не ждёт разбора.

    Разбор — это от двух до пяти обращений к модели: подержи мост ответ до
    конца, и окно висело бы всё это время. Человеку отвечают «пущено», а
    чем кончилось — говорят вестью.
    """
    bot = with_bot()

    answer = await ask(api.vacancies.create_from_text, {"raw_text": "Ищем флориста"})

    assert answer["ok"]["started"] is True
    assert [call for call in bot.calls if call[0] == "ui_ingest_pasted_text"] == [
        ("ui_ingest_pasted_text", "Ищем флориста", None)
    ]
    # Об удаче человеку говорят вестью, а не ответом на зов: к её приходу окно
    # уже закрыто, и другого способа сказать «получилось» нет.
    assert await told() == {"message": "Объявление заведено.", "danger": False}


async def test_the_named_publication_date_reaches_the_bot(api, ask, with_bot):
    """Названная дата публикации доезжает до конвейера.

    Из самого текста её не достать — в посте канала бот берёт её у Telegram, а
    у вставленного объявления взять неоткуда. Не доедь она, объявление
    выпало бы из отбора «за последние дни».
    """
    bot = with_bot()

    await ask(
        api.vacancies.create_from_text,
        {"raw_text": "Ищем сварщика", "posted_at": "2026-08-20"},
    )

    _, _, when = next(
        call for call in bot.calls if call[0] == "ui_ingest_pasted_text"
    )
    assert when.date().isoformat() == "2026-08-20"


async def test_an_empty_paste_is_refused_with_words(api, ask, with_bot):
    """Пустую вставку отбивают словами, а не молчанием.

    Разбирать нечего, и пущенная работа кончилась бы отказом изнутри — но
    человек к этому времени уже закрыл бы окно, решив, что вакансия заводится.
    """
    with_bot()

    answer = await ask(api.vacancies.create_from_text, {"raw_text": "   "})

    assert answer["fail"] == "denied"
    assert answer["detail"] == "Вставьте текст объявления."


async def test_pasting_before_the_bot_is_up_is_refused_by_name(api, ask):
    """До входа в Telegram вставку отбивают словами про бота.

    Разбор живёт на боте — там модели и место прогона. Кнопку рисуют всегда, и
    молчание на неё оставило бы человека ждать вакансию, которая не заводится.
    """
    answer = await ask(api.vacancies.create_from_text, {"raw_text": "Ищем повара"})

    assert answer["fail"] == "denied"
    assert answer["detail"] == "Бот ещё не готов."


async def test_a_pasted_duplicate_is_explained_not_swallowed(
    api, ask, with_bot, told
):
    """Про уже заведённое объявление человеку говорят словом.

    Иначе он вставляет текст, ничего не появляется, и он вставляет снова —
    так и не узнав, что эта вакансия давно в списке.
    """
    with_bot(pasted="duplicate")

    answer = await ask(api.vacancies.create_from_text, {"raw_text": "Ищем повара"})

    assert answer["ok"]["started"] is True
    assert await told() == {
        "message": "Такое объявление уже заведено.",
        "danger": True,
    }


async def test_the_typed_description_is_not_passed_off_as_the_source_text(api, ask):
    """Набранное описание исходным текстом объявления не становится.

    Исходным текстом судит повторный разбор: он читает его и пишет поверх
    полей. Ляг туда пересказ, сделанный человеком, — разбор пересказал бы
    пересказ и затёр бы им набранное вручную. У вакансии, заведённой полями,
    исходника нет, и это честнее подделки.
    """
    vacancy_id = await created(ask, api, description="Ищем флориста в студию")

    answer = await ask(api.vacancies.detail, vacancy_id)
    assert answer["ok"]["vacancy"]["raw_text"] is None


async def test_the_typed_publication_date_lands_in_the_row(api, ask):
    """Набранная дата публикации ложится в строку.

    По ней идут отбор «за последние дни» и давность в списке: без даты
    заведённая руками вакансия выглядит вчерашней ровно до тех пор, пока по
    ней не пройдёт отбор, а там пропадает вовсе.
    """
    vacancy_id = await created(ask, api, posted_at="2026-08-20")

    answer = await ask(api.vacancies.detail, vacancy_id)
    assert answer["ok"]["vacancy"]["posted_at"].startswith("2026-08-20")


async def test_an_unknown_grade_does_not_reach_the_card(api, ask):
    """Грейд не из перечня в карточку не попадает.

    Колонка держит обычную строку, и чужое значение отсеять может только код.
    Записанное молча, оно не совпало бы ни с одним отбором — вакансия
    пропала бы из выдачи по грейду, хотя в карточке он написан.
    """
    vacancy_id = await created(ask, api, grade="principal")

    answer = await ask(api.vacancies.detail, vacancy_id)

    assert answer["ok"]["vacancy"]["grade"] is None


async def test_the_card_timeline_tells_the_vacancy_was_made_by_hand(api, ask):
    """Лента карточки говорит, что вакансию завели руками.

    Лента объясняет, откуда строка взялась. Пустая у заведённой руками, она
    читалась бы как потерянный след обхода каналов.
    """
    vacancy_id = await created(ask, api)

    answer = await ask(api.vacancies.detail, vacancy_id)

    assert [one["kind"] for one in answer["ok"]["vacancy"]["events"]] == ["created_by_hand"]


async def test_a_chosen_company_is_linked_not_just_named(api, ask, session_factory):
    """Выбранная в списке компания привязывается, а не переписывается словом.

    Привязанную карточка компании показывает у себя в мини-списке, а
    записанное строкой имя не связано ни с чем: вакансия не нашлась бы ни
    оттуда, ни отбором по компании.
    """
    company = company_row(name="Nitka")
    await put(session_factory, company)

    vacancy_id = await created(ask, api, company_id=company.id)

    answer = await ask(api.vacancies.detail, vacancy_id)
    assert answer["ok"]["vacancy"]["company_id"] == company.id
    assert answer["ok"]["vacancy"]["company_name"] == "Nitka"


async def test_a_chosen_hr_is_linked_to_the_new_vacancy(api, ask, session_factory):
    """Выбранный в списке HR привязывается к заведённой вакансии.

    Без привязки карточка предложила бы связать её заново, а отклик отправлять
    было бы некому — отправка идёт по привязанному человеку.
    """
    hr = hr_row(name="Мария")
    await put(session_factory, hr)

    vacancy_id = await created(ask, api, hr_id=hr.id)

    answer = await ask(api.vacancies.detail, vacancy_id)
    assert answer["ok"]["vacancy"]["hr"]["name"] == "Мария"


async def test_the_form_is_offered_both_lists_at_once(api, ask, session_factory):
    """Форма получает и людей, и компании одним ответом.

    Показывает она их рядом, двумя списками: приезжай они порознь, один
    рисовался бы раньше другого, и выбирать пришлось бы в полупустой форме.
    """
    await put(session_factory, hr_row(name="Мария"), company_row(name="Nitka"))

    answer = await ask(api.vacancies.create_options)

    assert [row["name"] for row in answer["ok"]["hrs"]] == ["Мария"]
    assert [row["name"] for row in answer["ok"]["companies"]] == ["Nitka"]


async def test_salary_typed_in_three_fields_arrives_as_a_range(api, ask):
    """Зарплата, набранная тремя полями, доезжает вилкой и валютой.

    Отбор по зарплате смотрит на числа, а карточка — на знак валюты: набери
    человек «от 4000 до 4500» одной строкой, разбирать её пришлось бы обратно,
    хотя он уже разложил её сам.
    """
    vacancy_id = await created(
        ask, api, salary_min=4000, salary_max=4500, salary_currency="$"
    )

    answer = await ask(api.vacancies.detail, vacancy_id)

    card = answer["ok"]["vacancy"]
    assert (card["salary_min"], card["salary_max"]) == (4000, 4500)
    assert card["salary_currency"] == "$"


async def test_a_country_and_a_city_arrive_the_way_the_parser_writes_them(api, ask):
    """Страна и город складываются в то же написание, что кладёт разбор.

    Разбор пишет «Армения/Ереван», и заведённая руками вакансия обязана
    писаться так же: иначе отбор и статистика считали бы одно и то же место
    двумя разными.
    """
    vacancy_id = await created(ask, api, country="Армения", city="Ереван")

    answer = await ask(api.vacancies.detail, vacancy_id)

    assert answer["ok"]["vacancy"]["location"] == "Армения/Ереван"


async def test_a_country_without_a_city_stands_alone(api, ask):
    """Названа одна страна — она и стоит в поле, без косой черты.

    Косая черта значит «страна и город»: висящая в конце, она читалась бы как
    потерянный город.
    """
    vacancy_id = await created(ask, api, country="Армения")

    answer = await ask(api.vacancies.detail, vacancy_id)

    assert answer["ok"]["vacancy"]["location"] == "Армения"


async def test_a_currency_named_in_words_becomes_its_sign(api, ask):
    """Валюта, набранная словом, приводится к знаку тем же кодом, что и разбор.

    Человек пишет её так, как привык — «usd», «руб», «долларов». Ляг это в
    колонку как есть, пилюля печатала бы «4000 usd», а отбор считал бы такую
    вакансию отдельной валютой.
    """
    vacancy_id = await created(
        ask, api, salary_min=4000, salary_max=4500, salary_currency="usd"
    )

    answer = await ask(api.vacancies.detail, vacancy_id)

    assert answer["ok"]["vacancy"]["salary_currency"] == "$"


async def test_an_unknown_currency_word_leaves_the_field_empty(api, ask):
    """Незнакомое слово валютой не становится.

    Записанное как есть, оно попало бы в пилюлю и в отбор наравне со знаками,
    которые разбор понимает, — и вакансия ушла бы в валюту, которой нет.
    """
    vacancy_id = await created(ask, api, salary_min=4000, salary_currency="галлеон")

    answer = await ask(api.vacancies.detail, vacancy_id)

    assert answer["ok"]["vacancy"]["salary_currency"] is None


async def test_the_form_is_told_the_telegram_handle_of_each_person(api, ask, session_factory):
    """Вместе с именем человека форме едет его ник.

    Имя уникальным не бывает — тёзок в подсказке различают только ником, и без
    него человек выбирает из одинаковых строк наугад.
    """
    await put(session_factory, hr_row(name="Ирина", telegram_username="ira_recr"))

    answer = await ask(api.vacancies.create_options)

    assert answer["ok"]["hrs"][0]["telegram_username"] == "ira_recr"
