"""Домен «Агрегаторы»: перечень, заведение, удаление, включение, вход и обход."""

import httpx

from backend.agent.availability import NO_DRIVER
from backend.bot.aggregators import HUMAN_TIMEOUT_NOTE
from backend.models import Aggregator, VacancyStatus
from backend.repository.aggregators import WEB_SEARCH_NAME
from tests.dbio import all_rows, put
from tests.factories import vacancy_row
from tests.factories_aggregators import aggregator_row, application_row, web_search_row
from tests.fakes.site_home import serve_home


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


async def test_an_address_is_stored_as_a_new_aggregator_named_after_the_site(
    api, ask, monkeypatch
):
    """Сайт не ответил, модели нет — агрегатор всё равно заводится, под именем сайта."""
    serve_home(monkeypatch, httpx.ConnectError("сеть отвалилась"))

    answer = (await ask(api.aggregators.create, {"address": "https://www.Site.test/jobs"}))["ok"]

    assert (answer["status"], answer["aggregator"]["host"], answer["aggregator"]["name"]) == (
        "created", "site.test", "Site"
    )


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


async def test_a_toggle_without_its_flag_is_refused_with_the_number_echoed(api, ask):
    """По номеру в отказе окно возвращает на место именно нажатый тумблер."""
    answer = await ask(api.aggregators.set_active, {"aggregator_id": 7})

    assert (answer["fail"], answer["aggregator_id"], answer["is_active"]) == (
        "fields", 7, None
    )


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


async def test_the_list_counts_each_source_vacancies_and_finds_by_host(
    api, ask, session_factory
):
    """Строка перечня несёт счёт вакансий своего источника; поиск идёт и по хосту.

    По счёту источник оценивают так же, как канал: не давший ни одной вакансии
    — повод его выключить. Хост ищется наравне с именем: имя заведённого
    агрегатора и есть его хост, но человек может его переименовать.
    """
    web = web_search_row()
    site = aggregator_row(name="Работа", host="site.test")
    other = aggregator_row(name="Другой", host="other.test")
    await put(session_factory, site, web, other)
    await put(session_factory,
              vacancy_row(source_aggregator_id=site.id, source_key="v/1"),
              vacancy_row(source_aggregator_id=site.id, source_key="v/2"),
              vacancy_row(source_aggregator_id=site.id, source_key="v/3", is_parsed=False))

    everything = (await ask(api.aggregators.list, {}))["ok"]
    found = (await ask(api.aggregators.list, {"search": "SITE"}))["ok"]

    assert [(a["name"], a["vacancy_count"]) for a in everything["aggregators"]] == [
        (WEB_SEARCH_NAME, 0), ("Работа", 2), ("Другой", 0)
    ]
    assert (found["search"], [a["name"] for a in found["aggregators"]]) == ("SITE", ["Работа"])


async def test_a_broken_list_payload_still_shows_everything(api, ask, session_factory):
    await put(session_factory, aggregator_row())

    answer = (await ask(api.aggregators.list, "мусор"))["ok"]

    assert (answer["search"], len(answer["aggregators"])) == ("", 1)


async def test_the_card_counts_only_this_source_vacancies(api, ask, session_factory):
    """Числа карточки — по вакансиям этого агрегатора и только его."""
    site = aggregator_row(host="site.test", is_logged_in=True)
    other = aggregator_row(host="other.test")
    await put(session_factory, site, other)
    await put(session_factory,
              vacancy_row(source_aggregator_id=site.id, source_key="v/1"),
              vacancy_row(source_aggregator_id=site.id, source_key="v/2",
                          status=VacancyStatus.APPLIED),
              vacancy_row(source_aggregator_id=other.id, source_key="v/3"))

    card = (await ask(api.aggregators.detail, site.id))["ok"]

    assert (card["aggregator_id"], card["host"], card["is_logged_in"]) == (site.id, "site.test", True)
    assert card["stats"]["total"] == 2
    assert card["stats"]["status_counts"][VacancyStatus.APPLIED.value] == 1
    assert (card["stats"]["fit_percent"], card["stats"]["apply_percent"]) == (100, 50)


async def test_the_site_icon_shows_in_the_list_and_on_the_card(api, ask, session_factory):
    """Значок вшит в ответ картинкой, как аватар канала; без значка — пусто."""
    site = aggregator_row(host="site.test", avatar=b"icon")
    bare = aggregator_row(host="bare.test")
    await put(session_factory, site, bare)

    listed = {row["host"]: row["avatar"] for row in (await ask(api.aggregators.list, {}))["ok"]["aggregators"]}
    card = (await ask(api.aggregators.detail, site.id))["ok"]

    assert listed["site.test"].startswith("data:image/") and listed["bare.test"] is None
    assert card["avatar"] == listed["site.test"]


