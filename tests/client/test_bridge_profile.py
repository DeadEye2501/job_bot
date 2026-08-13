"""Следствия слотов анкеты — того, что человек рассказывает о себе.

Навыки и опыт входят сюда же: они части одного рассказа и без анкеты не
сохраняются вовсе. Файл резюме лежит своим файлом — он не рассказ, а вложение.
"""

import json


PERSON = {
    "first_name": "Иван",
    "last_name": "Петров",
    "title": "Питон-разработчик",
    "email": "ivan@example.com",
}


async def _saved_person(main_api, watch, **extra) -> None:
    """Заводит анкету и ждёт ответа: без неё не сохранить ни навыков, ни опыта."""
    caught = watch(main_api.profile_save_done)
    main_api.save_profile(json.dumps({**PERSON, **extra}))
    assert (await caught.next())["ok"] is True


async def test_a_missing_required_field_is_refused_by_its_name(main_api, watch):
    """Незаполненное обязательное поле называют по имени.

    Анкета уходит в языковую модель письмом от лица человека. Без имени или
    без должности письмо получится безымянным, и разбираться, какого поля не
    хватило, человеку пришлось бы перебором.
    """
    caught = watch(main_api.profile_save_done)

    main_api.save_profile(json.dumps({**PERSON, "email": "   "}))

    answer = await caught.next()
    assert answer["ok"] is False
    assert answer["error"] == "Поле 'email' обязательно."


async def test_a_saved_person_comes_back_on_the_next_request(main_api, watch):
    """Сохранённая анкета возвращается при следующем открытии экрана.

    Экран открывают заново после каждого перехода по разделам, и он рисуется
    только тем, что пришло. Не вернись анкета — человек увидел бы пустую
    форму и заполнил бы её второй раз поверх сохранённой.
    """
    await _saved_person(main_api, watch)
    caught = watch(main_api.profile_changed)

    main_api.request_profile()

    profile = (await caught.next())["profile"]
    assert profile["first_name"] == "Иван"
    assert profile["title"] == "Питон-разработчик"


async def test_grades_keep_the_declared_order_not_the_clicked_one(main_api, watch):
    """Ступени ложатся в порядке объявления, а не нажатий.

    Из этой колонки собирается строка запроса к модели, и разный порядок дал
    бы разные запросы на одну и ту же анкету — а ответ модели зависит от
    текста запроса.
    """
    await _saved_person(main_api, watch, grades=["senior", "junior"])
    caught = watch(main_api.profile_changed)

    main_api.request_profile()

    assert (await caught.next())["profile"]["grades"] == ["junior", "senior"]


async def test_an_unknown_work_format_never_reaches_the_column(main_api, watch):
    """Незнакомый вид работы отбрасывается, а не ложится в колонку.

    Колонка читается как закрытый набор — по ней анкета сравнивается с
    разобранной вакансией. Чужое значение не совпало бы ни с чем и тихо
    испортило бы отбор.
    """
    await _saved_person(main_api, watch, work_format=["office", "космос"])
    caught = watch(main_api.profile_changed)

    main_api.request_profile()

    assert (await caught.next())["profile"]["work_format"] == ["office"]


async def test_an_unknown_language_level_becomes_the_usual_one(main_api, watch):
    """Незнакомый уровень языка заменяется обычным, а не роняет сохранение.

    Уровни приходят из формы, и там бывает и «свободный», и пустая строка.
    Отбей мост всю анкету — человек потерял бы и остальные поля, набранные
    в тот же заход.
    """
    await _saved_person(
        main_api,
        watch,
        languages=[{"language": "английский", "level": "свободный"}],
    )
    caught = watch(main_api.profile_changed)

    main_api.request_profile()

    languages = (await caught.next())["profile"]["languages"]
    assert languages == [{"language": "английский", "level": "B2"}]


async def test_skills_without_a_person_are_refused_by_name(main_api, watch):
    """Навыки без анкеты не сохраняют и говорят, что заводить первым.

    Навык привязан к анкете; заведись он раньше — привязывать было бы не к
    чему. Человеку при этом надо назвать порядок, а не отказать вообще.
    """
    caught = watch(main_api.skills_save_done)

    main_api.save_skills(json.dumps({"skills": [{"name": "Python"}]}))

    answer = await caught.next()
    assert answer["ok"] is False
    assert answer["error"] == "Сначала сохраните профайл (CV-таб)."


