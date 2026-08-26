"""Следствия сверки разобранного резюме с его же текстом.

Модель на запрет «не выдумывай» полагаться не даёт: маленькая её не держит.
Отсюда проверка кодом — по тем полям, где выдумка меняет отбор вакансий.
"""

from backend.llm.cv_grounding import grounded_in_cv
from backend.payloads import ParsedCvLanguage
from tests.factories import parsed_cv, parsed_cv_place, parsed_cv_profile, parsed_cv_skill


def test_a_language_the_resume_never_names_is_dropped():
    """Резюме маркетолога языков не называет, а модель дописала французский."""
    parsed = parsed_cv(
        languages=[ParsedCvLanguage(language="Французский", level="B2")]
    )

    grounded = grounded_in_cv(parsed, "Маркетолог. Яндекс.Директ, Google Ads, CRM.")

    assert grounded.languages == []


def test_a_language_the_resume_names_survives():
    parsed = parsed_cv(languages=[ParsedCvLanguage(language="Английский", level="B2")])

    grounded = grounded_in_cv(parsed, "Иностранные языки: Английский — B2")

    assert [lang.language for lang in grounded.languages] == ["Английский"]


def test_a_language_named_in_a_declined_form_survives():
    """«Владею английским» — тот же язык, лишь в другом падеже."""
    parsed = parsed_cv(languages=[ParsedCvLanguage(language="Английский", level="B2")])

    grounded = grounded_in_cv(parsed, "Свободно владею английским, читаю документацию.")

    assert [lang.language for lang in grounded.languages] == ["Английский"]


def test_a_grade_the_resume_never_names_is_dropped():
    """У электрика в резюме нет ни слова о грейде, а модель выдала два."""
    parsed = parsed_cv(profile=parsed_cv_profile(grades=["middle", "senior"]))

    grounded = grounded_in_cv(parsed, "Электрик. Опыт работы 8 лет. Группа допуска 4.")

    assert grounded.profile.grades == []


def test_a_grade_the_resume_names_survives():
    parsed = parsed_cv(profile=parsed_cv_profile(grades=["senior"]))

    grounded = grounded_in_cv(parsed, "Senior Python Developer, ищу удалённую работу.")

    assert grounded.profile.grades == ["senior"]


def test_a_grade_named_in_russian_survives():
    """Своё звание пишут и по-русски, и терять его из-за этого незачем."""
    parsed = parsed_cv(profile=parsed_cv_profile(grades=["lead"]))

    grounded = grounded_in_cv(parsed, "Ищу позицию тимлида в продуктовой команде.")

    assert grounded.profile.grades == ["lead"]


def test_the_rest_of_the_resume_is_left_alone():
    """Сверка касается двух полей; навыки, опыт и прочий профиль не её дело."""
    parsed = parsed_cv(
        profile=parsed_cv_profile(location="Ереван", education="МИРЭА"),
        skills=[parsed_cv_skill("Python")],
        experience=[parsed_cv_place(company="Контур")],
    )

    grounded = grounded_in_cv(parsed, "Резюме без единого слова про грейды и языки.")

    assert [skill.name for skill in grounded.skills] == ["Python"]
    assert [place.company for place in grounded.experience] == ["Контур"]
    assert grounded.profile.location == "Ереван"
    assert grounded.profile.education == "МИРЭА"


def test_a_language_whose_name_is_too_short_to_check_survives():
    """«中文» проверить нечем: корня у такого имени не бывает.

    Непроверяемое остаётся. Сверка заведена против выдумки, а выбросить
    настоящее — беда крупнее той, от которой она сторожит.
    """
    parsed = parsed_cv(languages=[ParsedCvLanguage(language="中文", level="B1")])

    grounded = grounded_in_cv(parsed, "Резюме на русском языке без слова «китайский».")

    assert [lang.language for lang in grounded.languages] == ["中文"]


