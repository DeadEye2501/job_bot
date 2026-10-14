"""Следствия слотов анкеты — того, что человек рассказывает о себе.

Навыки и опыт входят сюда же: они части одного рассказа и без анкеты не
сохраняются вовсе. Файл резюме лежит своим файлом — он не рассказ, а вложение.
"""

PERSON = {
    "first_name": "Иван",
    "last_name": "Петров",
    "title": "Питон-разработчик",
    "email": "ivan@example.com",
}


async def _saved_person(api, ask, **extra) -> None:
    """Заводит анкету и ждёт ответа: без неё не сохранить ни навыков, ни опыта."""
    answer = await ask(api.profile.save, {**PERSON, **extra})
    assert answer["ok"] == {}


async def test_a_missing_required_field_is_refused_by_its_name(api, ask):
    """Незаполненное обязательное поле называют по имени.

    Анкета уходит в языковую модель письмом от лица человека. Без имени или
    без должности письмо получится безымянным, и разбираться, какого поля не
    хватило, человеку пришлось бы перебором.
    """
    answer = await ask(api.profile.save, {**PERSON, "email": "   "})

    assert answer["fail"] == "denied"
    assert answer["detail"] == "Поле 'email' обязательно."


async def test_a_saved_person_comes_back_on_the_next_request(api, ask):
    """Сохранённая анкета возвращается при следующем открытии экрана.

    Экран открывают заново после каждого перехода по разделам, и он рисуется
    только тем, что пришло. Не вернись анкета — человек увидел бы пустую
    форму и заполнил бы её второй раз поверх сохранённой.
    """
    await _saved_person(api, ask, education="МГУ", location="Москва")

    answer = await ask(api.profile.get)

    profile = answer["ok"]["profile"]
    # Целиком, а не выборочно: экран рисуется только тем, что пришло, и
    # потерянное по дороге поле он показал бы пустым — а следующее нажатие
    # сохранило бы эту пустоту поверх записанного. Метка правки идёт особняком:
    # её ставит сама запись, и значение её тут не предмет.
    assert profile.pop("updated_at") is not None
    assert profile == {
        "first_name": "Иван",
        "last_name": "Петров",
        "title": "Питон-разработчик",
        "email": "ivan@example.com",
        "phone": None,
        "location": "Москва",
        "telegram_username": None,
        "github_url": None,
        "education": "МГУ",
        "free_preferences": None,
        "expected_salary": None,
        "expected_salary_currency": None,
        "expected_salary_period": None,
        "first_name_latin": None,
        "last_name_latin": None,
        "gender": None,
        "patronymic": None, "patronymic_latin": None, "birth_date": None,
        "citizenship": None, "about_me": None, "resume_url": None,
        "grades": [],
        "work_format": [],
        "languages": [],
    }


async def test_the_answers_for_forms_come_back_as_saved(api, ask):
    await ask(api.profile.save, {
        **PERSON, "expected_salary": "250000", "expected_salary_currency": "RUB",
        "expected_salary_period": "month", "first_name_latin": " Ivan ",
        "last_name_latin": "Petrov", "gender": "male",
    })

    profile = (await ask(api.profile.get))["ok"]["profile"]

    assert {k: profile[k] for k in (
        "expected_salary", "expected_salary_currency", "expected_salary_period",
        "first_name_latin", "last_name_latin", "gender",
    )} == {
        "expected_salary": 250000, "expected_salary_currency": "₽",
        "expected_salary_period": "month", "first_name_latin": "Ivan",
        "last_name_latin": "Petrov", "gender": "male",
    }


async def test_the_new_personal_fields_come_back_as_saved(api, ask):
    await ask(api.profile.save, {
        **PERSON, "patronymic": " Сергеевич ", "patronymic_latin": "Sergeevich",
        "birth_date": "1990-03-15", "citizenship": "Россия",
        "about_me": "Строю сервисы.\nЛюблю тесты.", "resume_url": "https://hh.ru/resume/1",
    })

    profile = (await ask(api.profile.get))["ok"]["profile"]

    assert {k: profile[k] for k in (
        "patronymic", "patronymic_latin", "birth_date", "citizenship", "about_me", "resume_url",
    )} == {
        "patronymic": "Сергеевич", "patronymic_latin": "Sergeevich",
        "birth_date": "1990-03-15", "citizenship": "Россия",
        "about_me": "Строю сервисы.\nЛюблю тесты.", "resume_url": "https://hh.ru/resume/1",
    }


