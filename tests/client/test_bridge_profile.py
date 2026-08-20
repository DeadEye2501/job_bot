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
        "grades": [],
        "work_format": [],
        "languages": [],
    }


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
