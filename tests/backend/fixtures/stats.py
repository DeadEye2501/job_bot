"""Обстановка для проверок сводки: отклик и ответ на него."""

import pytest

from backend.models import VacancyStatus
from tests.dbio import put
from tests.factories import message_row, status_history_row, vacancy_row


@pytest.fixture
def applied(session_factory):
    """Завести вакансию с отправленным откликом и, если просят, ответом HR.

    Связка эта у сводки несущая: срок ответа считается от перехода в
    «отправлено» до первого входящего, а доля молчания — от числа откликов
    без такого входящего. Собранная руками, она занимала в каждой проверке по
    двадцать строк, и предмет проверки тонул в них.

    Срок ответа задаётся сдвигом от отправки, а не своим временем: сравнивают
    в сводке именно разницу, и записанная двумя независимыми временами она
    считается в уме на каждой проверке.

    Всё, что связке не принадлежит, — своё письмо, удалённое, второй отклик по
    той же вакансии, — тест дописывает сам к отданной вакансии; лишнее в полях
    вакансии задаётся именованными доводами, они уходят в `vacancy_row`.

    Ответ без HR не ставится: письмо приходит от кого-то, и вакансия без
    человека отвечающего не имеет. Отклик без ответа — имеет: отправляют его
    мы, и в сводке он считается молчанием.
    """

    async def build(applied_at, *, hr=None, answered_after=None, **overrides):
        vacancy = vacancy_row(hr_id=hr.id if hr else None, **overrides)
        await put(session_factory, vacancy)
        rows = [
            status_history_row(
                vacancy.id, status=VacancyStatus.APPLIED, changed_at=applied_at
            )
        ]
        if answered_after is not None:
            rows.append(
                message_row(
                    hr_id=hr.id,
                    vacancy_id=vacancy.id,
                    is_incoming=True,
                    sent_at=applied_at + answered_after,
                )
            )
        await put(session_factory, *rows)
        return vacancy

    return build
