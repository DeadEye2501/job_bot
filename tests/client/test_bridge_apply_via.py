"""Отклик выбранным способом: какие способы есть у вакансии и запуск агента одним из них."""

from backend.domain.apply_order import Way
from backend.models import ContactAddedBy
from tests.dbio import put
from tests.factories import blacklist_row, hr_row, vacancy_row
from tests.factories_aggregators import aggregator_row, mail_account_row, vacancy_contact_row

FORM = "https://company.test/apply"


async def _vacancy(session_factory, **over):
    vacancy = vacancy_row(**over)
    await put(session_factory, vacancy)
    await put(session_factory, vacancy_contact_row(vacancy.id, FORM, added_by=ContactAddedBy.PARSE),
              vacancy_contact_row(vacancy.id, "hr@company.test", added_by=ContactAddedBy.PARSE))
    return vacancy


async def test_the_ways_of_a_vacancy_come_with_telegram_and_the_lock(
    api, ask, session, session_factory
):
    hr = hr_row()
    await put(session_factory, hr)
    vacancy = await _vacancy(session_factory, hr_id=hr.id)
    await put(session_factory, mail_account_row())

    answer = (await ask(api.vacancies.apply_ways, vacancy.id))["ok"]

    assert answer["ways"] == [{"method": "form", "target": FORM},
                              {"method": "email", "target": "hr@company.test"}]
    assert answer["telegram"] is True and answer["lock"]


async def test_no_way_leads_to_a_blacklisted_site(api, ask, session_factory):
    """Сайт в отсеве не работает и для откликов: ни кнопкой его агрегатора, ни
    формой на нём. Вакансию могли разобрать до того, как сайт занесли в отсев."""
    site = aggregator_row(host="board.test", is_logged_in=True)
    await put(session_factory, site, blacklist_row(kind="aggregator", value="board.test"))
    vacancy = vacancy_row(source_aggregator_id=site.id, source_key="v/1",
                          source_url="https://board.test/v/1")
    await put(session_factory, vacancy)
    await put(session_factory,
              vacancy_contact_row(vacancy.id, "https://spb.board.test/apply", added_by=ContactAddedBy.PARSE),
              vacancy_contact_row(vacancy.id, FORM, added_by=ContactAddedBy.PARSE))

    answer = (await ask(api.vacancies.apply_ways, vacancy.id))["ok"]

    assert answer["ways"] == [{"method": "form", "target": FORM}]


async def test_a_missing_vacancy_has_no_ways(api, ask):
    answer = await ask(api.vacancies.apply_ways, 999)

    assert (answer["fail"], answer["detail"]) == ("denied", "Вакансия не найдена.")


async def test_a_chosen_way_goes_to_the_agent(api, ask, with_bot, told, session_factory):
    bot = with_bot()
    vacancy = await _vacancy(session_factory)

    answer = await ask(api.vacancies.apply_via,
                       {"vacancy_id": vacancy.id, "method": "form", "target": FORM})

    assert answer["ok"]["started"] is True
    assert (await told())["danger"] is False
    assert bot.calls == [("apply_via_agent", vacancy.id, Way("form", FORM, None))]


async def test_a_way_the_vacancy_does_not_have_is_refused(api, ask, with_bot, session_factory):
    bot = with_bot()
    vacancy = await _vacancy(session_factory)

    answer = await ask(api.vacancies.apply_via,
                       {"vacancy_id": vacancy.id, "method": "form", "target": "https://evil.test/"})

    assert answer["fail"] == "denied" and bot.calls == []


