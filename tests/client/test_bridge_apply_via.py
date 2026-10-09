"""Отклик выбранным способом: какие способы есть у вакансии и запуск агента одним из них."""

from backend.domain.apply_order import Way
from backend.models import ContactAddedBy
from backend.repository.mail_account import MailSettings, save_mail_account
from tests.dbio import put
from tests.factories import hr_row, vacancy_row
from tests.factories_aggregators import vacancy_contact_row

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
    async with session.begin():
        await save_mail_account(session, MailSettings("me@mail.test", "secret", "smtp.mail.test", 465))

    answer = (await ask(api.vacancies.apply_ways, vacancy.id))["ok"]

    assert answer["ways"] == [{"method": "form", "target": FORM},
                              {"method": "email", "target": "hr@company.test"}]
    assert answer["telegram"] is True and answer["lock"]


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


async def test_off_mode_is_explained(api, ask, with_bot, told, session_factory):
    with_bot(apply_via="off")
    vacancy = await _vacancy(session_factory)

    await ask(api.vacancies.apply_via, {"vacancy_id": vacancy.id, "method": "form", "target": FORM})

    said = await told()
    assert said["danger"] is True and "выключен" in said["message"]
