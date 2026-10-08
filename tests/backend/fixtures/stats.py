"""Обстановка для проверок сводки: отклик и ответ на него."""

import pytest

from backend.models import VacancyStatus
from backend.repository.stats_pipeline import get_stats_channels_pipeline
from tests.dbio import put
from tests.factories import status_history_row, vacancy_row


@pytest.fixture
def applied(session_factory):
    """Завести вакансию с отправленным откликом и, если просят, ответом на него.

    Связка эта у сводки несущая: срок ответа считается от перехода в
    «отправлено» до первого ответного перехода, а доля молчания — от числа
    откликов без такого перехода. Собранная руками, она занимала в каждой
    проверке по двадцать строк, и предмет проверки тонул в них.

    Срок ответа задаётся сдвигом от отправки, а не своим временем: сравнивают
    в сводке именно разницу, и записанная двумя независимыми временами она
    считается в уме на каждой проверке. Ответ — переход в статус `answer`;
    откуда пришёл ответ, сводке неважно.

    Всё, что связке не принадлежит, — второй отклик, лишний переход, письмо —
    тест дописывает сам к отданной вакансии; лишнее в полях вакансии задаётся
    именованными доводами, они уходят в `vacancy_row`.

    Сама вакансия заводится мигом отклика и в статусе отклика, а не остаётся
    новой на начале времён: `Vacancy.created_at` — это отбор периода у трёх
    запросов сводки, и вакансия из начала времён не попадала бы ни в одну
    прибавку. Тест, которому нужно иное, называет поле именованным доводом.
    """

    async def build(
        applied_at, *, answered_after=None, answer=VacancyStatus.ANSWERED, **overrides
    ):
        fields = {"status": VacancyStatus.APPLIED, "created_at": applied_at}
        fields.update(overrides)
        vacancy = vacancy_row(**fields)
        await put(session_factory, vacancy)
        rows = [
            status_history_row(
                vacancy.id, status=VacancyStatus.APPLIED, changed_at=applied_at
            )
        ]
        if answered_after is not None:
            rows.append(
                status_history_row(
                    vacancy.id, status=answer, changed_at=applied_at + answered_after
                )
            )
        await put(session_factory, *rows)
        return vacancy

    return build


async def rows_by_channel(session, **kwargs) -> dict[int | None, dict]:
    """Строки таблицы, разложенные по номеру канала; без канала — под `None`."""
    got = await get_stats_channels_pipeline(session, **kwargs)
    return {row["id"]: row for row in got["channels"]}
