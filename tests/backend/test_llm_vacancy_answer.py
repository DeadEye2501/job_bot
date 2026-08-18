"""Следствия разбора ответа модели в разобранную вакансию.

Заголовок обязателен: без него объявление нечем показать в списке, и вся
вакансия отбрасывается. Всё прочее необязательно, и пустое значение везде
сводится к отсутствию — экран отличает «поля нет» от «поле есть, но пусто».

Отдельный узел — ссылка, прилепленная моделью к названию компании. Её
вырезают из названия и, если поле сайта пусто, кладут туда: иначе название
«Контур https://kontur.ru/» не совпадёт ни с одной записью в базе.
"""

import json

import pytest

from backend.llm.vacancy import _parse_vacancy_json
from tests.fakes.llm import parsed_vacancy_answer


def _answer(**fields) -> str:
    """Ответ модели строкой: разбор читает её до всякого клиента."""
    return json.dumps(parsed_vacancy_answer(**fields), ensure_ascii=False)


def test_an_answer_without_an_object_is_not_parsed():
    """Ответ без объекта разбору не поддаётся."""
    assert _parse_vacancy_json("совсем не то, что просили") is None


def test_a_broken_object_is_not_parsed():
    """Объект с поломанным содержимым разбору не поддаётся."""
    assert _parse_vacancy_json('{"title": "Разработчик",}') is None


@pytest.mark.parametrize(
    "raw_title",
    [
        pytest.param(None, id="заголовка нет"),
        pytest.param("", id="пустой заголовок"),
        pytest.param("   ", id="одни пробелы"),
        pytest.param(42, id="не строка"),
    ],
)
def test_a_vacancy_without_a_title_is_dropped(raw_title):
    """Вакансия без заголовка отбрасывается целиком."""
    answer = json.dumps({"title": raw_title, "salary": "$3000"}, ensure_ascii=False)

    assert _parse_vacancy_json(answer) is None


def test_a_title_is_trimmed():
    """Заголовок обрезается по краям."""
    parsed = _parse_vacancy_json(_answer(title="  Python-разработчик  "))

    assert parsed.title == "Python-разработчик"


@pytest.mark.parametrize(
    "field",
    [
        "description",
        "company_name",
        "company_website",
        "hr_contact",
        "other_contact",
        "salary",
        "location",
    ],
)
def test_an_empty_text_field_becomes_absence(field):
    """Пустое текстовое поле становится отсутствием, а не пустой строкой."""
    parsed = _parse_vacancy_json(_answer(**{field: "   "}))

    assert getattr(parsed, field) is None


@pytest.mark.parametrize(
    "field",
    ["description", "company_name", "salary", "location"],
)
def test_a_non_string_field_becomes_absence(field):
    """Поле не-строкой становится отсутствием, а не роняет разбор."""
    parsed = _parse_vacancy_json(_answer(**{field: 42}))

    assert getattr(parsed, field) is None


def test_a_text_field_is_trimmed():
    """Непустое текстовое поле обрезается по краям."""
    parsed = _parse_vacancy_json(_answer(salary="  $3000  "))

    assert parsed.salary == "$3000"


@pytest.mark.parametrize(
    "raw_contact",
    [
        pytest.param("Откликнуться", id="подпись ссылки"),
        pytest.param("Подробнее", id="подпись ссылки словом"),
        pytest.param("пишите в комментарии под постом", id="указание словами"),
        pytest.param("Apply here", id="подпись по-английски"),
    ],
)
def test_a_way_to_apply_without_an_address_is_dropped(raw_contact):
    """Способ отклика без адреса не сохраняется.

    Пост часто кончается ссылкой-словом, а до модели доезжает только её
    подпись — сам адрес остаётся в разметке сообщения. Записанная как есть,
    она даёт в заметке вакансии «Контакты: Откликнуться»: строка есть, а
    откликаться по ней некуда.
    """
    parsed = _parse_vacancy_json(_answer(other_contact=raw_contact))

    assert parsed.other_contact is None


@pytest.mark.parametrize(
    "raw_contact",
    [
        pytest.param("jobs@acme.com", id="почта"),
        pytest.param("https://forms.gle/abc123", id="ссылка"),
        pytest.param("hh.ru/vacancy/12345", id="домен"),
        pytest.param("резюме на careers.acme.com/apply", id="адрес внутри фразы"),
        pytest.param("звонить +7 999 123-45-67", id="телефон"),
    ],
)
def test_a_way_to_apply_with_an_address_is_kept(raw_contact):
    """Способ отклика с адресом сохраняется дословно."""
    parsed = _parse_vacancy_json(_answer(other_contact=raw_contact))

    assert parsed.other_contact == raw_contact


@pytest.mark.parametrize(
    ("raw_contact", "expected"),
    [
        pytest.param(
            "контакты в описании (https://acme.test/jobs)",
            "https://acme.test/jobs",
            id="подпись со своим адресом",
        ),
        pytest.param(
            "Откликнуться (https://forms.gle/abc)",
            "https://forms.gle/abc",
            id="подпись кнопки со своим адресом",
        ),
    ],
)
def test_an_address_written_after_its_label_is_left_alone_of_the_label(
    raw_contact, expected
):
    """От подписи с адресом в скобках остаётся один адрес.

    Адрес спрятанной ссылки дописывается за её подписью при чтении поста
    (`extract_post_text`), и модель приносит их вместе. В заметке вакансии
    нужен способ отклика, а не пересказ поста: «Контакты: контакты в описании
    (https://…)» читается как сбой, а не как адрес.
    """
    parsed = _parse_vacancy_json(_answer(other_contact=raw_contact))

    assert parsed.other_contact == expected


