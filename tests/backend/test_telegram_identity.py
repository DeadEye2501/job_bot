"""Следствия, которые наблюдают тесты `backend/domain/telegram_identity.py`."""

import pytest

from backend.domain.telegram_identity import (
    ARTICLE_URL_RE,
    DialogPeer,
    hrs_to_catch_up,
    normalize_username,
    typed_username,
)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        pytest.param(
            "вся вакансия https://telegra.ph/Senior-Manual-QA-08-21",
            ["https://telegra.ph/Senior-Manual-QA-08-21"],
            id="адрес словами",
        ),
        pytest.param(
            "ПОСМОТРЕТЬ (https://telegra.ph/Senior-Manual-QA-08-21)",
            ["https://telegra.ph/Senior-Manual-QA-08-21"],
            id="адрес за подписью ссылки",
        ),
        pytest.param(
            "вся вакансия https://telegra.ph/Senior-Manual-QA-08-21.",
            ["https://telegra.ph/Senior-Manual-QA-08-21"],
            id="точка в конце предложения",
        ),
        pytest.param(
            "тут https://telegra.ph/QA-08-21, а ещё тут",
            ["https://telegra.ph/QA-08-21"],
            id="запятая после адреса",
        ),
        pytest.param(
            "вся вакансия https://telegra.ph/QA-08-21#trebovaniya",
            ["https://telegra.ph/QA-08-21#trebovaniya"],
            id="якорь остаётся в адресе",
        ),
        pytest.param("наш сайт https://telegra.ph/", [], id="корень без статьи"),
        pytest.param("https://habr.com/QA-08-21", [], id="чужой сайт"),
    ],
)
def test_which_addresses_count_as_an_article(text, expected):
    """Адрес статьи узнаётся в тексте объявления и не прихватывает лишнего.

    Скобка отдельно: адрес спрятанной ссылки дописывают в текст именно в
    скобках, и утащенная в адрес закрывающая скобка вела бы в никуда.
    """
    assert ARTICLE_URL_RE.findall(text) == expected


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

    assert [hr.id for hr in hrs_to_catch_up(contacts, chats)] == [2, 1]


def test_a_contact_without_a_dialog_is_not_read_at_all():
    """Собеседника, с которым разговора нет, догон не читает.

    Читать у него нечего, а попытка дорогая: его номера нет в кэше пиров, и
    чтение уходит в розыск по нику, за который Telegram запрещает такой розыск
    часами — на весь аккаунт, вместе с розыском HR новых вакансий.
    """
    contacts = [Contact(1, user_id=11), Contact(2, user_id=22)]

    ordered = hrs_to_catch_up(contacts, [DialogPeer(22)])

    assert [hr.id for hr in ordered] == [2]


def test_without_a_known_dialog_list_everyone_is_read():
    """Список переписок неизвестен — читаются все: отбор по нему молча
    потерял бы живую переписку."""
    contacts = [Contact(1, user_id=11), Contact(2, user_id=22)]

    assert [hr.id for hr in hrs_to_catch_up(contacts, None)] == [1, 2]


def test_a_contact_known_only_by_a_handle_is_matched_by_it():
    """Известного одним ником опознают по нику, без оглядки на регистр.

    Так заводит собеседников разбор объявления: в посте стоит `@ник`, а номера
    учётной записи там нет вовсе. Не сведи мы его по нику — именно у такого
    переписка и не догонялась бы, а он-то как раз и пишет первым.
    """
    contacts = [Contact(1, user_id=11), Contact(78, username="Mastakova_TeamLead")]

    matched = hrs_to_catch_up(contacts, [DialogPeer(8435291761, "mastakova_teamlead")])

    assert [hr.id for hr in matched] == [78]


def test_one_dialog_takes_one_contact():
    """Одну переписку забирает тот, кто опознан по номеру, а не по нику.

    Ник свободно достаётся другому человеку, и запись со своим номером под
    чужим ником принадлежит не тому, с кем идёт разговор. Второму переписки
    не достаётся, и его не читают, как всякого без переписки.
    """
    by_number = Contact(1, user_id=500, username="кто-то")
    by_handle = Contact(2, username="кто-то")

    matched = hrs_to_catch_up([by_number, by_handle], [DialogPeer(500, "кто-то")])

    assert [hr.id for hr in matched] == [1]

