"""Следствия, которые наблюдают тесты `backend/domain/scoring.py`.

Закрытый `_build_skill_level_lookup` проверяется через публичный
`score_stack`: снаружи он виден только начисленными баллами.
"""

from backend.domain.scoring import build_skill_lookup, score_stack
from tests.factories import profile_skill


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
    score = score_stack(["Python"], [], [profile_skill("  Python  ", 3)])

    assert score == 3


def test_a_whitespace_only_skill_matches_nothing():
    """Навык из одних пробелов не делает знакомой любую пустую строку.

    Он свёлся бы к пустому ключу, и такой ключ нашёлся бы для всякой
    пробельной строки в стеке вакансии: вместо штрафа за незнакомое
    требование вакансия получала бы плюс за уровень.
    """
    score = score_stack(["   "], [], [profile_skill("   ", 3)])

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
    assert score_stack(["Python"], [], []) == 0


def test_a_required_skill_the_profile_has_adds_its_level():
    """Обязательный навык, который есть, добавляет свой уровень."""
    got = score_stack(["Python"], [], [profile_skill("Python", 3)])
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
    got = score_stack(["ci cd"], [], [profile_skill("CI/CD", 3), profile_skill("ci cd", 1)])
    assert got == 3


def test_a_separator_inside_a_name_does_not_cost_points():
    """Разделитель внутри названия — не другой навык.

    «Docker-Compose» в анкете и «docker compose» в стеке вакансии — одно и
    то же, и так их уже читал разбор резюме. Пока баллы считались по своему,
    более строгому правилу, такой навык отнимал балл как незнакомый — и
    вакансия могла не пройти порог из-за написания через дефис.
    """
    got = score_stack(["docker compose"], [], [profile_skill("Docker-Compose", 3)])
    assert got == 3


def test_a_required_skill_the_profile_lacks_costs_a_point():
    """Обязательный навык, которого нет, отнимает балл."""
    got = score_stack(["Rust"], [], [profile_skill("Python", 3)])
    assert got == -1


def test_a_preferred_skill_the_profile_has_adds_one_less():
    """Желательный навык стоит на балл меньше обязательного."""
    got = score_stack([], ["Python"], [profile_skill("Python", 3)])
    assert got == 2


def test_a_preferred_skill_at_the_lowest_level_adds_nothing():
    """Желательный навык первого уровня не поднимает вакансию над остальными."""
    got = score_stack([], ["Bash"], [profile_skill("Bash", 1)])
    assert got == 0


def test_a_preferred_skill_the_profile_lacks_costs_nothing():
    """Отсутствие желательного навыка ничем не наказывается."""
    got = score_stack([], ["Rust"], [profile_skill("Python", 3)])
    assert got == 0


def test_an_alias_scores_exactly_like_the_name():
    """Псевдоним — другое написание того же навыка, и стоит столько же."""
    skills = [profile_skill("PostgreSQL", 4, aliases=["Postgres"])]
    assert score_stack(["postgres"], [], skills) == 4


def test_blank_and_non_string_stack_items_are_skipped():
    """Мусор в стеке не участвует в подсчёте и не роняет его."""
    got = score_stack(["", None, "Python"], [], [profile_skill("Python", 2)])
    assert got == 2


def test_one_profile_skill_named_twice_is_paid_for_once():
    """Два написания одного навыка анкеты дают его уровень один раз.

    Объявление называет инструменты порознь — «Photoshop, Illustrator», — и
    в стеке они остаются порознь: карточка обязана показать, что требуют
    именно их. А в анкете это один навык одного уровня, и заплатить за него
    дважды значило бы поднять вакансию с одним знакомым умением над той, где
    их правда два.
    """
    skills = [profile_skill("Adobe Suite", 3, aliases=["Photoshop", "Illustrator"])]
    assert score_stack(["Photoshop", "Illustrator"], [], skills) == 3


def test_the_stronger_half_pays_for_a_skill_named_in_both():
    """Навык, названный в обеих половинах, весит по обязательной.

    Половина решает не порядок упоминания, а строгость: требование весит
    полным уровнем, «будет плюсом» — на балл меньше. Возьми верх желательная,
    и вакансия, где навык прямо требуют, оценивалась бы ниже той, где его
    называют пожеланием.
    """
    skills = [profile_skill("Adobe Suite", 3, aliases=["Photoshop", "Illustrator"])]
    assert score_stack(["Illustrator"], ["Photoshop"], skills) == 3


def test_two_unknown_names_each_cost_their_own_point():
    """Незнакомые анкете названия остаются каждый сам по себе.

    Свести их не по чему: общего навыка, за который они оба сошли бы, в
    анкете нет вовсе, и вакансия, требующая двух незнакомых технологий,
    должна стоять ниже требующей одной.
    """
    got = score_stack(["Rust", "Go"], [], [profile_skill("Python", 3)])
    assert got == -2


def test_required_and_preferred_add_up_together():
    """Обе половины стека складываются в один итог."""
    skills = [profile_skill("Python", 3), profile_skill("Docker", 2)]
    got = score_stack(["Python", "Rust"], ["Docker"], skills)
    assert got == 3
