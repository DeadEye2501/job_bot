"""Следствия чтения нагрузок форм «добавить HR» и «добавить компанию».

Каждая форма открывается с двух экранов — из подборщика вакансии и из
контактов, — а читает её одно объявление: пока их было по два, копии
разошлись написанием ника у HR и разбором написаний у компании.
"""

import pytest

from backend.repository.companies_card import create_company
from backend.repository.hr_identify import create_hr
from client.form_payloads import (
    hr_is_identified,
    read_new_company_fields,
    read_new_hr_fields,
)


def test_the_at_sign_never_reaches_the_column():
    """Ведущий «@» до колонки не доезжает.

    Колонка хранит голое написание: кнопка «в чёрный список» строит из него
    `@{username}`, и с «@» в колонке записала бы «@@ivanov», а отправка
    искала бы собеседника по несуществующему нику.
    """
    fields = read_new_hr_fields({"telegram_username": "@ivanov"})

    assert fields["telegram_username"] == "ivanov"


def test_a_pasted_telegram_link_becomes_the_bare_handle():
    """Вставленная ссылка на переписку становится голым ником.

    Ник чаще всего копируют не по буквам, а ссылкой из шапки чата. Легла
    бы она в колонку как есть — отправка пошла бы искать собеседника с
    именем «t.me/ivan» и не нашла никого.
    """
    for pasted in ("t.me/ivanov", "https://t.me/ivanov", "http://t.me/ivanov/"):
        assert read_new_hr_fields({"telegram_username": pasted})[
            "telegram_username"
        ] == "ivanov"


def test_what_is_not_a_telegram_handle_is_refused():
    """Не телеграмовское в поле ника отвергается, а не пишется как есть.

    В колонке ника осмысленно только то, чем Telegram умеет искать
    собеседника. Имя человека, номер телефона или чужая ссылка молча легли
    бы туда — и отправка потом не нашла бы никого, не сказав почему.
    """
    for wrong in ("Иван Петров", "+79991234567", "https://example.com/ivan"):
        with pytest.raises(ValueError):
            read_new_hr_fields({"telegram_username": wrong})


def test_an_empty_field_is_read_as_absence():
    """Пустое и пробельное поле читается как отсутствие, а не как строка.

    Пустая строка в колонке ника означала бы «ник есть, и он пустой»:
    отправка сочла бы такого HR адресуемым и ушла бы в никуда.
    """
    fields = read_new_hr_fields(
        {"name": "  ", "telegram_username": "   ", "notes": ""}
    )

    assert fields["name"] is None
    assert fields["telegram_username"] is None
    assert fields["notes"] is None


def test_a_username_of_one_at_sign_is_absence_too():
    """Ник из одного «@» — тоже отсутствие: после среза не остаётся ничего."""
    fields = read_new_hr_fields({"telegram_username": "@"})

    assert fields["telegram_username"] is None


def test_the_account_number_arrives_as_a_number():
    """Номер учётной записи доезжает числом, а не строкой из формы.

    Окно отдаёт поля формы строками; строка в колонке номера сравнивалась
    бы с числом из Telegram и не совпала бы ни с одним собеседником.
    """
    fields = read_new_hr_fields({"telegram_user_id": "77"})

    assert fields["telegram_user_id"] == 77


def test_an_omitted_account_number_is_absence():
    """Незаполненный номер — отсутствие; пустая строка тоже."""
    assert read_new_hr_fields({})["telegram_user_id"] is None
    assert read_new_hr_fields({"telegram_user_id": ""})["telegram_user_id"] is None


def test_notes_alone_do_not_make_a_hr_worth_saving():
    """Одни заметки записью не считаются.

    Ни поиском, ни отправкой такую строку не достать: сослаться на
    человека нечем, и на экране она осталась бы строкой из одних заметок.
    """
    assert hr_is_identified(read_new_hr_fields({"notes": "звонил в среду"})) is False


