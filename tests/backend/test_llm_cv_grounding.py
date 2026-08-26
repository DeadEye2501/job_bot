"""Следствия сверки разобранного резюме с его же текстом.

Модель на запрет «не выдумывай» полагаться не даёт: маленькая её не держит.
Отсюда проверка кодом — по тем полям, где выдумка меняет отбор вакансий.
"""

from backend.llm.cv_grounding import grounded_in_cv
from backend.payloads import ParsedCvLanguage
from tests.factories import parsed_cv, parsed_cv_place, parsed_cv_profile, parsed_cv_skill


def test_a_language_the_resume_never_names_is_dropped():
    """Резюме маркетолога языков не называет, а модель дописала родной."""
    parsed = parsed_cv(languages=[ParsedCvLanguage(language="Русский", level="native")])

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
