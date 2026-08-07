"""Следствия, которые наблюдают тесты подсчёта баллов `backend/domain.py`.

Закрытые `_build_skill_level_lookup`, `_word_match`, `_compile_word_pattern` и
`_is_word_char` проверяются через публичные `score_parsed` и `check_blacklist`:
снаружи они видны только начисленными баллами и сработавшим образцом.
"""

from backend.domain import (
    build_skill_lookup,
    check_blacklist,
    is_empty_vacancy,
    score_parsed,
)
from tests.factories import parsed_vacancy, profile_skill


def test_a_skill_name_is_found_regardless_of_case():
    """Имя навыка попадает в набор приведённым к нижнему регистру."""
    assert "python" in build_skill_lookup([profile_skill("Python", 3)])


def test_aliases_land_in_the_lookup_next_to_the_name():
    """Псевдонимы ищутся наравне с именем."""
    lookup = build_skill_lookup(
        [profile_skill("PostgreSQL", 3, aliases=["Postgres", "PG"])]
    )
    assert {"postgresql", "postgres", "pg"} <= lookup


def test_a_skill_without_a_name_adds_nothing():
    """Навык с пустым именем в набор не попадает."""
    assert build_skill_lookup([profile_skill("", 3)]) == set()


def test_a_non_string_alias_is_ignored():
    """Мусор в псевдонимах не ломает набор и в него не попадает."""
    lookup = build_skill_lookup(
        [profile_skill("Python", 3, aliases=["py", 42, None, ""])]
    )
    assert lookup == {"python", "py"}


def test_an_empty_profile_scores_nothing():
    """Без навыков в профиле подсчёт не начисляет и не отнимает."""
    assert score_parsed(parsed_vacancy(stack_required=["Python"]), []) == 0


def test_a_required_skill_the_profile_has_adds_its_level():
    """Обязательный навык, который есть, добавляет свой уровень."""
    got = score_parsed(
        parsed_vacancy(stack_required=["Python"]), [profile_skill("Python", 3)]
    )
    assert got == 3


def test_a_required_skill_the_profile_lacks_costs_a_point():
    """Обязательный навык, которого нет, отнимает балл."""
    got = score_parsed(
        parsed_vacancy(stack_required=["Rust"]), [profile_skill("Python", 3)]
    )
    assert got == -1


def test_a_preferred_skill_the_profile_has_adds_one_less():
    """Желательный навык стоит на балл меньше обязательного."""
    got = score_parsed(
        parsed_vacancy(stack_preferred=["Python"]), [profile_skill("Python", 3)]
    )
    assert got == 2


def test_a_preferred_skill_at_the_lowest_level_adds_nothing():
    """Желательный навык первого уровня не поднимает вакансию над остальными."""
    got = score_parsed(
        parsed_vacancy(stack_preferred=["Bash"]), [profile_skill("Bash", 1)]
    )
    assert got == 0


def test_a_preferred_skill_the_profile_lacks_costs_nothing():
    """Отсутствие желательного навыка ничем не наказывается."""
    got = score_parsed(
        parsed_vacancy(stack_preferred=["Rust"]), [profile_skill("Python", 3)]
    )
    assert got == 0


def test_an_alias_scores_exactly_like_the_name():
    """Псевдоним — другое написание того же навыка, и стоит столько же."""
    skills = [profile_skill("PostgreSQL", 4, aliases=["Postgres"])]
    assert score_parsed(parsed_vacancy(stack_required=["postgres"]), skills) == 4


def test_blank_and_non_string_stack_items_are_skipped():
    """Мусор в стеке не участвует в подсчёте и не роняет его."""
    got = score_parsed(
        parsed_vacancy(stack_required=["", None, "Python"]),
        [profile_skill("Python", 2)],
    )
    assert got == 2


def test_required_and_preferred_add_up_together():
    """Обе половины стека складываются в один итог."""
    skills = [profile_skill("Python", 3), profile_skill("Docker", 2)]
    got = score_parsed(
        parsed_vacancy(stack_required=["Python", "Rust"], stack_preferred=["Docker"]),
        skills,
    )
    assert got == 3


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


def test_a_missing_parse_counts_as_an_empty_vacancy():
    """Если разобрать не удалось вовсе — вакансия пустая."""
    assert is_empty_vacancy(None)


def test_a_title_alone_is_not_a_vacancy():
    """Один заголовок без единого признака — мусор."""
    assert is_empty_vacancy(parsed_vacancy())


def test_a_single_signal_is_still_not_enough():
    """Одного признака мало."""
    assert is_empty_vacancy(parsed_vacancy(hr_contact="@anna_hr"))


def test_two_signals_make_a_real_vacancy():
    """Короткий, но настоящий пост: контакт и зарплата — уже вакансия."""
    assert not is_empty_vacancy(
        parsed_vacancy(hr_contact="@anna_hr", salary="150 000")
    )


def test_a_preferred_only_stack_still_counts_as_a_signal():
    """Стек считается признаком, даже если он весь в желательной половине."""
    assert not is_empty_vacancy(
        parsed_vacancy(stack_preferred=["Python"], company_name="ООО Ромашка")
    )
