"""Цикл откликателя: по каждой вакансии первый доступный способ, пока один не удастся."""

import time

import pytest

from backend.applying import run
from backend.applying.result import Dropped, Missed, TelegramClosed, Unfit
from backend.models import Vacancy, VacancyStatus
from tests.backend.fixtures.applying import MAIL


@pytest.fixture
def executors(monkeypatch):
    """Исполнители-подделки: ответ по способу, журнал вызовов."""
    calls, answers = [], {}

    def fake(method):
        async def execute(kit, vacancy_id, way):
            calls.append((vacancy_id, way.method))
            return answers.get((vacancy_id, method), "applied")
        return execute

    monkeypatch.setattr(run, "EXECUTORS", {m: fake(m) for m in
                        ("telegram", "aggregator", "form", "email")})
    return calls, answers


async def test_each_vacancy_gets_its_first_way(executors, two_vacancies, kit):
    calls, _ = executors
    await run.apply_vacancies(kit, [v.id for v in two_vacancies])
    assert [m for _, m in calls] == ["telegram", "telegram"]


async def test_a_missed_way_hands_over_to_the_next(executors, two_vacancies, kit):
    calls, answers = executors
    first = two_vacancies[0].id
    answers[(first, "telegram")] = Missed("нет адресата")
    await run.apply_vacancies(kit, [first])
    assert calls == [(first, "telegram"), (first, "email")]


async def test_a_vacancy_taken_out_of_new_during_the_run_gets_no_application(
        executors, two_vacancies, kit, session_factory, monkeypatch):
    """Прогон длинный, а человек тем временем правит статусы: убранная им из New
    вакансия отклика не получает, хотя в списке прогона она была."""
    calls, _ = executors
    first, second = (v.id for v in two_vacancies)
    applied = run.EXECUTORS["telegram"]

    async def declining_the_next(kit, vacancy_id, way):
        async with session_factory() as session:
            (await session.get(Vacancy, second)).status = VacancyStatus.DECLINE
            await session.commit()
        return await applied(kit, vacancy_id, way)

    monkeypatch.setitem(run.EXECUTORS, "telegram", declining_the_next)
    await run.apply_vacancies(kit, [first, second])
    assert calls == [(first, "telegram")]


async def test_an_unfit_vacancy_tries_no_other_way(executors, two_vacancies, kit):
    """Не подходит сама вакансия, а не способ: следующему способу пробовать нечего."""
    calls, answers = executors
    first = two_vacancies[0].id
    answers[(first, "telegram")] = Unfit("Условие формы")
    await run.apply_vacancies(kit, [first])
    assert calls == [(first, "telegram")]


async def test_a_vacancy_the_person_finished_tries_no_other_way(executors, two_vacancies, kit):
    """«Закончить» — про вакансию, а не про способ: следующий способ не пробуется."""
    calls, answers = executors
    first = two_vacancies[0].id
    answers[(first, "telegram")] = Dropped()
    await run.apply_vacancies(kit, [first])
    assert calls == [(first, "telegram")]


async def test_a_telegram_ban_closes_telegram_for_the_rest_of_the_run(
        executors, two_vacancies, kit):
    calls, answers = executors
    first, second = (v.id for v in two_vacancies)
    answers[(first, "telegram")] = Missed("FloodWait", TelegramClosed(until=time.time() + 600))
    await run.apply_vacancies(kit, [first, second])
    assert calls == [(first, "telegram"), (first, "email"), (second, "email")]


async def test_a_crashed_way_hands_over_to_the_next(executors, two_vacancies, kit, monkeypatch):
    """Сбой приложения в одном способе — промах этого способа, а не конец прогона."""
    calls, _ = executors
    first, second = (v.id for v in two_vacancies)

    async def crash(kit, vacancy_id, way):
        calls.append((vacancy_id, way.method))
        raise RuntimeError("сбой")

    monkeypatch.setitem(run.EXECUTORS, "telegram", crash)
    await run.apply_vacancies(kit, [first, second])
    assert calls == [(first, "telegram"), (first, "email"), (second, "telegram"), (second, "email")]


async def test_the_window_hears_each_vacancy_and_its_place_counted_from_zero(
        executors, two_vacancies, kit, monkeypatch):
    """Окно само называет место в очереди с единицы — ход уходит с нуля, как у каналов."""
    steps = []
    monkeypatch.setattr(kit.pipeline, "emit_progress",
                        lambda stage, label, current, total: steps.append((stage, label, current, total)))
    await run.apply_vacancies(kit, [v.id for v in two_vacancies])
    assert steps == [("apply", "Вакансия 1", 0, 2), ("apply", "Вакансия 2", 1, 2)]


async def test_a_chosen_way_is_tried_alone(executors, two_vacancies, kit):
    calls, answers = executors
    first = two_vacancies[0].id
    answers[(first, "email")] = Missed("сервер не принял")
    outcome = await run.apply_chosen(kit, first, MAIL)
    assert isinstance(outcome, Missed) and calls == [(first, "email")]
