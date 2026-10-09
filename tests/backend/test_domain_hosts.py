"""Адрес, разобранный на хост и остаток: по хосту сравнивают сайты, по остатку —
страницы одного сайта."""

from backend.domain.hosts import AddressParts, address_parts


def test_an_address_splits_into_its_host_and_the_rest():
    assert address_parts("HTTPS://www.Site.test:443/a/b/?x=1#top") == AddressParts(
        "site.test", "a/b", "x=1", "top"
    )


def test_an_address_without_a_scheme_splits_the_same_way():
    assert address_parts("site.test/a") == AddressParts("site.test", "a", "", "")


def test_a_stray_bracket_does_not_break_the_parse():
    """Контакт с непарной скобкой — текст, а не повод уронить запись разбора.

    Скобка стоит до первой косой: только в хосте `urlsplit` принимает её за
    начало адреса IPv6 и бросает.
    """
    assert address_parts("site.test[1/form") == AddressParts("site.test[1", "form", "", "")
