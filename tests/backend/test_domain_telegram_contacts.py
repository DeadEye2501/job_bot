"""Какие записи — Telegram, о ком из них спрашивать и кого из людей взять HR."""

from backend.domain.telegram_contacts import (
    SortedTelegram, TelegramContact, chosen_person, sorted_telegram, telegram_contacts,
)


def test_telegram_entries_keep_their_order_with_the_named_hr_first():
    found = telegram_contacts("@anna_hr", ["hr@acme.com", "https://t.me/jobs_channel/15", "t.me/boris_hr"])

    assert found == [
        TelegramContact("@anna_hr", "anna_hr"),
        TelegramContact("https://t.me/jobs_channel/15", None),
        TelegramContact("t.me/boris_hr", "boris_hr"),
    ]


def test_one_nick_written_twice_is_one_entry():
    assert telegram_contacts(None, ["@Anna_hr", "https://t.me/anna_hr"]) == [TelegramContact("@Anna_hr", "Anna_hr")]


def test_a_bare_word_is_a_nick_only_when_the_parse_named_it_the_hr():
    """Разбор отдаёт названного HR и голым ником; среди прочих контактов голое слово — не ник."""
    assert telegram_contacts("anna_hr", ["boris_hr"]) == [TelegramContact("anna_hr", "anna_hr")]


def test_an_invitation_has_no_nick_to_ask_about_and_stays_a_contact():
    assert telegram_contacts(None, ["https://t.me/+AbCdEf", "https://t.me/joinchat/AbCdEf"]) == []


def test_the_named_person_is_chosen_otherwise_the_first():
    assert chosen_person("boris_hr", ["anna_hr", "Boris_hr"]) == "Boris_hr"
    assert chosen_person("jobs", ["anna_hr", "boris_hr"]) == "anna_hr"
    assert chosen_person(None, ["anna_hr", "boris_hr"]) == "anna_hr"
    assert chosen_person("anna_hr", []) is None


def test_one_channel_written_two_ways_lands_in_contacts_once():
    assert sorted_telegram("@jobs_channel", ["https://t.me/jobs_channel", "hr@acme.com"], [], set()) == SortedTelegram(
        None, ["@jobs_channel", "hr@acme.com"], [])


def test_people_found_by_the_seeker_leave_the_contacts_whether_chosen_or_not():
    found = ["https://t.me/anna_hr", "https://t.me/boris_hr", "https://t.me/jobs_channel/15"]

    assert sorted_telegram(None, [], found, {"anna_hr", "boris_hr"}) == SortedTelegram(
        "https://t.me/anna_hr", [], ["https://t.me/anna_hr", "https://t.me/boris_hr"])
