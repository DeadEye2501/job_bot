"""Следствия правила «родной язык у разобранной анкеты есть всегда»."""

from backend.llm.cv_native import with_native_language
from backend.payloads import ParsedCvLanguage
from tests.factories import parsed_cv


def test_a_resume_written_in_russian_gives_a_native_russian():
    parsed = parsed_cv()

    filled = with_native_language(parsed, "Электрик. Опыт работы 8 лет.")

    assert [(x.language, x.level) for x in filled.languages] == [("Русский", "native")]


def test_a_resume_written_in_latin_gives_a_native_english():
    parsed = parsed_cv()

    filled = with_native_language(parsed, "Electrician. Eight years of experience.")

    assert [(x.language, x.level) for x in filled.languages] == [("English", "native")]


def test_a_russian_resume_full_of_latin_terms_is_still_russian():
    """Резюме разработчика: текст русский, а технологии названы латиницей.

    Доля латиницы взята как в настоящем резюме — около четверти. Одна
    выхваченная строка «Стек: Python, Django, PostgreSQL» латиницей
    перевешивает, но резюме из таких строк не состоит.
    """
    parsed = parsed_cv()

    filled = with_native_language(
        parsed,
        "Python backend разработчик с опытом более семи лет. Несколько раз "
        "запускал проекты с нуля — от проектирования архитектуры и схемы "
        "данных до вывода в production. Хорошо понимаю весь жизненный цикл "
        "разработки, умею делать гибкие и масштабируемые модели данных под "
        "задачи бизнеса.\nСтек: Python, Django, PostgreSQL, Docker, Redis.",
    )

    assert [x.language for x in filled.languages] == ["Русский"]


def test_the_resume_language_already_native_is_not_doubled():
    """Язык резюме уже назван родным — второй такой же строки не заводят."""
    parsed = parsed_cv(
        languages=[ParsedCvLanguage(language="Русский", level="native")]
    )

    filled = with_native_language(parsed, "Инженер. Родной язык — русский.")

    assert [(x.language, x.level) for x in filled.languages] == [
        ("Русский", "native")
    ]


def test_a_native_named_by_the_person_stays_the_only_one():
    """Родной язык человек назвал сам — угадывать больше нечего.

    Резюме при этом написано по-русски, и русский в анкету попадает, но уже
    высшим уровнем, а не вторым родным: своё слово человека сильнее нашего
    вывода из языка письма.
    """
    parsed = parsed_cv(
        languages=[ParsedCvLanguage(language="Армянский", level="native")]
    )

    filled = with_native_language(parsed, "Инженер. Родной язык — армянский.")

    assert [(x.language, x.level) for x in filled.languages] == [
        ("Русский", "C2"),
        ("Армянский", "native"),
    ]


def test_the_native_language_comes_first_and_keeps_the_others():
    """Прочие языки остаются на месте, родной встаёт перед ними."""
    parsed = parsed_cv(languages=[ParsedCvLanguage(language="Английский", level="B2")])

    filled = with_native_language(parsed, "Инженер. Английский — B2.")

    assert [(x.language, x.level) for x in filled.languages] == [
        ("Русский", "native"),
        ("Английский", "B2"),
    ]


def test_the_resume_language_already_listed_becomes_native():
    """Язык резюме уже назван строкой — ему меняют уровень, а не двоят его."""
    parsed = parsed_cv(languages=[ParsedCvLanguage(language="Русский", level="B2")])

    filled = with_native_language(parsed, "Инженер. Русский — B2.")

    assert [(x.language, x.level) for x in filled.languages] == [("Русский", "native")]


def test_the_resume_language_listed_in_another_case_is_not_doubled():
    """Модель пишет язык строчной буквой — это тот же язык, а не второй."""
    parsed = parsed_cv(languages=[ParsedCvLanguage(language="русский", level="C2")])

    filled = with_native_language(parsed, "Инженер. Русский язык — C2.")

    assert [(x.language, x.level) for x in filled.languages] == [("русский", "native")]


def test_the_resume_language_is_not_lost_beside_another_native():
    """Родным назван чужой язык — язык резюме всё равно попадает в анкету.

    Спроси мы только «есть ли хоть один родной» — русского в анкете не
    оказалось бы вовсе, а родным числился бы английский.
    """
    parsed = parsed_cv(
        languages=[ParsedCvLanguage(language="Английский", level="native")]
    )

    filled = with_native_language(parsed, "Инженер-конструктор. Английский — Advanced.")

    assert ("Русский", "C2") in [(x.language, x.level) for x in filled.languages]
