"""Следствия, которые наблюдают тесты `backend/domain/blacklist.py`.

Закрытые `_word_match`, `_compile_word_pattern` и `_is_word_char` проверяются
через публичный `check_blacklist`: снаружи они видны только сработавшим
образцом.
"""

from backend.domain.blacklist import check_blacklist


def test_an_empty_text_matches_no_pattern():
    """В пустом тексте чёрный список ничего не находит."""
    assert check_blacklist("", ["казино"]) is None


def test_the_matched_pattern_comes_back_as_written():
    """Возвращается сам образец, а не найденный кусок текста."""
    assert check_blacklist("Ищем в казино", ["ставки", "казино"]) == "казино"


def test_the_match_ignores_case():
    """Регистр в тексте не мешает срабатыванию."""
    assert check_blacklist("КАЗИНО ищет", ["казино"]) == "казино"


def test_a_pattern_inside_a_longer_cyrillic_word_does_not_match():
    """Границы слова считаются и для кириллицы: «нода» не ловится в «нодаль»."""
    assert check_blacklist("нодаль", ["нода"]) is None


def test_a_pattern_starting_with_punctuation_keeps_its_boundaries():
    """«.NET» не ловится внутри «.netкафедра», но ловится отдельным словом."""
    assert check_blacklist(".netкафедра", [".NET"]) is None
    assert check_blacklist("нужен .net разработчик", [".NET"]) == ".NET"


def test_an_empty_pattern_is_skipped():
    """Пустой образец не считается совпадением с чем угодно."""
    assert check_blacklist("любой текст", ["", "казино"]) is None
