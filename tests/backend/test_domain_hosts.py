"""Адрес, разобранный на хост и остаток: по хосту сравнивают сайты, по остатку —
страницы одного сайта."""

import pytest

from backend.domain.hosts import AddressParts, address_parts, host_owns, source_key


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


@pytest.mark.parametrize(("link_host", "owned"), [
    ("site.test", True), ("spb.site.test", True), ("notsite.test", False),
])
def test_a_subdomain_belongs_to_its_site(link_host, owned):
    assert host_owns("site.test", link_host) is owned


def test_an_aggregator_number_is_the_path_without_parameters():
    assert source_key("https://site.test/vacancy/123456?from=main", "site.test") == "vacancy/123456"


def test_a_subdomain_page_is_the_same_aggregator():
    assert source_key("https://spb.site.test/vacancy/7/", "site.test") == "vacancy/7"


def test_a_page_with_a_port_is_the_same_aggregator():
    assert source_key("https://site.test:443/vacancy/7", "site.test") == "vacancy/7"


def test_a_page_of_another_site_has_no_number_on_this_aggregator():
    assert source_key("https://other.test/vacancy/7", "site.test") is None


def test_a_web_page_is_known_by_host_and_path():
    assert source_key("https://www.company.test/careers/dev/?utm=1", None) == (
        "company.test/careers/dev"
    )


def test_an_address_without_a_path_has_no_number():
    assert source_key("https://site.test/", "site.test") is None
