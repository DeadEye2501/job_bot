"""Чьё резюме идёт к отклику: язык важнее формы, а нет нужного — другое."""

from backend.domain.resume_choice import reply_slot


def test_an_english_reply_takes_the_english_resume():
    assert reply_slot("English", main=True, english=True) == "english"
    assert reply_slot("Deutsch", main=True, english=True) == "english"


def test_a_reply_in_the_app_language_takes_the_main_resume():
    assert reply_slot("Русский", main=True, english=True) == "main"


def test_without_the_wanted_resume_the_other_goes():
    assert reply_slot("English", main=True, english=False) == "main"
    assert reply_slot("Русский", main=False, english=True) == "english"


def test_without_both_nothing_goes():
    assert reply_slot("English", main=False, english=False) is None
