"""Следствия, которые наблюдают тесты `backend/domain/transitions.py`.

Граф проверяется через `should_apply_status` — через ворота, которыми им
пользуются, а не чтением словаря переходов. Словарь — объявление; ворота —
следствие.
"""

import pytest

from backend.domain.transitions import (
    GHOSTING_ELIGIBLE_FROM,
    is_terminal_for_auto,
    should_apply_status,
)
from backend.models import VacancyStatus

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


@pytest.mark.parametrize("status", list(VacancyStatus))
def test_every_status_is_known_to_the_gate(status):
    """Ворота знают каждый статус перечисления.

    Новый статус без ключа в графе роняет `is_terminal_for_auto` с
    `KeyError` в бою; рукописные списки `TERMINAL` и `LIVE` такого не
    заметят — новый статус просто не попадёт ни в один прогон.
    """
    is_terminal_for_auto(status)
    ways_out(status)


def test_terminal_and_live_lists_cover_every_status():
    """Рукописные списки TERMINAL и LIVE вместе называют весь VacancyStatus.

    Статус, добавленный и в перечисление, и в граф, но забытый в обоих
    рукописных списках, молча остался бы без параметризованной проверки —
    KeyError его бы не поймал.
    """
    assert set(TERMINAL) | set(LIVE) == set(VacancyStatus)


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


@pytest.mark.parametrize(
    "initial",
    [VacancyStatus.NEW, VacancyStatus.SCAM, VacancyStatus.NOT_FIT],
)
def test_nothing_moves_a_vacancy_into_an_initial_status(initial):
    """Ни один автопереход не ведёт в начальный статус (New/Scam/Not Fit)."""
    assert not [
        status for status in VacancyStatus
        if should_apply_status(status, initial)
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


@pytest.mark.parametrize("status", list(VacancyStatus))
def test_ghosting_eligibility_agrees_with_the_gate(status):
    """Список кандидатов на Ghosting по таймеру совпадает с тем, что пропускают ворота.

    `GHOSTING_ELIGIBLE_FROM` объявлен отдельно от графа переходов как защита
    от расхождения (см. докстринг в `backend/domain/transitions.py`). Здесь
    сверяются два независимых источника, а не читается содержимое одного.
    """
    eligible = status in GHOSTING_ELIGIBLE_FROM
    gate_allows = should_apply_status(status, VacancyStatus.GHOSTING)
    assert eligible == gate_allows