async def test_a_saved_skill_comes_back_with_its_spellings(main_api, watch):
    """Навык возвращается вместе с написаниями-синонимами.

    По ним вакансия сверяется с анкетой: в объявлениях пишут и «Postgres», и
    «PostgreSQL». Потеряйся написания — половина совпадений пропала бы.
    """
    await _saved_person(main_api, watch)
    saved = watch(main_api.skills_save_done)
    listed = watch(main_api.skills_changed)

    main_api.save_skills(
        json.dumps(
            {
                "skills": [
                    {"name": "PostgreSQL", "level": 3, "aliases": ["Postgres", "PG"]}
                ]
            }
        )
    )
    assert (await saved.next())["ok"] is True

    main_api.request_skills()
    skill = (await listed.next())["skills"][0]
    assert skill["name"] == "PostgreSQL"
    assert skill["aliases"] == ["Postgres", "PG"]


async def test_a_nameless_skill_is_dropped_not_saved_empty(main_api, watch):
    """Навык без имени не сохраняется вовсе.

    Пустая строка в списке — след незакрытой формы. Сохранись она, в анкете
    появился бы безымянный навык, который ни с чем не совпадёт и который
    человек не сможет найти, чтобы удалить.
    """
    await _saved_person(main_api, watch)
    saved = watch(main_api.skills_save_done)
    listed = watch(main_api.skills_changed)

    main_api.save_skills(
        json.dumps({"skills": [{"name": "Python"}, {"name": "   "}]})
    )
    assert (await saved.next())["ok"] is True

    main_api.request_skills()
    assert [s["name"] for s in (await listed.next())["skills"]] == ["Python"]


async def test_experience_without_a_person_is_refused_by_name(main_api, watch):
    """Опыт без анкеты не сохраняют по той же причине, что и навыки."""
    caught = watch(main_api.experience_save_done)

    main_api.save_experience(
        json.dumps({"experience": [{"company": "Контур", "role": "Разработчик"}]})
    )

    answer = await caught.next()
    assert answer["ok"] is False
    assert answer["error"] == "Сначала сохраните профайл (CV-таб)."


async def test_a_broken_experience_row_is_named_by_its_number(main_api, watch):
    """Плохую запись опыта называют её номером в списке.

    Записей бывает десяток, и они одинаковы на вид. Скажи мост просто «дата
    неверна» — человек искал бы её глазами по всему списку.
    """
    await _saved_person(main_api, watch)
    caught = watch(main_api.experience_save_done)

    main_api.save_experience(
        json.dumps(
            {
                "experience": [
                    {
                        "company": "Контур",
                        "role": "Разработчик",
                        "start_date": "2020-01-01",
                    },
                    {"company": "Рога", "role": "Старший", "start_date": "вчера"},
                ]
            }
        )
    )

    answer = await caught.next()
    assert answer["ok"] is False
    assert "#2" in answer["error"]


async def test_a_saved_experience_keeps_its_skills(main_api, watch):
    """Опыт возвращается вместе с навыками, которые к нему привязали.

    Связь ведут по имени навыка, и она нужна письму: в нём упоминают не все
    навыки подряд, а те, что относятся к месту работы.
    """
    await _saved_person(main_api, watch)
    skills_saved = watch(main_api.skills_save_done)
    main_api.save_skills(json.dumps({"skills": [{"name": "Python"}]}))
    assert (await skills_saved.next())["ok"] is True

    saved = watch(main_api.experience_save_done)
    listed = watch(main_api.experience_changed)
    main_api.save_experience(
        json.dumps(
            {
                "experience": [
                    {
                        "company": "Контур",
                        "role": "Разработчик",
                        "start_date": "2020-01-01",
                        "skill_names": ["Python"],
                    }
                ]
            }
        )
    )
    assert (await saved.next())["ok"] is True

    main_api.request_experience()
    row = (await listed.next())["experience"][0]
    assert row["company"] == "Контур"
    assert row["skill_names"] == ["Python"]
