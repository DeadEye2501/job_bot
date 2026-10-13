"""Что в разобранных местах работы и проектах не подтверждается текстом резюме.

Отделено от прочей сверки предметом: там проверяют отдельные значения —
грейд, формат работы, язык, — а здесь сперва находят в тексте кусок самой
записи, и уже в нём смотрят, откуда взялся её стек. Граница куска и есть
то, что здесь сторожат.
"""

from backend.llm.cv_grounding import grounded_in_cv
from tests.factories_cv import parsed_cv, parsed_cv_place, parsed_cv_project


def test_a_stack_is_dropped_when_the_job_has_no_stack_section():
    """Стек, которого у работы нет, собирается из её же обязанностей.

    Модель видит «Корректировки в 1С» и кладёт 1С в стек работы. Названия при
    этом настоящие — выдумано их место, и потому сверка по одному лишь
    присутствию в тексте такого не ловит.
    """
    parsed = parsed_cv(
        experience=[
            parsed_cv_place(
                company="ООО «Адвант»", stack=["1С: Предприятие 8.3", "Диадок"]
            )
        ]
    )
    text = (
        "ООО «Адвант», г. Томск\n"
        "Обязанности:\n"
        "- Корректировки в «1С: Предприятие 8.3»\n"
        "- Отправка документов в «Диадок»\n"
    )

    grounded = grounded_in_cv(parsed, text)

    assert grounded.experience[0].stack == []


def test_a_word_that_merely_starts_like_the_company_is_not_its_heading():
    """Слово, начинающееся как название компании, границей работы не считается.

    Шапку работы ищут с начала строки, и короткое название легко оказывается
    началом чужого слова. Прими его за шапку — граница уедет вверх, и всё, что
    ниже, отойдёт следующей работе вместе с её стеком.
    """
    parsed = parsed_cv(
        experience=[
            parsed_cv_place(company="Контур", stack=["Python"]),
            parsed_cv_place(company="АСТ", stack=[]),
        ]
    )
    text = (
        "Контур, Екатеринбург\n"
        "Астрономия — увлечение\n"
        "Технологии: Python\n"
        "АСТ, Москва\n"
    )

    grounded = grounded_in_cv(parsed, text)

    assert grounded.experience[0].stack == ["Python"]


def test_a_stack_under_its_own_heading_survives():
    parsed = parsed_cv(
        experience=[parsed_cv_place(company="Контур", stack=["Python", "Django"])]
    )
    text = "Контур\nBackend разработчик\n\nСтек:\n    Python | Django\n"

    grounded = grounded_in_cv(parsed, text)

    assert grounded.experience[0].stack == ["Python", "Django"]


def test_a_stack_of_a_job_not_found_in_the_text_survives():
    """Работу в тексте не нашли — проверять нечем, и стек остаётся."""
    parsed = parsed_cv(
        experience=[parsed_cv_place(company="Переименованная", stack=["Python"])]
    )

    grounded = grounded_in_cv(parsed, "Резюме, где такой компании не значится.")

    assert grounded.experience[0].stack == ["Python"]


def test_each_job_is_asked_about_its_own_heading():
    """У первой работы стек назван, у второй нет — вторая его и лишается."""
    parsed = parsed_cv(
        experience=[
            parsed_cv_place(company="Первая", stack=["Python"]),
            parsed_cv_place(company="Вторая", stack=["Django"]),
        ]
    )
    text = (
        "Первая\nСтек:\n    Python\n\n"
        "Вторая\nОбязанности:\n- Поддержка сервисов на Django\n"
    )

    grounded = grounded_in_cv(parsed, text)

    assert [place.stack for place in grounded.experience] == [["Python"], []]


def test_a_heading_word_inside_a_company_name_is_not_a_heading():
    """«ООО Инновационные технологии безопасности» — не раздел «Технологии».

    Заголовок стоит с начала строки, и спрашивать надо именно это. Ищи слово
    где попало — и любая компания, назвавшаяся технологиями, инструментами или
    решениями, разрешила бы себе стек, которого в резюме нет.
    """
    parsed = parsed_cv(
        experience=[
            parsed_cv_place(
                company="ООО «Инновационные технологии безопасности»",
                stack=["1С:Предприятие 7.7", "Парус-Бухгалтерия"],
            )
        ]
    )
    text = (
        "Компания: ООО «Инновационные технологии безопасности»\n"
        "Обязанности:\n- Ведение учёта\n\n"
        "Ключевые навыки\n- 1С 7.7 и 8.3, Парус-Бухгалтерия\n"
    )

    grounded = grounded_in_cv(parsed, text)

    assert grounded.experience[0].stack == []