async def test_a_wrong_birth_date_is_refused_by_its_name_and_nothing_is_written(api, ask):
    """Негодная дата рождения отбивает всю запись, и отказ называет поле.

    Запись идёт после каждой правки: ляг остальное без даты, человек не узнал
    бы, что набранное в календаре пропало.
    """
    await _saved_person(api, ask, education="МГУ")

    answer = await ask(api.profile.save, {**PERSON, "education": "СПбГУ",
                                          "birth_date": "15.03.1990"})

    assert answer["fail"] == "fields"
    assert "дата рождения" in answer["detail"]
    profile = (await ask(api.profile.get))["ok"]["profile"]
    assert (profile["education"], profile["birth_date"]) == ("МГУ", None)


async def test_a_zero_salary_is_saved_as_no_salary(api, ask):
    """Ноль — «не названо» и в окне, и в разборе резюме: правило у путей одно."""
    await ask(api.profile.save, {**PERSON, "expected_salary": "0"})

    assert (await ask(api.profile.get))["ok"]["profile"]["expected_salary"] is None


async def test_an_unknown_gender_or_currency_never_reaches_the_column(api, ask):
    await ask(api.profile.save, {
        **PERSON, "gender": "другое", "expected_salary_currency": "тугрики",
    })

    profile = (await ask(api.profile.get))["ok"]["profile"]

    assert (profile["gender"], profile["expected_salary_currency"]) == (None, None)


async def test_grades_keep_the_declared_order_not_the_clicked_one(api, ask):
    """Ступени ложатся в порядке объявления, а не нажатий.

    Из этой колонки собирается строка запроса к модели, и разный порядок дал
    бы разные запросы на одну и ту же анкету — а ответ модели зависит от
    текста запроса.
    """
    await _saved_person(api, ask, grades=["senior", "junior"])

    answer = await ask(api.profile.get)

    assert answer["ok"]["profile"]["grades"] == ["junior", "senior"]


async def test_an_unknown_work_format_never_reaches_the_column(api, ask):
    """Незнакомый вид работы отбрасывается, а не ложится в колонку.

    Колонка читается как закрытый набор — по ней анкета сравнивается с
    разобранной вакансией. Чужое значение не совпало бы ни с чем и тихо
    испортило бы отбор.
    """
    await _saved_person(api, ask, work_format=["office", "космос"])

    answer = await ask(api.profile.get)

    assert answer["ok"]["profile"]["work_format"] == ["office"]


async def test_an_unknown_language_level_becomes_the_usual_one(api, ask):
    """Незнакомый уровень языка заменяется обычным, а не роняет сохранение.

    Уровни приходят из формы, и там бывает и «свободный», и пустая строка.
    Отбей мост всю анкету — человек потерял бы и остальные поля, набранные
    в тот же заход.
    """
    await _saved_person(
        api,
        ask,
        languages=[{"language": "английский", "level": "свободный"}],
    )

    answer = await ask(api.profile.get)

    languages = answer["ok"]["profile"]["languages"]
    assert languages == [{"language": "английский", "level": "B2"}]


async def test_skills_without_a_person_are_refused_by_name(api, ask):
    """Навыки без анкеты не сохраняют и говорят, что заводить первым.

    Навык привязан к анкете; заведись он раньше — привязывать было бы не к
    чему. Человеку при этом надо назвать порядок, а не отказать вообще.
    """
    answer = await ask(api.profile.save_skills, {"skills": [{"name": "Python"}]})

    assert answer["fail"] == "denied"
    assert answer["detail"] == "Сначала сохраните профайл (CV-таб)."


async def test_a_saved_skill_comes_back_with_its_spellings(api, ask):
    """Навык возвращается вместе с написаниями-синонимами.

    По ним вакансия сверяется с анкетой: в объявлениях пишут и «Postgres», и
    «PostgreSQL». Потеряйся написания — половина совпадений пропала бы.
    """
    await _saved_person(api, ask)

    saved = await ask(
        api.profile.save_skills,
        {"skills": [{"name": "PostgreSQL", "level": 3, "aliases": ["Postgres", "PG"]}]},
    )
    assert saved["ok"] == {}

    listed = await ask(api.profile.skills)
    skill = listed["ok"]["skills"][0]
    assert skill["name"] == "PostgreSQL"
    assert skill["aliases"] == ["Postgres", "PG"]


