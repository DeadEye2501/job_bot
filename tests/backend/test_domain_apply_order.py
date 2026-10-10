"""Порядок способов отклика: Telegram, кнопка агрегатора, форма, почта."""

from backend.domain.apply_order import KnownSite, VacancyFacts, Way, World, apply_ways
from tests.factories_aggregators import world_of

SITE = KnownSite(1, "site.test")
WEB = KnownSite(9, None)


def _vacancy(**over) -> VacancyFacts:
    return VacancyFacts(**{"hr_handle": None, "source_url": None,
                           "source_site": None, "contacts": [], **over})


def _world(**over) -> World:
    """Мир с одним агрегатором человека — `SITE`."""
    return world_of(**{"sites": [SITE], **over})


def test_telegram_goes_first():
    ways = apply_ways(_vacancy(hr_handle="@hr_name", contacts=[
        "https://site.test/vacancy/1", "hr@company.test"]), _world())
    assert [w.method for w in ways] == ["telegram", "aggregator", "email"]
    assert ways[0] == Way("telegram", "@hr_name", None)


def test_a_closed_telegram_is_not_offered():
    ways = apply_ways(_vacancy(hr_handle="@hr_name"), _world(telegram_open=False))
    assert ways == []


def test_without_a_ready_agent_only_telegram_and_mail_remain():
    ways = apply_ways(_vacancy(hr_handle="@hr_name", contacts=[
        "https://site.test/vacancy/1", "https://company.test/apply", "hr@company.test"]),
        _world(agent_ready=False))
    assert [w.method for w in ways] == ["telegram", "email"]


def test_a_closed_site_drops_its_button():
    ways = apply_ways(_vacancy(source_url="https://site.test/vacancy/1", source_site=SITE),
                      _world(closed_sites={1}))
    assert ways == []


def test_a_vacancy_from_an_aggregator_goes_through_its_button_first():
    ways = apply_ways(_vacancy(source_url="https://site.test/vacancy/1", source_site=SITE,
                               contacts=["hr@company.test"]), _world())
    assert ways == [Way("aggregator", "https://site.test/vacancy/1", 1),
                    Way("email", "hr@company.test", None)]


def test_an_aggregator_link_in_the_contacts_counts_too():
    ways = apply_ways(_vacancy(contacts=["https://spb.site.test/vacancy/9"]), _world())
    assert ways[0] == Way("aggregator", "https://spb.site.test/vacancy/9", 1)


def test_a_web_find_goes_to_its_own_page_as_a_form():
    ways = apply_ways(_vacancy(source_url="https://company.test/jobs/1", source_site=WEB), _world())
    assert ways[0] == Way("form", "https://company.test/jobs/1", None)


def test_a_web_find_on_a_known_aggregator_goes_through_its_button():
    """Веб-поиск принёс страницу агрегатора человека: это его кнопка, а не форма работодателя."""
    ways = apply_ways(_vacancy(source_url="https://site.test/vacancy/5", source_site=WEB), _world())
    assert ways == [Way("aggregator", "https://site.test/vacancy/5", 1)]


def test_the_page_of_a_channel_post_is_not_a_form():
    """Адрес у вакансии из канала — пост в Telegram, а не форма работодателя."""
    assert apply_ways(_vacancy(source_url="https://t.me/jobs/10"), _world()) == []


def test_another_link_in_the_contacts_is_a_form():
    ways = apply_ways(_vacancy(contacts=["https://company.test/apply", "hr@company.test"]), _world())
    assert ways == [Way("form", "https://company.test/apply", None),
                    Way("email", "hr@company.test", None)]


def test_mail_is_offered_only_when_set_up():
    assert apply_ways(_vacancy(contacts=["hr@company.test"]), _world(mail_ready=False)) == []


def test_a_phone_is_not_a_way_to_apply():
    assert apply_ways(_vacancy(contacts=["+7 999 000-00-00"]), _world()) == []


def test_a_link_to_an_aggregator_without_login_is_neither_a_button_nor_a_form():
    """Без входа кнопка агрегатора не работает, а формой работодателя его страница не бывает."""
    away = KnownSite(2, "board.test", logged_in=False)
    assert apply_ways(_vacancy(contacts=["https://board.test/vacancy/3"]),
                      _world(sites=[SITE, away])) == []
