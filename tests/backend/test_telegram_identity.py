"""Следствия, которые наблюдают тесты `backend/domain/telegram_identity.py`."""

import pytest

from backend.domain.telegram_identity import (
    DialogPeer,
    hrs_in_dialog_order,
    normalize_username,
    typed_username,
)


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


class Contact:
    """Наш собеседник в том виде, в каком его знает база."""

    def __init__(self, hr_id, *, user_id=None, username=None):
        self.id = hr_id
        self.telegram_user_id = user_id
        self.telegram_username = username


def test_the_order_of_the_dialog_list_wins_over_the_order_of_the_contacts():
    """Собеседники выстраиваются по свежести переписки, а не по номеру строки.

    Догон читает их подряд и на каждого тратит обращение к Telegram; человек
    закрывает окно раньше, чем очередь дойдёт до конца. Свежая переписка — та,
    ради которой он приложение и открыл, — обязана идти первой.
    """
    contacts = [Contact(1, user_id=11), Contact(2, user_id=22)]
    chats = [DialogPeer(22), DialogPeer(11)]

    assert [hr.id for hr in hrs_in_dialog_order(contacts, chats)] == [2, 1]


def test_a_contact_without_a_dialog_goes_last_but_is_not_dropped():
    """Собеседник, с которым разговора нет, уходит в хвост, а не выбрасывается.

    В хвост — потому что читать у него нечего и стоит попытка дорого: его
    номера нет в кэше пиров, и чтение уходит в розыск по нику, который Telegram
    душит ожиданиями в десятки секунд.

    Но не выбрасывается: список переписок мог прийти неполным — чтение его
    обрывается, когда закладку поставить не по чему, — и отбор по нему молча
    потерял бы живую переписку.
    """
    contacts = [Contact(1, user_id=11), Contact(2, user_id=22)]

    ordered = hrs_in_dialog_order(contacts, [DialogPeer(22)])

    assert [hr.id for hr in ordered] == [2, 1]


def test_a_contact_known_only_by_a_handle_is_matched_by_it():
    """Известного одним ником опознают по нику, без оглядки на регистр.

    Так заводит собеседников разбор объявления: в посте стоит `@ник`, а номера
    учётной записи там нет вовсе. Не сведи мы его по нику — именно у такого
    переписка и не догонялась бы, а он-то как раз и пишет первым.
    """
    # Второй нужен, чтобы проверка вообще могла упасть: с одним собеседником
    # он попал бы в ответ и головой, и хвостом, и ответ был бы тем же.
    contacts = [Contact(1, user_id=11), Contact(78, username="Mastakova_TeamLead")]

    matched = hrs_in_dialog_order(contacts, [DialogPeer(8435291761, "mastakova_teamlead")])

    assert [hr.id for hr in matched] == [78, 1]


def test_one_dialog_takes_one_contact():
    """Одну переписку забирает тот, кто опознан по номеру, а не по нику.

    Ник свободно достаётся другому человеку, и запись со своим номером под
    чужим ником принадлежит не тому, с кем идёт разговор. Второй при этом не
    пропадает — уходит в хвост, как всякий без переписки.
    """
    by_number = Contact(1, user_id=500, username="кто-то")
    by_handle = Contact(2, username="кто-то")

    matched = hrs_in_dialog_order([by_number, by_handle], [DialogPeer(500, "кто-то")])

    assert [hr.id for hr in matched] == [1, 2]

