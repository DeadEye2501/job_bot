"""Отклик выбранным способом: какие способы доступны у вакансии и запуск одного из них."""

from backend.domain.apply_order import Way
from backend.models import ContactAddedBy
from tests.dbio import put
from tests.factories import hr_row, vacancy_row
from tests.factories_aggregators import mail_account_row, vacancy_contact_row

FORM = "https://company.test/apply"


async def _vacancy(session_factory, **over):
    vacancy = vacancy_row(**over)
    await put(session_factory, vacancy)
    await put(session_factory, vacancy_contact_row(vacancy.id, FORM, added_by=ContactAddedBy.PARSE),
              vacancy_contact_row(vacancy.id, "hr@company.test", added_by=ContactAddedBy.PARSE))
    return vacancy


async def test_the_window_gets_only_available_ways(api, ask, session_factory):
    """Агент не готов — формы в перечне нет; Telegram и почта на месте."""
    hr = hr_row(telegram_username="hr_name")
    await put(session_factory, hr, mail_account_row())
    vacancy = await _vacancy(session_factory, hr_id=hr.id)

    answer = await ask(api.vacancies.apply_ways, vacancy.id)

    assert answer == {"ok": {"ways": [{"method": "telegram", "target": "@hr_name"},
                                      {"method": "email", "target": "hr@company.test"}]}}


async def test_a_missing_vacancy_has_no_ways(api, ask):
    answer = await ask(api.vacancies.apply_ways, 999)

    assert (answer["fail"], answer["detail"]) == ("denied", "Вакансия не найдена.")


async def test_a_chosen_way_goes_to_the_applier(api, ask, with_bot, told, session_factory):
    bot = with_bot()
    await put(session_factory, mail_account_row())
    vacancy = await _vacancy(session_factory)

    answer = await ask(api.vacancies.apply_via,
                       {"vacancy_id": vacancy.id, "method": "email", "target": "hr@company.test"})

    assert answer["ok"]["started"] is True
    assert (await told())["danger"] is False
    assert bot.calls == [("apply_chosen_way", vacancy.id, Way("email", "hr@company.test", None))]


async def test_a_way_not_available_now_is_refused(api, ask, with_bot, session_factory):
    """Форма у вакансии есть, но агент не готов: выбрать её нельзя."""
    bot = with_bot()
    vacancy = await _vacancy(session_factory)

    answer = await ask(api.vacancies.apply_via,
                       {"vacancy_id": vacancy.id, "method": "form", "target": FORM})

    assert answer["fail"] == "denied" and bot.calls == []


async def test_a_way_the_vacancy_does_not_have_is_refused(api, ask, with_bot, session_factory):
    bot = with_bot()
    vacancy = await _vacancy(session_factory)

    answer = await ask(api.vacancies.apply_via,
                       {"vacancy_id": vacancy.id, "method": "form", "target": "https://evil.test/"})

    assert answer["fail"] == "denied" and bot.calls == []
