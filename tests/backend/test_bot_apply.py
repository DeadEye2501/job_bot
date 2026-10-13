"""Ручной отклик одним зовом: выбранный способ через того же откликателя, в месте прогона."""

import asyncio

from backend.applying import run
from backend.applying.result import Unfit
from backend.bot.apply import apply_all_new, apply_chosen_way
from backend.models import BotMode, Vacancy, VacancyStatus
from tests.backend.fixtures.applying import MAIL, TG, telegram_vacancy
from tests.backend.fixtures.bot import switch_to
from tests.dbio import all_rows, only_row



async def test_a_manual_telegram_application_goes_through_the_same_applier(manual_case):
    bot, vacancy = await manual_case(status=VacancyStatus.DECLINE)
    assert await apply_chosen_way(bot, vacancy.id, TG) == "ok"
    assert (await only_row(bot.session_factory, Vacancy)).status is VacancyStatus.APPLIED


async def test_a_manual_application_reads_the_profile_before_the_letter(manual_case):
    """До первого оборота анкета в памяти конвейера пуста — письмо без неё не сочинить."""
    bot, vacancy = await manual_case()
    bot.ingestion.profile_block = ""

    async def reload_resources():
        bot.ingestion.profile_block = "Иван Петров, Python-разработчик"

    bot.ingestion.reload_resources = reload_resources
    assert await apply_chosen_way(bot, vacancy.id, TG) == "ok"


async def test_a_manual_application_finished_in_the_window_has_its_own_word(manual_case):
    """Человек закончил, а не провалился: ручной отклик отвечает своим словом."""
    bot, vacancy = await manual_case()
    await bot.rs.set_app("auto_apply", "confirm")
    bot.on_human_needed = lambda kind, host, payload: bot.human_done({"drop": True})

    assert await apply_chosen_way(bot, vacancy.id, TG) == "dropped"
    assert (await only_row(bot.session_factory, Vacancy)).status is VacancyStatus.NEW


async def test_applying_to_all_new_waits_for_confirmation_too(manual_case):
    bot, vacancy = await manual_case()
    await bot.rs.set_app("auto_apply", "confirm")
    asked = []

    def answer(kind, host, payload):
        asked.append(payload)
        bot.human_done({"items": payload["items"]})

    bot.on_human_needed = answer

    assert await apply_all_new(bot) == "ok"
    assert len(asked) == 1
    assert (await only_row(bot.session_factory, Vacancy)).status is VacancyStatus.APPLIED


async def test_a_manual_application_is_not_held_by_off(manual_case, session_factory):
    """Режим — про автоматику: нажатое человеком работает и в Off."""
    bot, vacancy = await manual_case()
    await switch_to(session_factory, BotMode.OFF)
    assert await apply_chosen_way(bot, vacancy.id, TG) == "ok"


async def test_a_second_click_waits_for_the_slot(manual_case):
    bot, vacancy = await manual_case(hang=True)
    first = asyncio.create_task(apply_chosen_way(bot, vacancy.id, TG))
    await bot.hanging.wait()
    assert await apply_chosen_way(bot, vacancy.id, TG) == "busy"
    bot.cancel_current_poll()
    assert await first == "cancelled"


async def test_a_way_that_did_not_work_is_a_failure(manual_case):
    bot, vacancy = await manual_case()
    assert await apply_chosen_way(bot, vacancy.id, MAIL) == "failed"


async def test_a_way_that_found_the_vacancy_unfit_says_so(manual_case, monkeypatch):
    """Окну это не провал способа: вакансия ушла в Not Fit, и сказать надо об этом."""
    bot, vacancy = await manual_case()

    async def unfit(kit, vacancy_id, way):
        return Unfit("Условие формы")

    monkeypatch.setitem(run.EXECUTORS, "email", unfit)
    assert await apply_chosen_way(bot, vacancy.id, MAIL) == "unfit"


async def test_apply_all_new_goes_through_every_new_vacancy(manual_case, session_factory):
    """Отказ откликом перевёлся бы в Applied — он остаётся отказом, значит его не трогали."""
    bot, first = await manual_case()
    second = await telegram_vacancy(session_factory)
    declined = await telegram_vacancy(session_factory, status=VacancyStatus.DECLINE)

    assert await apply_all_new(bot) == "ok"

    statuses = {v.id: v.status for v in await all_rows(session_factory, Vacancy)}
    assert statuses == {first.id: VacancyStatus.APPLIED, second.id: VacancyStatus.APPLIED,
                        declined.id: VacancyStatus.DECLINE}


async def test_apply_all_new_is_not_held_by_off(manual_case, session_factory):
    """Режим — про автоматику: нажатое человеком работает и в Off."""
    bot, vacancy = await manual_case()
    await switch_to(session_factory, BotMode.OFF)

    assert await apply_all_new(bot) == "ok"
    assert (await only_row(bot.session_factory, Vacancy)).status is VacancyStatus.APPLIED


async def test_apply_all_new_waits_for_the_slot_and_stops_on_cancel(manual_case):
    bot, _ = await manual_case(hang=True)
    first = asyncio.create_task(apply_all_new(bot))
    await bot.hanging.wait()
    assert await apply_all_new(bot) == "busy"
    bot.cancel_current_poll()
    assert await first == "cancelled"


async def test_a_missing_vacancy_is_missing(manual_case):
    bot, _ = await manual_case()
    assert await apply_chosen_way(bot, 999, TG) == "missing"
