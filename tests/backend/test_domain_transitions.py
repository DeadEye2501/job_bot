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

# Живое — всё, что не названо терминальным. Выписанный руками второй список
# пришлось бы сверять с перечислением отдельной проверкой, а такая проверка
# стережёт свои же фикстуры: статус, забытый в обоих списках, молча не попал
# бы ни в один прогон. Здесь он попадает в живые сам, и если он на деле
# терминальный — краснеет проверка выходов, а не молчит перечень.
LIVE = [status for status in VacancyStatus if status not in TERMINAL]


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


@pytest.mark.parametrize("status", list(VacancyStatus))
def test_the_same_status_is_never_reapplied(status):
    """Переход в тот же самый статус ворота не пропускают — ни из одного.

    Отдельной охраны у этого запрета нет: его держит сам граф тем, что в
    нём нет петель. Значит и щупать надо каждый статус — петля, заведённая
    у любого из них, иначе прошла бы весь набор незамеченной.
    """
    assert not should_apply_status(status, status)


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
    [VacancyStatus.NEW, VacancyStatus.SCAM, VacancyStatus.GHOSTING],
)
def test_the_send_button_applies_where_no_application_counts(current):
    """Там, где отклика нет или он ничего не дал, ушедшее письмо и есть отклик."""
    assert should_apply_status(current, VacancyStatus.APPLIED, force=True)


@pytest.mark.parametrize(
    "current",
    [
        VacancyStatus.ANSWERED,
        VacancyStatus.INVITATION,
        VacancyStatus.TEST,
        VacancyStatus.IN_PROGRESS,
        VacancyStatus.OFFER,
        VacancyStatus.DECLINE,
    ],
)
def test_the_send_button_never_rolls_a_vacancy_back_to_applied(current):
    """С вакансии, ушедшей по воронке дальше, кнопка в «отклик» не откатывает.

    Человек жмёт отправку, а не меняет статус: письмо там — очередная реплика
    переписки, а не отклик.
    """
    assert not should_apply_status(current, VacancyStatus.APPLIED, force=True)


def test_a_second_send_adds_no_second_applied():
    """Второе письмо по уже откликнутой вакансии записи не заводит.

    Статус уже говорит то же самое, что сказала бы новая строка, а петель в
    графе нет.
    """
    assert not should_apply_status(
        VacancyStatus.APPLIED, VacancyStatus.APPLIED, force=True
    )


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