def test_an_overlong_description_is_cut_with_an_ellipsis():
    """Слишком длинное описание обрезается и помечается многоточием.

    Модель нарушает «три-шесть предложений» и присылает килобайты. Экран
    всё равно показывает три строки, но в базу такое складывать незачем.
    """
    parsed = _parse_vacancy_json(_answer(description="а" * 2000))

    assert len(parsed.description) == 1501
    assert parsed.description.endswith("…")


def test_a_description_at_the_limit_is_left_whole():
    """Описание ровно по пределу не трогают."""
    parsed = _parse_vacancy_json(_answer(description="а" * 1500))

    assert parsed.description == "а" * 1500


@pytest.mark.parametrize(
    ("field", "value", "expected"),
    [
        pytest.param("grade", "SENIOR", "senior", id="уровень приводится"),
        pytest.param("grade", "architect", None, id="уровень не из набора"),
        pytest.param("remote", "  Remote ", "remote", id="удалённость приводится"),
        pytest.param("remote", "anywhere", None, id="удалённость не из набора"),
    ],
)
def test_a_value_from_a_set_is_checked_against_it(field, value, expected):
    """Уровень и удалённость проверяются по своему набору значений."""
    parsed = _parse_vacancy_json(_answer(**{field: value}))

    assert getattr(parsed, field) == expected


def test_the_two_stack_lists_are_read_separately():
    """Обязательный и желательный стеки читаются порознь."""
    parsed = _parse_vacancy_json(
        _answer(stack_required=["python 3.13"], stack_preferred=["docker"])
    )

    assert parsed.stack_required == ["Python"]
    assert parsed.stack_preferred == ["Docker"]


def test_an_old_single_stack_falls_back_to_the_required_one():
    """Старый одиночный стек целиком считается обязательным.

    Так отвечают устаревшие снимки модели, не знающие о разделении. Считать
    его желательным было бы опаснее: несовпавший обязательный отнимает
    балл, а несовпавший желательный не отнимает ничего.
    """
    parsed = _parse_vacancy_json(_answer(stack=["Python", "Docker"]))

    assert parsed.stack_required == ["Python", "Docker"]
    assert parsed.stack_preferred == []


def test_a_new_empty_stack_does_not_fall_back_to_the_old_field():
    """Присланный пустым новый стек к старому полю не откатывается.

    Пустой список — это ответ «стека нет», и подмена его старым полем
    вернула бы то, чего модель не говорила.
    """
    parsed = _parse_vacancy_json(
        _answer(stack_required=[], stack=["Python"])
    )

    assert parsed.stack_required == []


def test_a_link_glued_to_the_company_name_moves_to_the_website():
    """Ссылка, прилепленная к названию компании, переезжает в поле сайта."""
    parsed = _parse_vacancy_json(_answer(company_name="Контур https://kontur.ru/"))

    assert parsed.company_name == "Контур"
    assert parsed.company_website == "https://kontur.ru/"


def test_a_bare_domain_glued_to_the_name_moves_too():
    """Голый домен без схемы переезжает так же."""
    parsed = _parse_vacancy_json(_answer(company_name="Контур www.kontur.ru"))

    assert parsed.company_name == "Контур"
    assert parsed.company_website == "www.kontur.ru"


def test_a_separator_between_the_name_and_the_link_is_removed():
    """Разделитель между названием и ссылкой убирается вместе с ней."""
    parsed = _parse_vacancy_json(_answer(company_name="Контур — kontur.ru"))

    assert parsed.company_name == "Контур"


def test_an_existing_website_is_not_overwritten_by_the_glued_link():
    """Уже присланный сайт прилепленной ссылкой не затирается."""
    parsed = _parse_vacancy_json(
        _answer(
            company_name="Контур https://kontur.dev",
            company_website="https://kontur.ru",
        )
    )

    assert parsed.company_name == "Контур"
    assert parsed.company_website == "https://kontur.ru"


def test_a_name_that_is_only_a_link_is_left_alone():
    """Название, состоящее из одной ссылки, не опустошается.

    Иначе у вакансии не осталось бы названия компании вовсе, а так хотя бы
    видно, откуда она.
    """
    parsed = _parse_vacancy_json(_answer(company_name="https://kontur.ru"))

    assert parsed.company_name == "https://kontur.ru"
    assert parsed.company_website is None


def test_a_company_name_with_its_address_in_brackets_is_split_clean():
    """Имя компании и адрес в скобках разнимаются без остатка скобок.

    Такую пару собирает чтение поста, дописывая адрес спрятанной ссылки за
    её подписью, а модель приносит её целиком в имя компании. Скобка,
    оставшаяся в имени, ломает сведение компаний, а скобка в адресе — кнопку
    «открыть сайт».
    """
    parsed = _parse_vacancy_json(
        _answer(company_name="Acme (https://acme.com)", company_website=None)
    )

    assert parsed.company_name == "Acme"
    assert parsed.company_website == "https://acme.com"


def test_an_hr_contact_written_after_its_label_loses_the_label():
    """От имени со ссылкой на человека в скобках остаётся один адрес.

    «писать Анне (https://t.me/anna_hr)» приходит от модели целиком, а по
    такой строке ни ник не разобрать, ни собеседника не завести.
    """
    parsed = _parse_vacancy_json(
        _answer(hr_contact="Анне (https://t.me/anna_hr)")
    )

    assert parsed.hr_contact == "https://t.me/anna_hr"