def test_a_grade_is_not_confirmed_by_a_word_it_merely_hides_inside():
    """«middleware» — не грейд, «валидация» — не лид.

    Ищи сверка подстрокой без границ слова, и выдуманный грейд подтверждался
    бы любым словом, внутри которого он случайно оказался.
    """
    parsed = parsed_cv(profile=parsed_cv_profile(grades=["middle", "lead"]))

    grounded = grounded_in_cv(
        parsed, "Писал middleware, занимался валидацией и консолидацией отчётов."
    )

    assert grounded.profile.grades == []


def test_a_grade_named_with_a_russian_ending_survives():
    """Звание в тексте склоняют: «сеньора», «джуна», «тимлида»."""
    parsed = parsed_cv(profile=parsed_cv_profile(grades=["senior"]))

    grounded = grounded_in_cv(parsed, "Ищу работу сеньора в продуктовой команде.")

    assert grounded.profile.grades == ["senior"]


def test_a_grade_named_as_an_intern_survives():
    """«Стажёр» — то же звание, что junior, и терять его незачем."""
    parsed = parsed_cv(profile=parsed_cv_profile(grades=["junior"]))

    grounded = grounded_in_cv(parsed, "Стажёр отдела аналитики, ищу первую работу.")

    assert grounded.profile.grades == ["junior"]


def test_an_invented_native_language_is_dropped_like_any_other():
    """Родному языку поблажки нет, и это главное здесь.

    Модель выводит родной язык из фамилии кандидата. Освободи его от сверки —
    и выдуманный «Армянский» пройдёт в анкету, а настоящий язык резюме уже не
    добавится: родной ведь формально есть. Дыра открывается ровно там, ради
    чего сверка заведена.
    """
    parsed = parsed_cv(
        languages=[ParsedCvLanguage(language="Армянский", level="native")]
    )

    grounded = grounded_in_cv(parsed, "Саркисян Ашот. Электрик. Опыт 8 лет.")

    assert grounded.languages == []


def test_a_language_level_the_text_never_names_drops_to_the_lowest():
    """Уровень тоже сверяется с текстом, а не только сам язык.

    «Английский (разговорный)» модель превращает в B1 или B2 — по настроению.
    Ни того, ни другого в резюме нет, а по уровню языка отбирают вакансии:
    выдуманный C1 приведёт к объявлениям, где человеку работать нечем.
    """
    parsed = parsed_cv(languages=[ParsedCvLanguage(language="Английский", level="B1")])

    grounded = grounded_in_cv(parsed, "Иностранные языки: английский (разговорный)")

    assert [(x.language, x.level) for x in grounded.languages] == [
        ("Английский", "A1")
    ]


def test_a_language_level_named_in_the_text_survives():
    parsed = parsed_cv(languages=[ParsedCvLanguage(language="Английский", level="C1")])

    grounded = grounded_in_cv(parsed, "Иностранные языки: английский — C1")

    assert [(x.language, x.level) for x in grounded.languages] == [
        ("Английский", "C1")
    ]


def test_a_native_level_is_not_asked_to_be_named_in_the_text():
    """Родной уровень выводится из языка письма, в тексте его слова нет."""
    parsed = parsed_cv(
        languages=[ParsedCvLanguage(language="Английский", level="native")]
    )

    grounded = grounded_in_cv(parsed, "Иностранные языки: английский")

    assert [(x.language, x.level) for x in grounded.languages] == [
        ("Английский", "native")
    ]


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


def test_a_stack_under_its_own_heading_survives():
    parsed = parsed_cv(
        experience=[parsed_cv_place(company="Mindcheckapp", stack=["Python", "Django"])]
    )
    text = "Mindcheckapp\nBackend разработчик\n\nСтек:\n    Python | Django\n"

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


def test_a_level_hidden_inside_another_word_does_not_confirm_it():
    """«B2B-продажи» — не уровень английского B2."""
    parsed = parsed_cv(languages=[ParsedCvLanguage(language="Английский", level="B2")])

    grounded = grounded_in_cv(parsed, "Английский. Опыт B2B-продаж и работы с CRM.")

    assert [(x.language, x.level) for x in grounded.languages] == [
        ("Английский", "A1")
    ]


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
