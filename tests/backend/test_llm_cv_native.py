"""Следствия правила «резюме не называет родного — родной язык его текста»."""

from backend.llm.cv_native import with_native_language
from backend.payloads import ParsedCvLanguage
from tests.factories_cv import parsed_cv


def _levels(parsed):
    return [(x.language, x.level) for x in parsed.languages]


def test_the_language_the_model_names_for_the_text_becomes_native():
    """Язык текста называет модель: по буквам латиница не отличает испанский
    от английского."""
    filled = with_native_language(parsed_cv(text_language="Español"))

    assert _levels(filled) == [("Español", "native")]


def test_an_unnamed_text_language_adds_nothing():
    filled = with_native_language(
        parsed_cv(languages=[ParsedCvLanguage(language="Английский", level="B2")]))

    assert _levels(filled) == [("Английский", "B2")]


def test_the_resume_language_already_native_is_not_doubled():
    """Язык резюме уже назван родным — второй такой же строки не заводят."""
    parsed = parsed_cv(
        languages=[ParsedCvLanguage(language="Русский", level="native")], text_language="Русский")

    assert _levels(with_native_language(parsed)) == [("Русский", "native")]


def test_a_native_named_by_the_person_stays_the_only_one():
    """Родной язык человек назвал сам — язык текста попадает в анкету высшим
    уровнем, а не вторым родным: своё слово человека сильнее вывода из языка
    письма."""
    parsed = parsed_cv(
        languages=[ParsedCvLanguage(language="Армянский", level="native")], text_language="Русский")

    assert _levels(with_native_language(parsed)) == [("Русский", "C2"), ("Армянский", "native")]


def test_the_native_language_comes_first_and_keeps_the_others():
    """Прочие языки остаются на месте, родной встаёт перед ними."""
    parsed = parsed_cv(
        languages=[ParsedCvLanguage(language="Английский", level="B2")], text_language="Русский")

    assert _levels(with_native_language(parsed)) == [("Русский", "native"), ("Английский", "B2")]


def test_the_resume_language_already_listed_becomes_native():
    """Язык резюме уже назван строкой — ему меняют уровень, а не двоят его."""
    parsed = parsed_cv(
        languages=[ParsedCvLanguage(language="Русский", level="B2")], text_language="Русский")

    assert _levels(with_native_language(parsed)) == [("Русский", "native")]


def test_the_resume_language_listed_in_another_case_is_not_doubled():
    """Модель пишет язык строчной буквой — это тот же язык, а не второй."""
    parsed = parsed_cv(
        languages=[ParsedCvLanguage(language="русский", level="C2")], text_language="Русский")

    assert _levels(with_native_language(parsed)) == [("русский", "native")]
