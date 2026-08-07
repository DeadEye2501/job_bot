"""Следствия, которые наблюдают тесты графа статусов `backend/domain.py`.

Граф проверяется через `should_apply_status` — через ворота, которыми им
пользуются, а не чтением словаря переходов. Словарь — объявление; ворота —
следствие.
"""

import pytest

from backend.domain import (
    decide_vacancy_status,
    is_terminal_for_auto,
    should_apply_status,
)
from backend.models import VacancyStatus
from tests.factories import parsed_vacancy

TERMINAL = [
    VacancyStatus.OFFER,
    VacancyStatus.DECLINE,
    VacancyStatus.SCAM,
    VacancyStatus.NOT_FIT,
]

LIVE = [
    VacancyStatus.NEW,
    VacancyStatus.APPLIED,
    VacancyStatus.ANSWERED,
    VacancyStatus.INVITATION,
    VacancyStatus.TEST,
    VacancyStatus.IN_PROGRESS,
    VacancyStatus.GHOSTING,
]


def ways_out(status: VacancyStatus) -> list[VacancyStatus]:
    """Куда ворота пропускают из этого статуса."""
    return [other for other in VacancyStatus if should_apply_status(status, other)]


@pytest.mark.parametrize("status", TERMINAL)
def test_no_automatic_transition_leaves_a_terminal_status(status):
    """Из терминального статуса ворота не пропускают ни одного перехода."""
    assert is_terminal_for_auto(status)
    assert ways_out(status) == []


@pytest.mark.parametrize("status", LIVE)
def test_a_live_status_has_at_least_one_way_out(status):
    """Из живого статуса ворота пропускают хотя бы один переход."""
    assert not is_terminal_for_auto(status)
    assert ways_out(status)


def test_the_same_status_is_never_reapplied():
    """Переход в тот же самый статус ворота не пропускают."""
    assert not should_apply_status(VacancyStatus.APPLIED, VacancyStatus.APPLIED)


def test_a_fresh_vacancy_can_only_become_applied():
    """Из New автоматически ведёт единственная дорога — в Applied."""
    assert ways_out(VacancyStatus.NEW) == [VacancyStatus.APPLIED]


def test_nothing_moves_a_vacancy_back_to_new():
    """Обратно в New не ведёт ни один автопереход."""
    assert not [
        status for status in VacancyStatus
        if should_apply_status(status, VacancyStatus.NEW)
    ]


def test_a_second_invitation_is_refused_right_after_the_first():
    """Пока мяч у соискателя, повторное приглашение или тест не назначаются."""
    assert not should_apply_status(
        VacancyStatus.INVITATION, VacancyStatus.INVITATION
    )
    assert not should_apply_status(VacancyStatus.INVITATION, VacancyStatus.TEST)


def test_an_invitation_becomes_possible_again_from_in_progress():
    """А после возврата мяча к HR — снова назначаются."""
    assert should_apply_status(VacancyStatus.IN_PROGRESS, VacancyStatus.INVITATION)
    assert should_apply_status(VacancyStatus.IN_PROGRESS, VacancyStatus.TEST)


@pytest.mark.parametrize(
    "revived",
    [
        VacancyStatus.ANSWERED,
        VacancyStatus.INVITATION,
        VacancyStatus.TEST,
        VacancyStatus.OFFER,
        VacancyStatus.DECLINE,
    ],
)
def test_ghosting_releases_a_vacancy_when_the_hr_finally_answers(revived):
    """Молчание HR не окончательно: ответ выводит вакансию из Ghosting."""
    assert should_apply_status(VacancyStatus.GHOSTING, revived)


def test_the_send_button_revives_a_rejected_vacancy():
    """Кнопка «Отправить отклик» проводит Not Fit в Applied поверх графа."""
    assert not should_apply_status(VacancyStatus.NOT_FIT, VacancyStatus.APPLIED)
    assert should_apply_status(
        VacancyStatus.NOT_FIT, VacancyStatus.APPLIED, force=True
    )


@pytest.mark.parametrize(
    "current",
    [
        VacancyStatus.DECLINE,
        VacancyStatus.OFFER,
        VacancyStatus.GHOSTING,
        VacancyStatus.IN_PROGRESS,
    ],
)
def test_the_send_button_does_not_overwrite_an_outcome_already_reached(current):
    """Случайный клик «Отправить» не затирает уже случившийся исход."""
    assert not should_apply_status(current, VacancyStatus.APPLIED, force=True)


def test_the_send_button_opens_nothing_but_applied():
    """Признак force открывает дорогу только в Applied и никуда больше."""
    assert not should_apply_status(
        VacancyStatus.NEW, VacancyStatus.OFFER, force=True
    )


def test_an_unparseable_post_is_rejected_with_a_named_reason():
    """Пост, из которого ничего не извлеклось, уходит в Not Fit с причиной."""
    assert decide_vacancy_status(None, 10, None, threshold=0) == (
        VacancyStatus.NOT_FIT,
        "unparseable",
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
