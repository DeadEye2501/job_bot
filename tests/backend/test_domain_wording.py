"""Написание стоит в тексте словом, а не куском чужого слова."""

from backend.domain.wording import spelled_alone


def test_a_russian_word_is_found_in_its_declined_form():
    assert spelled_alone("ищу позицию сеньора", "сеньор")


def test_an_english_word_must_end_where_it_is_spelled():
    assert not spelled_alone("пишу middleware", "middle")


def test_a_short_word_does_not_take_the_tail_of_a_hyphenated_one():
    assert not spelled_alone("upper-intermediate", "intermediate")


def test_a_hyphen_and_a_space_between_words_are_one_spelling():
    assert spelled_alone("upper intermediate", "upper-intermediate")
