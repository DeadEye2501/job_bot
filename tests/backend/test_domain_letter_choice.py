"""Выбор готового письма человека: язык по языку отклика, длина по пределу."""

from types import SimpleNamespace

import pytest

from backend.domain.letter_choice import ready_letter


def _letters(**over):
    return SimpleNamespace(**{"ru": "Полное", "ru_short": "Кратко", "en": "Full one", "en_short": "Short",
                              **over})


@pytest.mark.parametrize("language", ["Русский", "русский язык", "Russian", "RU"])
def test_a_russian_apply_gets_the_russian_letter(language):
    assert ready_letter(_letters(), language, None) == "Полное"


@pytest.mark.parametrize("language", ["English", "Español", "Украинский"])
def test_any_other_language_gets_the_english_letter(language):
    assert ready_letter(_letters(), language, None) == "Full one"


def test_a_full_letter_too_long_for_the_limit_gives_way_to_the_short_one():
    assert ready_letter(_letters(ru="Полное письмо"), "Русский", 6) == "Кратко"


def test_short_asks_for_the_short_letter_even_when_the_full_one_fits():
    assert ready_letter(_letters(), "English", None, short=True) == "Short"


def test_no_letter_fits_the_limit():
    assert ready_letter(_letters(), "Русский", 3) is None


def test_a_missing_letter_is_not_replaced_with_the_other_language():
    assert ready_letter(_letters(ru=None, ru_short=None), "Русский", None) is None


def test_a_profile_without_letters_has_none():
    assert ready_letter(None, "Русский", None) is None
