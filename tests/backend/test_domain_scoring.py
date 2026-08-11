"""Следствия, которые наблюдают тесты `backend/domain/scoring.py`.

Закрытый `_build_skill_level_lookup` проверяется через публичный
`score_parsed`: снаружи он виден только начисленными баллами.
"""

from backend.domain.scoring import build_skill_lookup, score_parsed
from tests.factories import parsed_vacancy, profile_skill


def test_a_skill_name_is_found_regardless_of_case():
    """Имя навыка попадает в набор приведённым к нижнему регистру."""
    assert "python" in build_skill_lookup([profile_skill("Python", 3)])


def test_a_stray_space_around_the_name_does_not_cost_points():
    """Пробел по краям имени навыка на счёт не влияет.

    Пробел в анкете — опечатка ввода, а не другой навык. Экран
    статистики его уже отбрасывал, и без того же правила здесь один и тот
    же навык считался своим в статистике и чужим в баллах: вакансия
    получала минус за незнакомое требование вместо плюса за уровень.
    """
    score = score_parsed(
        parsed_vacancy(stack_required=["Python"]),
        [profile_skill("  Python  ", 3)],
    )

    assert score == 3


def test_a_whitespace_only_skill_matches_nothing():
    """Навык из одних пробелов не делает знакомой любую пустую строку.

    Он свёлся бы к пустому ключу, и такой ключ нашёлся бы для всякой
    пробельной строки в стеке вакансии: вместо штрафа за незнакомое
    требование вакансия получала бы плюс за уровень.
    """
    score = score_parsed(
        parsed_vacancy(stack_required=["   "]), [profile_skill("   ", 3)]
    )

    assert score == -1


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


def test_of_two_names_sharing_a_key_the_first_one_scores():
    """Из двух навыков с одним ключом баллы даёт заведённый первым.

    «CI/CD» и «ci cd» сводятся к одному ключу, и порядок выдачи базы ничем
    не задан. Побеждай последний — балл вакансии зависел бы от того, в каком
    порядке база вернула строки анкеты. Разбор резюме и правка мест работы
    уже разрешают это столкновение в пользу первого, и правило должно быть
    одно: иначе один и тот же навык весит на экране статистики иначе, чем в
    оценке вакансии.
    """
    got = score_parsed(
        parsed_vacancy(stack_required=["ci cd"]),
        [profile_skill("CI/CD", 3), profile_skill("ci cd", 1)],
    )
    assert got == 3


def test_a_separator_inside_a_name_does_not_cost_points():
    """Разделитель внутри названия — не другой навык.

    «Docker-Compose» в анкете и «docker compose» в стеке вакансии — одно и
    то же, и так их уже читал разбор резюме. Пока баллы считались по своему,
    более строгому правилу, такой навык отнимал балл как незнакомый — и
    вакансия могла не пройти порог из-за написания через дефис.
    """
    got = score_parsed(
        parsed_vacancy(stack_required=["docker compose"]),
        [profile_skill("Docker-Compose", 3)],
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
