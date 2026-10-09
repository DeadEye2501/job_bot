"""Порядок способов отклика: кнопка агрегатора, форма, почта."""

from backend.domain.apply_order import ApplyFacts, KnownSite, Way, apply_ways

SITE = KnownSite(1, "site.test")
WEB = KnownSite(9, None)


def _facts(**over) -> ApplyFacts:
    fields = dict(source_url=None, source_site=None, contacts=[], sites=[SITE],
                  mail_ready=True, closed=set())
    fields.update(over)
    return ApplyFacts(**fields)


def test_a_vacancy_from_an_aggregator_goes_through_its_button_first():
    ways = apply_ways(_facts(source_url="https://site.test/vacancy/1", source_site=SITE,
                             contacts=["hr@company.test"]))
    assert ways == [Way("aggregator", "https://site.test/vacancy/1", 1),
                    Way("email", "hr@company.test", None)]


def test_an_aggregator_link_in_the_contacts_counts_too():
    ways = apply_ways(_facts(contacts=["https://spb.site.test/vacancy/9"]))
    assert ways[0] == Way("aggregator", "https://spb.site.test/vacancy/9", 1)


def test_a_closed_aggregator_is_skipped_until_the_round_ends():
    ways = apply_ways(_facts(source_url="https://site.test/vacancy/1", source_site=SITE,
                             closed={1}))
    assert ways == []


def test_a_web_find_goes_to_its_own_page_as_a_form():
    ways = apply_ways(_facts(source_url="https://company.test/jobs/1", source_site=WEB))
    assert ways[0] == Way("form", "https://company.test/jobs/1", None)


def test_a_web_find_on_a_known_aggregator_goes_through_its_button():
    """Веб-поиск принёс страницу агрегатора человека: это его кнопка, а не форма работодателя."""
    ways = apply_ways(_facts(source_url="https://site.test/vacancy/5", source_site=WEB))
    assert ways == [Way("aggregator", "https://site.test/vacancy/5", 1)]


def test_the_page_of_a_channel_post_is_not_a_form():
    """Адрес у вакансии из канала — пост в Telegram, а не форма работодателя."""
    assert apply_ways(_facts(source_url="https://t.me/jobs/10")) == []


def test_another_link_in_the_contacts_is_a_form():
    ways = apply_ways(_facts(contacts=["https://company.test/apply", "hr@company.test"]))
    assert ways == [Way("form", "https://company.test/apply", None),
                    Way("email", "hr@company.test", None)]


def test_mail_is_offered_only_when_set_up():
    assert apply_ways(_facts(contacts=["hr@company.test"], mail_ready=False)) == []


def test_a_phone_is_not_a_way_to_apply():
    assert apply_ways(_facts(contacts=["+7 999 000-00-00"])) == []


def test_a_link_to_an_aggregator_without_login_is_neither_a_button_nor_a_form():
    """Без входа кнопка агрегатора не работает, а формой работодателя его страница не бывает."""
    away = KnownSite(2, "board.test", logged_in=False)
    assert apply_ways(_facts(contacts=["https://board.test/vacancy/3"], sites=[SITE, away])) == []