async def test_a_card_of_a_missing_aggregator_is_refused_with_the_number(api, ask):
    answer = await ask(api.aggregators.detail, 404)

    assert (answer["fail"], answer["aggregator_id"]) == ("denied", 404)


async def test_only_this_aggregator_vacancies_are_paged(api, ask, session_factory):
    mine = aggregator_row(host="site.test")
    other = aggregator_row(host="other.test")
    await put(session_factory, mine, other)
    await put(session_factory,
              vacancy_row(title="Моя", source_aggregator_id=mine.id, source_key="v/1"),
              vacancy_row(title="Чужая", source_aggregator_id=other.id, source_key="v/2"))

    answer = (await ask(api.aggregators.vacancies, {"aggregator_id": mine.id, "limit": 5}))["ok"]

    assert (answer["aggregator_id"], answer["has_more"]) == (mine.id, False)
    assert [row["title"] for row in answer["vacancies"]] == ["Моя"]


async def test_a_page_without_the_aggregator_is_bad_fields(api, ask):
    answer = await ask(api.aggregators.vacancies, {"limit": 5})

    assert answer["fail"] == "fields"


async def test_the_switch_over_all_leaves_each_row_as_it_was(api, ask, session_factory):
    """Общий выключатель — отдельный признак: тумблеры строк он не переписывает."""
    await put(session_factory,
              aggregator_row(host="site.test", is_logged_in=True, is_active=True),
              aggregator_row(host="other.test", is_active=False))

    turned = (await ask(api.aggregators.set_all_active, {"is_active": False}))["ok"]
    listed = (await ask(api.aggregators.list, {}))["ok"]

    assert turned == {"is_active": False}
    assert listed["enabled"] is False
    assert [a["is_active"] for a in listed["aggregators"]] == [True, False]


async def test_the_switch_over_all_comes_back_on(api, ask):
    await ask(api.aggregators.set_all_active, {"is_active": False})
    await ask(api.aggregators.set_all_active, {"is_active": True})

    assert (await ask(api.aggregators.list, {}))["ok"]["enabled"] is True


async def test_turning_all_without_the_flag_is_bad_fields(api, ask):
    answer = await ask(api.aggregators.set_all_active, {})

    assert answer["fail"] == "fields"


async def test_blacklisting_switches_the_aggregator_off_and_marks_it(api, ask, session_factory):
    site = aggregator_row(host="site.test", is_logged_in=True, is_active=True)
    await put(session_factory, site)

    blocked = (await ask(api.aggregators.block, site.id))["ok"]
    listed = (await ask(api.aggregators.list, {}))["ok"]["aggregators"]
    card = (await ask(api.aggregators.detail, site.id))["ok"]

    assert (blocked["value"], blocked["existed"]) == ("site.test", False)
    assert [(a["is_active"], a["is_blacklisted"]) for a in listed] == [(False, True)]
    assert card["blacklist_value"] == "site.test"


async def test_a_blacklisted_aggregator_is_not_switched_on(api, ask, session_factory):
    site = aggregator_row(host="site.test", is_logged_in=True)
    await put(session_factory, site)
    await ask(api.aggregators.block, site.id)

    answer = await ask(api.aggregators.set_active, {"aggregator_id": site.id, "is_active": True})

    assert answer == {"fail": "denied",
                      "detail": "В чёрном списке — снимите запись, чтобы включить"}


async def test_unblocking_clears_the_mark(api, ask, session_factory):
    site = aggregator_row(host="site.test")
    await put(session_factory, site)
    await ask(api.aggregators.block, site.id)

    removed = (await ask(api.aggregators.unblock, site.id))["ok"]
    card = (await ask(api.aggregators.detail, site.id))["ok"]

    assert (removed["updated"], card["blacklist_value"]) == (1, None)


async def test_web_search_cannot_be_blacklisted(api, ask, session_factory):
    web = web_search_row()
    await put(session_factory, web)

    answer = await ask(api.aggregators.block, web.id)

    assert (answer["fail"], answer["detail"]) == ("denied", "Поиск по сети в чёрный список не заносится")


async def test_a_run_of_a_blacklisted_site_is_explained(api, ask, with_bot, told, session_factory):
    with_bot(aggregator_run="blacklisted")
    site = aggregator_row()
    await put(session_factory, site)

    await ask(api.aggregators.run_now, site.id)

    assert await told() == {
        "message": "В чёрном списке — снимите запись, чтобы работать с сайтом", "danger": True
    }
