"""Браузерный способ: одна сессия агента на кнопку агрегатора или форму работодателя."""

import pytest

from backend.agent.stops import LimitExhausted, ResumeMissing
from backend.applying.browser import via_browser
from backend.applying.result import Dropped, Missed, SiteClosed, Unfit
from backend.domain.apply_order import Way
from backend.models import (
    AggregatorResume, Vacancy, VacancyEvent, VacancyStatus, VacancyStatusHistory,
)
from tests.backend.fixtures.applying import FORM, PAGE
from tests.dbio import all_rows, only_row, put
from tests.factories_aggregators import aggregator_resume_row, web_search_row
from tests.fakes.agent import (
    LimitHit,
    edited,
    finish_step,
    finished,
    page_item,
    record_step,
    under_confirmation,
)


async def test_a_recorded_application_is_applied(board, kit_with):
    site, vacancy = await board()
    kit = await kit_with([record_step(PAGE, via="aggregator")])
    assert await via_browser(kit, vacancy.id, Way("aggregator", PAGE, site.id)) == "applied"


async def test_a_page_the_person_finished_drops_the_vacancy(board, kit_with, session_factory):
    """«Закончить» в окне — исход способа как есть: вакансия остаётся в New, что
    бы агент ни сказал после."""
    site, vacancy = await board()

    async def step(tools):
        await tools["need_human"](kind="confirm", items=[page_item("#name", "Иван")])
        await tools["finish"](result="not_fit", reason="передумал")

    kit, _ = await under_confirmation(await kit_with([step]), finished)

    assert await via_browser(kit, vacancy.id, Way("aggregator", PAGE, site.id)) == Dropped()
    assert (await only_row(session_factory, Vacancy)).status is VacancyStatus.NEW


async def _typing(kit_with, board, *, confirming):
    """Сессия агента: под подтверждением подтверждает имя «Иван», затем пробует
    вписать оба варианта."""
    site, vacancy = await board()
    answers = []

    async def step(tools):
        if confirming:
            await tools["need_human"](kind="confirm", items=[page_item("#name", "Иван")])
        answers.append(await tools["browser_type"](selector="#name", text="Иван"))
        answers.append(await tools["browser_type"](selector="#name", text="Иван Петров"))
        await tools["record_application"](via="aggregator", target=PAGE)

    return site, vacancy, await kit_with([step]), answers


async def test_under_confirmation_only_the_edited_text_reaches_the_page(board, kit_with):
    site, vacancy, kit, answers = await _typing(kit_with, board, confirming=True)
    kit, _ = await under_confirmation(kit, edited({"Имя": "Иван Петров"}))

    await via_browser(kit, vacancy.id, Way("aggregator", PAGE, site.id))

    page = await kit.browser.page()
    assert [call for call in page.calls if call[0] == "fill"] == [("fill", "#name", "Иван Петров")]
    assert answers[0].startswith("не вышло")


async def test_with_auto_apply_on_typing_is_as_before(board, kit_with):
    site, vacancy, kit, _ = await _typing(kit_with, board, confirming=False)

    await via_browser(kit, vacancy.id, Way("aggregator", PAGE, site.id))

    page = await kit.browser.page()
    assert [call for call in page.calls if call[0] == "fill"] == [
        ("fill", "#name", "Иван"), ("fill", "#name", "Иван Петров")]


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


async def test_a_form_the_profile_rules_out_leaves_the_vacancy_as_not_fit(board, kit_with, session_factory):
    """Дело не в способе, а в вакансии: итог несёт причину, а не урок о площадке,
    и вакансия уходит в Not Fit с этой причиной в истории."""
    site, vacancy = await board()
    kit = await kit_with([finish_step("not_fit", "Условие формы")])
    outcome = await via_browser(kit, vacancy.id, Way("aggregator", PAGE, site.id))
    assert outcome == Unfit("Условие формы")
    assert (await only_row(session_factory, Vacancy)).status is VacancyStatus.NOT_FIT
    assert (await only_row(session_factory, VacancyStatusHistory)).explanation == "Условие формы."


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


async def test_the_applier_is_told_which_resume_to_choose(board, kit_with, session_factory):
    site, vacancy = await board()
    await put(session_factory, aggregator_resume_row(
        site.id, title="Повар-кондитер", url="https://site.test/resume/7", is_chosen=True))
    kit = await kit_with([record_step(PAGE, via="aggregator")])

    await via_browser(kit, vacancy.id, Way("aggregator", PAGE, site.id))

    (plan,) = kit.run_session.plans
    assert "Повар-кондитер" in plan.task and "https://site.test/resume/7" in plan.task


async def test_a_chosen_resume_missing_on_the_site_stops_the_run_and_leaves_none_chosen(
    board, kit_with, session_factory
):
    site, vacancy = await board()
    await put(session_factory,
              aggregator_resume_row(site.id, title="Пропало", url="https://site.test/resume/1",
                                    is_chosen=True),
              aggregator_resume_row(site.id, title="Осталось", url="https://site.test/resume/2",
                                    position=1))
    kit = await kit_with([finish_step("resume_missing")])

    # Вакансия на поддомене: весть называет сайт агрегатора, а не адрес вакансии.
    with pytest.raises(ResumeMissing) as stop:
        await via_browser(kit, vacancy.id, Way("aggregator", "https://spb.site.test/vacancy/1", site.id))

    assert stop.value.site == "site.test"

    rows = await all_rows(session_factory, AggregatorResume)
    assert [(r.title, r.is_chosen) for r in rows] == [("Осталось", False)]
