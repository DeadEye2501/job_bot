"""Нормальная форма контакта вакансии: по ней два написания одного контакта
признаются одним."""

import pytest

from backend.domain.contact_keys import contact_key


@pytest.mark.parametrize(("written", "key"), [
    ("HR@Company.ru", "hr@company.ru"),
    ("mailto:HR@Company.ru", "hr@company.ru"),
    ("  hr@company.ru  ", "hr@company.ru"),
])
def test_an_address_is_compared_without_case_and_mailto(written, key):
    assert contact_key(written) == key


@pytest.mark.parametrize("written", [
    "https://hh.ru/vacancy/123?from=main",
    "http://www.hh.ru/vacancy/123/",
    "hh.ru/vacancy/123?utm_source=tg&utm_medium=post",
    "https://hh.ru/vacancy/123?gclid=a1&yclid=9",
    "HTTPS://HH.RU/vacancy/123",
    "https://hh.ru:443/vacancy/123",
])
def test_one_link_written_differently_gets_one_key(written):
    """Хост приводится тем же правилом, что сайт компании: порт и `www.` не в счёт."""
    assert contact_key(written) == "hh.ru/vacancy/123"


def test_a_meaningful_parameter_of_a_link_is_kept():
    """Отсекаются только метки прихода. Номер формы в параметре — часть адреса."""
    assert contact_key("https://forms.site/f?id=7&utm_source=x") == "forms.site/f?id=7"


@pytest.mark.parametrize("written", [
    "+7 (999) 123-45-67",
    "+7 999 123 45 67",
    "+7-999-123-45-67",
    "tel:+79991234567",
])
def test_a_phone_keeps_only_its_digits(written):
    assert contact_key(written) == "79991234567"


def test_a_label_before_a_colon_does_not_merge_two_contacts():
    """Подпись «Почта:» — не хост: два адреса за ней остаются двумя контактами."""
    assert contact_key("Почта: a@x.ru") != contact_key("Почта: b@x.ru")


def test_plain_words_are_compared_as_written():
    """Контакт без адреса сравнивается текстом, без лишних пробелов и регистра."""
    assert contact_key("  Пишите  В комментарии ") == "пишите в комментарии"