def test_a_company_named_after_a_heading_word_does_not_authorise_itself():
    """«Технологии Доверия» — имя работодателя, а не заголовок его стека.

    Кусок работы начинается с её названия, и заголовок ищется с начала строки.
    Не отступи от названия — и всякая компания, чьё имя начинается со слова из
    перечня, разрешила бы себе стек одним своим именем.
    """
    parsed = parsed_cv(
        experience=[
            parsed_cv_place(company="Технологии Доверия", stack=["1С", "Диадок"])
        ]
    )
    text = "Технологии Доверия\nОбязанности:\n- Отправка документов в «Диадок» из 1С\n"

    grounded = grounded_in_cv(parsed, text)

    assert grounded.experience[0].stack == []


def test_a_company_mentioned_in_the_summary_does_not_shrink_its_block():
    """«О себе: 8 лет в Контуре» — не то место, где начинается работа.

    Ищи название с начала текста — и кусок работы съёжится до упоминания в
    шапке, заголовка стека там не будет, и настоящий стек пропадёт.
    """
    parsed = parsed_cv(
        experience=[
            parsed_cv_place(company="Контур", stack=["Python", "Django"]),
            parsed_cv_place(company="Сбер", stack=["Java"]),
        ]
    )
    text = (
        "О себе\nВосемь лет в Контуре и Сбере.\n\n"
        "Опыт работы\n\nКонтур\nBackend разработчик\n\nСтек:\n    Python | Django\n\n"
        "Сбер\nBackend разработчик\n\nСтек:\n    Java\n"
    )

    grounded = grounded_in_cv(parsed, text)

    assert [place.stack for place in grounded.experience] == [
        ["Python", "Django"],
        ["Java"],
    ]


def test_the_last_job_ends_where_the_projects_begin():
    """Проекты — граница последней работы: стек проекта ей не зачитывается."""
    parsed = parsed_cv(
        experience=[parsed_cv_place(company="Контур", stack=["Go"])],
        projects=[parsed_cv_project(name="Бот", stack=["Python"])],
    )
    text = (
        "Контур\n"
        "Обязанности:\n"
        "- сервисы на Go\n"
        "Проекты\n"
        "Бот\n"
        "Стек: Python\n"
    )

    grounded = grounded_in_cv(parsed, text)

    assert grounded.experience[0].stack == []
    assert grounded.projects[0].stack == ["Python"]


def test_projects_above_the_jobs_are_bounded_all_the_same():
    """Раздел проектов бывает и выше опыта: и тогда у каждой записи свой кусок."""
    parsed = parsed_cv(
        experience=[parsed_cv_place(company="Контур", stack=["Go"])],
        projects=[parsed_cv_project(name="Бот", stack=["Python"])],
    )
    text = (
        "Проекты\n"
        "Бот\n"
        "- бот на Python\n"
        "Опыт работы\n"
        "Контур\n"
        "Стек: Go\n"
    )

    grounded = grounded_in_cv(parsed, text)

    assert grounded.projects[0].stack == []
    assert grounded.experience[0].stack == ["Go"]


def test_a_project_without_a_stack_section_keeps_no_stack():
    """Стек проекта проверяется тем же правилом, что стек работы."""
    parsed = parsed_cv(projects=[parsed_cv_project(name="Бот", stack=["Python"])])

    grounded = grounded_in_cv(parsed, "Проекты\nБот\n- бот на Python\n")

    assert grounded.projects[0].stack == []


def test_a_stack_heading_is_recognised_however_it_is_written():
    """Заголовок стека пишут по-разному, и своего стека из-за этого не лишают."""
    for heading in (
        "Стек:",
        "Стэк:",
        "• Стек:",
        "Технологический стек:",
        "Использованные технологии:",
        "Tech stack:",
        "Technologies:",
        "Инструменты:",
    ):
        parsed = parsed_cv(
            experience=[parsed_cv_place(company="Контур", stack=["Python"])]
        )
        text = f"Контур\nBackend разработчик\n\n{heading}\n    Python\n"

        grounded = grounded_in_cv(parsed, text)

        assert grounded.experience[0].stack == ["Python"], heading


