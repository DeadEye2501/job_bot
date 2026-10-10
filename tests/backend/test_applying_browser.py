"""Браузерный способ: одна сессия агента на кнопку агрегатора или форму работодателя."""

import pytest

from backend.agent.sessions import LimitExhausted
from backend.applying.browser import via_browser
from backend.applying.result import Missed, SiteClosed
from backend.domain.apply_order import Way
from backend.models import VacancyEvent
from tests.backend.fixtures.applying import FORM, PAGE
from tests.dbio import all_rows, put
from tests.factories_aggregators import web_search_row
from tests.fakes.agent import LimitHit, finish_step, record_step


async def test_a_recorded_application_is_applied(board, kit_with):
    site, vacancy = await board()
    kit = await kit_with([record_step(PAGE, via="aggregator")])
    assert await via_browser(kit, vacancy.id, Way("aggregator", PAGE, site.id)) == "applied"


async def test_a_closed_platform_is_a_lesson(board, kit_with):
    site, vacancy = await board()
    kit = await kit_with([finish_step("platform_closed")])
    outcome = await via_browser(kit, vacancy.id, Way("aggregator", PAGE, site.id))
    assert outcome.lesson == SiteClosed(site.id)


async def test_a_closed_vacancy_is_missed_without_a_lesson(board, kit_with):
    site, vacancy = await board()
    kit = await kit_with([finish_step("vacancy_closed")])
    outcome = await via_browser(kit, vacancy.id, Way("aggregator", PAGE, site.id))
    assert outcome == Missed("вакансия закрыта на сайте")


async def test_a_session_without_an_outcome_is_missed(board, kit_with):
    _, vacancy = await board()

    async def silent(tools):
        return None

    kit = await kit_with([silent])
    assert await via_browser(kit, vacancy.id, Way("form", FORM, None)) == Missed("агент закончил без итога")


async def test_an_exhausted_subscription_stops_the_run_not_just_the_way(board, kit_with):
    """Следующий способ упёрся бы в тот же лимит."""
    site, vacancy = await board()

    async def limit(tools):
        raise LimitHit

    kit = await kit_with([limit])
    with pytest.raises(LimitExhausted):
        await via_browser(kit, vacancy.id, Way("aggregator", PAGE, site.id))


async def test_the_applier_is_told_how_to_call_a_person(board, kit_with):
    """Откликатель зовёт человека на капчу и слетевший вход — правило о том в его наставлении."""
    site, vacancy = await board()
    kit = await kit_with([record_step(PAGE, via="aggregator")])

    await via_browser(kit, vacancy.id, Way("aggregator", PAGE, site.id))

    (plan,) = kit.run_session.plans
    # Подстрока самого правила о зове человека: слово `need_human` называет и
    # промпт роли, и по нему пропажу правила не заметить.
    assert 'need_human с kind="captcha"' in plan.system_prompt


async def test_a_simulated_application_is_told_not_to_send_and_is_marked(board, kit_with, session_factory):
    """Последнюю кнопку формы код не знает: «не отправлять» агенту говорит задание,
    а отклик записывается с пометкой симуляции."""
    site, vacancy = await board()
    kit = await kit_with([record_step(PAGE, via="aggregator")], send_locked=True)

    await via_browser(kit, vacancy.id, Way("aggregator", PAGE, site.id))

    (plan,) = kit.run_session.plans
    assert "Режим симуляции" in plan.task and kit.browser.sending is False
    (event,) = [e for e in await all_rows(session_factory, VacancyEvent) if e.kind == "applied"]
    assert event.payload["simulated"] is True


async def test_a_real_application_opens_the_browser_able_to_send(board, kit_with):
    site, vacancy = await board()
    kit = await kit_with([record_step(PAGE, via="aggregator")])

    await via_browser(kit, vacancy.id, Way("aggregator", PAGE, site.id))

    assert kit.browser.sending is True and ("profile", site.id) in kit.browser.calls


async def test_a_form_opens_in_the_web_search_profile(board, kit_with, session_factory):
    """У формы работодателя своего агрегатора нет: её открывает профиль «Поиска по сети»."""
    _, vacancy = await board()
    web = web_search_row()
    await put(session_factory, web)
    kit = await kit_with([record_step(FORM)])

    await via_browser(kit, vacancy.id, Way("form", FORM, None))

    assert ("profile", web.id) in kit.browser.calls
