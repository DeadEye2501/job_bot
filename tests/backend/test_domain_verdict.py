"""Следствия, которые наблюдают тесты `backend/domain/verdict.py`."""

from backend.domain.verdict import decide_vacancy_status, is_empty_vacancy
from backend.models import VacancyStatus
from tests.factories import parsed_vacancy


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


def test_a_blacklisted_vacancy_is_rejected_and_names_the_pattern():
    """Отказ по чёрному списку называет сработавший образец."""
    assert decide_vacancy_status(parsed_vacancy(), 10, "казино", threshold=0) == (
        VacancyStatus.NOT_FIT,
        "blacklist: казино",
    )


def test_a_low_score_is_rejected_and_shows_both_numbers():
    """Отказ по баллам показывает и набранное, и порог."""
    assert decide_vacancy_status(parsed_vacancy(), 2, None, threshold=5) == (
        VacancyStatus.NOT_FIT,
        "score 2 < 5",
    )


def test_a_vacancy_exactly_at_the_threshold_passes():
    """Порог включающий: ровно threshold баллов проходит."""
    assert decide_vacancy_status(parsed_vacancy(), 5, None, threshold=5) == (
        VacancyStatus.NEW,
        None,
    )


def test_the_blacklist_outranks_a_passing_score():
    """Чёрный список сильнее набранных баллов, сколько бы их ни было."""
    assert decide_vacancy_status(parsed_vacancy(), 100, "казино", threshold=5) == (
        VacancyStatus.NOT_FIT,
        "blacklist: казино",
    )
