"""Следствия, которые наблюдают тесты `backend/domain/verdict.py`."""

from backend.domain.verdict import (
    blacklist_refusal,
    decide_vacancy_status,
    is_empty_vacancy,
)
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


def test_a_phone_or_mail_is_a_contact_as_good_as_a_telegram_one():
    """Контакт вне Telegram — такой же признак вакансии: «требуются
    разнорабочие, тел. …» с описанием — вакансия, а не пустышка."""
    assert not is_empty_vacancy(
        parsed_vacancy(description="Разнорабочие на объект.", other_contacts=["+1 555 0100"])
    )


def test_a_preferred_only_stack_still_counts_as_a_signal():
    """Стек считается признаком, даже если он весь в желательной половине."""
    assert not is_empty_vacancy(
        parsed_vacancy(stack_preferred=["Python"], company_name="ООО Ромашка")
    )


def test_a_blacklisted_vacancy_is_rejected_and_names_the_pattern():
    """Отказ по чёрному списку называет сработавший образец.

    Человек читает причину в карточке и по ней правит список: без образца
    непонятно, какое из полусотни слов сработало.
    """
    assert blacklist_refusal("казино") == "blacklist: казино"


def test_an_untouched_vacancy_has_nothing_to_refuse():
    """Не задетое списком объявление отказа не получает."""
    assert blacklist_refusal(None) is None


def test_a_low_score_is_rejected_and_shows_both_numbers():
    """Отказ по баллам показывает и набранное, и порог."""
    assert decide_vacancy_status(2, threshold=5) == (
        VacancyStatus.NOT_FIT,
        "score 2 < 5",
    )


def test_a_vacancy_exactly_at_the_threshold_passes():
    """Порог включающий: ровно threshold баллов проходит."""
    assert decide_vacancy_status(5, threshold=5) == (VacancyStatus.NEW, None)
