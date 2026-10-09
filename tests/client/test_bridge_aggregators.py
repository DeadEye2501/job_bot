"""Домен «Агрегаторы»: перечень, заведение, удаление, включение, вход и обход."""

from backend.agent.availability import NO_DRIVER
from backend.bot.aggregators import HUMAN_TIMEOUT_NOTE
from backend.models import Aggregator
from backend.repository.aggregators import WEB_SEARCH_NAME
from tests.dbio import all_rows, put
from tests.factories import vacancy_row
from tests.factories_aggregators import aggregator_row, application_row, web_search_row


async def test_the_list_marks_web_search_and_says_why_the_agent_is_locked(
    api, ask, session_factory
):
    await put(session_factory, aggregator_row(host="site.test"),
              web_search_row())

    answer = (await ask(api.aggregators.list))["ok"]

    assert [(a["name"], a["is_web_search"]) for a in answer["aggregators"]] == [
        (WEB_SEARCH_NAME, True), ("HeadHunter", False)
    ]
    assert answer["lock"] == NO_DRIVER


async def test_an_address_is_stored_as_a_new_aggregator(api, ask, session_factory):
    answer = (await ask(api.aggregators.create, {"address": "https://www.Site.test/jobs"}))["ok"]

    assert (answer["status"], answer["aggregator"]["host"]) == ("created", "site.test")


async def test_an_address_that_is_not_a_site_is_refused(api, ask):
    answer = await ask(api.aggregators.create, {"address": "   "})

    assert answer == {"fail": "denied", "detail": "Адрес не похож на сайт"}


async def test_deleting_an_aggregator_with_applications_asks_first(
    api, ask, with_bot, session_factory
):
    bot = with_bot()
    site = aggregator_row()
    await put(session_factory, site)
    vacancy = vacancy_row(source_aggregator_id=site.id, source_key="v/1")
    await put(session_factory, vacancy)
    await put(session_factory, application_row(vacancy.id))

    asked = await ask(api.aggregators.delete, {"aggregator_id": site.id})
    done = await ask(api.aggregators.delete, {"aggregator_id": site.id, "confirmed": True})

    assert asked["ok"] == {"confirm": 1}
    assert done["ok"]["deleted"] is True
    assert bot.calls == [("delete_aggregator", site.id)]


async def test_web_search_cannot_be_deleted(api, ask, with_bot, session_factory):
    with_bot()
    web = web_search_row()
    await put(session_factory, web)

    answer = await ask(api.aggregators.delete, {"aggregator_id": web.id, "confirmed": True})

    assert answer == {"fail": "denied", "detail": "Поиск по сети удалить нельзя"}


async def test_an_aggregator_without_login_is_not_switched_on(api, ask, session_factory):
    site = aggregator_row(is_logged_in=False)
    await put(session_factory, site)

    answer = await ask(api.aggregators.set_active, {"aggregator_id": site.id, "is_active": True})

    assert answer == {"fail": "denied", "detail": "Сначала войдите на сайт"}
    assert [a.is_active for a in await all_rows(session_factory, Aggregator)] == [False]


async def test_a_run_answers_before_it_runs_and_tells_the_outcome(
    api, ask, with_bot, told, session_factory
):
    bot = with_bot(aggregator_run="human_timeout")
    site = aggregator_row()
    await put(session_factory, site)

    answer = await ask(api.aggregators.run_now, site.id)

    assert answer["ok"]["started"] is True
    assert await told() == {"message": HUMAN_TIMEOUT_NOTE, "danger": True}
    assert ("run_aggregator_now", site.id) in bot.calls


async def test_a_login_on_a_busy_slot_is_explained(api, ask, with_bot, told, session_factory):
    with_bot(aggregator_login="busy")
    site = aggregator_row()
    await put(session_factory, site)

    await ask(api.aggregators.login, site.id)

    assert await told() == {"message": "Уже идёт другой цикл, попробуйте позже.", "danger": True}


async def test_without_a_bot_nothing_is_launched(api, ask, session_factory):
    site = aggregator_row()
    await put(session_factory, site)

    answer = await ask(api.aggregators.run_now, site.id)

    assert (answer["fail"], answer["detail"]) == ("denied", "Бот ещё не готов.")
