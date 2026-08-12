"""Следствия, которые наблюдают тесты `backend/domain/telegram_identity.py`."""

import pytest

from backend.domain.telegram_identity import normalize_username, typed_username


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("@user_name", "user_name"),
        ("user_name", "user_name"),
        ("https://t.me/user_name", "user_name"),
        ("http://t.me/user_name", "user_name"),
        ("t.me/user_name/", "user_name"),
        ("t.me/user_name/123", "user_name"),
        ("  @user_name  ", "user_name"),
        ("t.me/s/user_name", "user_name"),
        ("telegram.me/user_name", "user_name"),
        ("www.t.me/user_name", "user_name"),
        ("HTTPS://T.ME/user_name", "user_name"),
        ("Https://T.me/user_name", "user_name"),
        ("t.me/S/user_name", "user_name"),
    ],
)
def test_the_username_is_extracted_from_any_link_form(raw, expected):
    """Имя вытаскивается из любой записи ссылки.

    Верхний регистр в схеме и домене — такая же запись, как прочие: её
    оставляют автоподстановка почтовых клиентов и сами объявления. Не узнав
    её, разбор оставит в карточке мусорную строку, а приговор о пустоте
    засчитает её за настоящий контакт — то есть отодвинет пустышку от
    «мусора» на целое деление.
    """
    assert normalize_username(raw) == expected


@pytest.mark.parametrize("typed", ["abcd", "@drew", "t.me/drew"])
def test_a_four_letter_handle_typed_by_a_person_is_accepted(typed):
    """Четырёхбуквенный ник, набранный человеком, принимается.

    Новым такие Telegram не выдаёт, но выданные когда-то работают, и
    собеседник с таким ником — обычное дело. Отвергнув его, форма не дала
    бы завести такого HR вовсе.
    """
    assert typed_username(typed) == typed.rsplit("/", 1)[-1].lstrip("@")


def test_a_four_letter_word_from_an_ad_is_not_taken_for_a_handle():
    """Короткое слово из объявления ником не считается.

    В объявлении контакт пишут как придётся, и «Anna» там — имя, а не ник.
    Приняв его за ник, разбор разыскал бы у Telegram живую чужую учётную
    запись, привязал бы к ней HR — и автоотправка ушла бы постороннему.
    Подтверждать тут некому: за формой стоит человек, за объявлением нет.
    """
    assert normalize_username("Anna") is None


@pytest.mark.parametrize(
    "raw",
    [
        None,
        "",
        "   ",
        "+79991234567",
        "t.me/joinchat/AAAA",
        "t.me/c/12345",
        "www.jobsboard",
        "abc",
        "1user_name",
        "user-name",
    ],
)
def test_an_unusable_contact_yields_no_username(raw):
    """Негодная запись даёт отсутствие имени, а не мусор."""
    assert normalize_username(raw) is None