def test_any_single_way_to_name_the_person_is_enough():
    """Хватает любого одного: имени, ника или номера учётной записи."""
    assert hr_is_identified(read_new_hr_fields({"name": "Иван"})) is True
    assert hr_is_identified(read_new_hr_fields({"telegram_username": "@ivanov"})) is True
    assert hr_is_identified(read_new_hr_fields({"telegram_user_id": "77"})) is True


def test_a_number_that_is_not_a_number_is_refused():
    """Нечисловой номер отвергается, а не доезжает до колонки молча.

    Слот ловит это и отвечает окну «Неверные поля»: молча положенный ноль
    привязал бы HR к чужой учётной записи.
    """
    with pytest.raises(ValueError):
        read_new_hr_fields({"telegram_user_id": "не число"})


async def test_the_read_fields_reach_the_hr_row_as_they_were_typed(session):
    """Прочитанные поля доезжают до строки HR теми же, что ввёл человек.

    Слоты зовут заведение развёрткой словаря, то есть имена ключей здесь —
    подпись чужого вызова: переименуй любой, и форма упадёт у пользователя,
    ничего не записав.
    """
    hr = await create_hr(
        session,
        **read_new_hr_fields(
            {
                "name": "Иван",
                "telegram_username": "@ivanov",
                "telegram_user_id": "77",
                "notes": "звонил в среду",
            }
        ),
    )

    assert (hr.name, hr.telegram_username, hr.telegram_user_id, hr.notes) == (
        "Иван",
        "ivanov",
        77,
        "звонил в среду",
    )


async def test_the_read_fields_reach_the_company_row_as_they_were_typed(session):
    """То же для компании: развёртка словаря бьётся с заведением строки."""
    company = await create_company(
        session,
        **read_new_company_fields(
            {
                "name": "Контур",
                "website": "https://kontur.ru",
                "aliases": "Кон, ООО Контур",
                "notes": "два офиса",
            }
        ),
    )

    assert (company.name, company.website, company.aliases, company.notes) == (
        "Контур",
        "https://kontur.ru",
        ["Кон", "ООО Контур"],
        "два офиса",
    )


def test_a_trailing_comma_does_not_add_an_empty_spelling():
    """Хвостовая запятая не добавляет пустого написания.

    Пустая строка в перечне написаний совпала бы с чем угодно при сведении
    компаний и склеила бы разные записи в одну.
    """
    fields = read_new_company_fields({"name": "Контур", "aliases": "Кон,"})

    assert fields["aliases"] == ["Кон"]


def test_company_spellings_arrive_both_as_a_line_and_as_a_list():
    """Прозвища читаются и строкой через запятую, и готовым списком.

    Одна форма отдаёт их строкой, другая — списком, и список, прочитанный
    как строка, лёг бы в колонку одним куском «['ООО Контур']», после чего
    ни одно написание не нашлось бы при сведении компаний.
    """
    from_line = read_new_company_fields({"name": "Контур", "aliases": " Кон , ООО Контур "})
    from_list = read_new_company_fields({"name": "Контур", "aliases": [" Кон ", "ООО Контур"]})

    assert from_line["aliases"] == ["Кон", "ООО Контур"]
    assert from_list["aliases"] == ["Кон", "ООО Контур"]


def test_a_company_without_spellings_gets_an_empty_list():
    """Незаполненные прозвища — пустой перечень, а не отсутствие.

    Колонка хранит список; `None` в ней означал бы «не знаем», и обход
    написаний при сведении компаний спотыкался бы о неё.
    """
    assert read_new_company_fields({"name": "Контур"})["aliases"] == []
    assert read_new_company_fields({"name": "Контур", "aliases": 5})["aliases"] == []


def test_a_company_name_of_spaces_is_read_as_no_name():
    """Название из одних пробелов — то же, что незаполненное.

    Слот отвечает на это «Название обязательно»: пустое имя не найти ни
    поиском, ни сведением, а в чёрный список оно пошло бы пустой строкой.
    """
    assert read_new_company_fields({"name": "   "})["name"] == ""