async def test_a_nameless_skill_is_dropped_not_saved_empty(api, ask):
    """Навык без имени не сохраняется вовсе.

    Пустая строка в списке — след незакрытой формы. Сохранись она, в анкете
    появился бы безымянный навык, который ни с чем не совпадёт и который
    человек не сможет найти, чтобы удалить.
    """
    await _saved_person(api, ask)

    saved = await ask(
        api.profile.save_skills, {"skills": [{"name": "Python"}, {"name": "   "}]}
    )
    assert saved["ok"] == {}

    listed = await ask(api.profile.skills)
    assert [s["name"] for s in listed["ok"]["skills"]] == ["Python"]


async def test_experience_without_a_person_is_refused_by_name(api, ask):
    """Опыт без анкеты не сохраняют по той же причине, что и навыки."""
    answer = await ask(
        api.profile.save_experience,
        {"experience": [{"company": "Контур", "role": "Разработчик"}]},
    )

    assert answer["fail"] == "denied"
    assert answer["detail"] == "Сначала сохраните профайл (CV-таб)."


async def test_a_broken_experience_row_is_named_by_its_number(api, ask):
    """Плохую запись опыта называют её номером в списке.

    Записей бывает десяток, и они одинаковы на вид. Скажи мост просто «дата
    неверна» — человек искал бы её глазами по всему списку.
    """
    await _saved_person(api, ask)

    answer = await ask(
        api.profile.save_experience,
        {
            "experience": [
                {
                    "company": "Контур",
                    "role": "Разработчик",
                    "start_date": "2020-01-01",
                },
                {"company": "Рога", "role": "Старший", "start_date": "вчера"},
            ]
        },
    )

    assert answer["fail"] == "denied"
    assert "#2" in answer["detail"]


async def test_a_saved_experience_keeps_its_skills(api, ask):
    """Опыт возвращается вместе с навыками, которые к нему привязали.

    Связь ведут по имени навыка, и она нужна письму: в нём упоминают не все
    навыки подряд, а те, что относятся к месту работы.
    """
    await _saved_person(api, ask)
    skills_saved = await ask(api.profile.save_skills, {"skills": [{"name": "Python"}]})
    assert skills_saved["ok"] == {}

    saved = await ask(
        api.profile.save_experience,
        {
            "experience": [
                {
                    "company": "Контур",
                    "role": "Разработчик",
                    "start_date": "2020-01-01",
                    "skill_names": ["Python"],
                }
            ]
        },
    )
    assert saved["ok"] == {}

    listed = await ask(api.profile.experience)
    row = listed["ok"]["experience"][0]
    assert row["company"] == "Контур"
    assert row["skill_names"] == ["Python"]


async def test_a_saved_project_comes_back_with_its_stack(api, ask):
    await _saved_person(api, ask)
    await ask(api.profile.save_skills, {"skills": [{"name": "Python"}]})

    saved = await ask(api.profile.save_projects, {"projects": [{
        "name": "Бот", "url": "https://example.org/bot",
        "about": ["Описание"], "skill_names": ["Python"],
    }]})
    assert saved["ok"] == {}

    listed = (await ask(api.profile.projects))["ok"]
    project = listed["projects"][0]
    assert {k: v for k, v in project.items() if k != "id"} == {
        "name": "Бот", "url": "https://example.org/bot",
        "about": ["Описание"], "skill_names": ["Python"],
    }
    assert [s["name"] for s in listed["skills_index"]] == ["Python"]


async def test_a_nameless_project_is_refused_by_its_number(api, ask):
    await _saved_person(api, ask)

    answer = await ask(api.profile.save_projects, {"projects": [{"name": "Бот"}, {"name": ""}]})

    assert answer["fail"] == "denied"
    assert "#2" in answer["detail"]


async def test_projects_without_a_person_are_refused_by_name(api, ask):
    answer = await ask(api.profile.save_projects, {"projects": [{"name": "Бот"}]})

    assert answer["fail"] == "denied"
    assert answer["detail"] == "Сначала сохраните профайл (CV-таб)."
