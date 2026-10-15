"""Решение, на каком языке писать: человеку — на его языке, работодателю — на языке вакансии."""

import pytest

from backend.domain.language_choice import person_language, reply_language, search_languages
from backend.llm.candidate import CandidateLanguage


@pytest.mark.parametrize(
    ("languages", "expected"),
    [
        pytest.param(
            [CandidateLanguage("Английский", "C1"), CandidateLanguage("Армянский", "native"),
             CandidateLanguage("Русский", "native")],
            "Армянский", id="первый родной"),
        pytest.param([CandidateLanguage("Испанский", "B2")], "English", id="родного нет"),
        pytest.param([], "English", id="языков нет"),
    ],
)
def test_the_person_language_is_the_first_native_one(languages, expected):
    """Язык человека — первый родной в его списке, без родного — английский."""
    assert person_language(languages) == expected


@pytest.mark.parametrize(
    ("vacancy", "expected"),
    [
        pytest.param("Español", "Español", id="язык вакансии известен"),
        pytest.param(None, "Қазақша", id="язык вакансии неизвестен"),
    ],
)
def test_a_reply_goes_in_the_vacancy_language(vacancy, expected):
    """Отклик — на языке вакансии; неизвестен он — на языке человека."""
    assert reply_language(vacancy, "Қазақша") == expected


def test_work_is_searched_in_native_languages_and_from_b1():
    """Ищут на родных языках и на тех, где уровень не ниже B1: ниже — работать на нём нельзя."""
    languages = [CandidateLanguage("Қазақша", "native"), CandidateLanguage("English", "B1"),
                 CandidateLanguage("Deutsch", "A2"), CandidateLanguage("Español", "C2")]

    assert search_languages(languages) == ["Қазақша", "English", "Español"]


def test_without_a_usable_language_work_is_searched_in_the_person_language():
    assert search_languages([CandidateLanguage("Deutsch", "A2")]) == ["English"]
