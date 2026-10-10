"""Ручной отклик одним зовом: выбранный способ через того же откликателя, в месте прогона."""

import asyncio

from backend.bot.apply import apply_chosen_way
from backend.domain.apply_order import Way
from backend.models import BotMode, Vacancy, VacancyStatus
from tests.backend.fixtures.bot import switch_to
from tests.dbio import only_row

TG = Way("telegram", "@hr_name", None)


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
    way = Way("email", "hr@company.test", None)
    assert await apply_chosen_way(bot, vacancy.id, way) == "failed"


async def test_a_missing_vacancy_is_missing(manual_case):
    bot, _ = await manual_case()
    assert await apply_chosen_way(bot, 999, TG) == "missing"
