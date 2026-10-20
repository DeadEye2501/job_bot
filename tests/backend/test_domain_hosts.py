"""Адрес, разобранный на хост и остаток: по хосту сравнивают сайты, по остатку —
страницы одного сайта."""

import pytest

from types import SimpleNamespace

from backend.domain.hosts import (
    AddressParts,
    address_parts,
    host_owns,
    link_kind,
    page_owner,
    site_label,
    source_key,
    vacancy_address_key,
)

_LEVER_UUID = "0f6a9c3e-1b2d-4e5f-8a7b-9c0d1e2f3a4b"


@pytest.mark.parametrize(("url", "kind"), [
    pytest.param("https://telegra.ph/QA-08-21", "article", id="статья"),
    pytest.param("telegra.ph/QA-08-21", "article", id="статья без схемы"),
    pytest.param("HTTPS://Telegra.ph/QA-08-21.", "article", id="статья заглавными и с точкой"),
    pytest.param("https://t.me/+AbCdEf123", "channel", id="приглашение"),
    pytest.param("https://t.me/joinchat/AbCdEf123", "channel", id="старое приглашение"),
    pytest.param("https://t.me/pyjobs?start=1", "channel", id="канал с хвостом"),
    pytest.param("https://t.me/pyjobs/15", "post", id="пост"),
    pytest.param("https://t.me/s/pyjobs/15", "post", id="пост веб-просмотра"),
    pytest.param("https://t.me/c/12345/15", "post", id="пост закрытого"),
    pytest.param("https://t.me/pyjobs/3/15", "post", id="пост темы форума"),
    pytest.param("https://t.me/c/12345/3/15", "post", id="пост темы закрытого"),
    pytest.param("https://t.me/pyjobs", "channel", id="канал"),
    pytest.param("t.me/pyjobs/", "channel", id="канал без схемы"),
    pytest.param("https://t.me/iv?url=https://site.test/a&rhash=1", "telegram", id="мгновенный просмотр"),
    pytest.param("https://telegra.ph/", "telegram", id="корень Telegraph"),
    pytest.param("https://hh.ru/vacancy/123", "page", id="площадка"),
    pytest.param("https://company.test/careers/qa", "page", id="сайт компании"),
])
def test_a_link_is_sorted_by_where_it_leads(url, kind):
    """Род ссылки решает одно правило по самому адресу: от него зависит, кто её
    читает — склейка статей, Telegram или агент."""
    assert link_kind(url) == kind


def test_a_page_belongs_to_the_site_that_owns_its_host():
    """Поддомен — та же площадка; «Поиск по сети» без хоста не владеет ничем."""
    hh, web = SimpleNamespace(host="hh.ru"), SimpleNamespace(host=None)

    assert page_owner("https://spb.hh.ru/vacancy/1", [web, hh]) is hh
    assert page_owner("https://nothh.ru/vacancy/1", [web, hh]) is None


@pytest.mark.parametrize(("url", "key"), [
    pytest.param("https://hh.ru/vacancy/123", "hh:123", id="hh"),
    pytest.param("http://spb.hh.ru/vacancy/123/?utm_source=tg&from=main", "hh:123",
                 id="hh с поддоменом, метками, http и косой"),
    pytest.param("https://career.habr.com/vacancies/1000150", "habr:1000150", id="Habr Career"),
    pytest.param("https://geekjob.ru/vacancy/6AD0B496115D80A7CD04E2B6", "geekjob:6ad0b496115d80a7cd04e2b6",
                 id="GeekJob"),
    pytest.param("https://getmatch.ru/vacancies/24081-python-developer", "getmatch:24081", id="getmatch"),
    pytest.param("https://www.linkedin.com/jobs/view/4012345678/", "linkedin:4012345678", id="LinkedIn"),
    pytest.param("https://www.linkedin.com/jobs/search/?currentJobId=4012345678&keywords=python",
                 "linkedin:4012345678", id="LinkedIn в выдаче"),
    pytest.param("https://job-boards.greenhouse.io/acme/jobs/8240119", "greenhouse:8240119", id="Greenhouse"),
    pytest.param("https://boards.greenhouse.io/acme/jobs/8240119?gh_src=board", "greenhouse:8240119",
                 id="Greenhouse со старого адреса"),
    pytest.param(f"https://jobs.lever.co/acme/{_LEVER_UUID.upper()}/apply", f"lever:{_LEVER_UUID}",
                 id="Lever с хвостом и в другом регистре"),
    pytest.param(f"https://jobs.ashbyhq.com/acme/{_LEVER_UUID}", f"ashby:{_LEVER_UUID}", id="Ashby"),
    pytest.param("https://acme.test/careers?gh_jid=8240119", "acme.test:gh:8240119",
                 id="Greenhouse на сайте компании"),
    pytest.param("https://t.me/s/Jobs_Channel/15", "tg:jobs_channel:15", id="пост Telegram"),
    pytest.param("https://t.me/c/1234567/15", "tg:1234567:15", id="пост закрытого канала"),
])
def test_a_vacancy_page_on_a_known_platform_is_keyed_by_its_number(url, key):
    """Один адрес такого вида — одна страница — одна вакансия: метки прихода,
    поддомен, схема и косая в конце номера не меняют."""
    assert vacancy_address_key(url) == key


@pytest.mark.parametrize("url", [
    pytest.param("https://acme.test/careers/python", id="сайт компании"),
    pytest.param("https://telegra.ph/Senior-QA-08-21", id="статья Telegraph"),
    pytest.param("https://hh.ru/employer/1455", id="страница площадки без вакансии"),
    pytest.param("https://t.me/jobs_channel", id="канал без поста"),
    pytest.param("hr@acme.test", id="почта"),
])
def test_an_address_without_a_vacancy_number_has_no_key(url):
    """Что однозначно не определить, того и не сравнивают: ложный повтор хуже
    пропущенного."""
    assert vacancy_address_key(url) is None


def test_two_numbers_on_one_platform_are_two_keys():
    assert vacancy_address_key("https://hh.ru/vacancy/1") != vacancy_address_key("https://hh.ru/vacancy/2")


def test_the_european_greenhouse_is_a_platform_of_its_own():
    """Общий ли у европейского экземпляра счёт номеров с основным, по адресу
    не сказать: один номер на двух экземплярах — две вакансии."""
    us = vacancy_address_key("https://job-boards.greenhouse.io/acme/jobs/8240119")
    eu = vacancy_address_key("https://job-boards.eu.greenhouse.io/acme/jobs/8240119")
    assert us != eu


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


def test_a_parameter_named_as_an_id_keeps_pages_apart():
    assert source_key("https://company.test/careers?gh_jid=abc&lang=en", None) == (
        "company.test/careers?gh_jid=abc"
    )


def test_a_numeric_parameter_keeps_pages_apart():
    assert source_key("https://site.test/job?vacancy=123&lang=en", "site.test") == (
        "job?vacancy=123"
    )


def test_a_number_in_a_parameter_keeps_its_case():
    assert source_key("https://Company.test/Careers?job_id=AbC", None) == (
        "company.test/careers?job_id=AbC"
    )


def test_click_session_and_arrival_marks_are_not_part_of_the_number():
    url = ("https://site.test/vacancy?job_id=7&gclid=a1&yclid=9&msclkid=b"
           "&sid=c&session_id=5&phpsessid=6&utm_id=4&from=12")
    assert source_key(url, "site.test") == "vacancy?job_id=7"


def test_a_parameter_that_merely_contains_sess_is_kept():
    assert source_key("https://site.test/test?assessment_id=7", "site.test") == "test?assessment_id=7"


def test_parameter_order_does_not_change_the_number():
    assert source_key("https://site.test/job?b_id=2&a_id=1", "site.test") == "job?a_id=1&b_id=2"


def test_an_address_without_a_path_has_no_number():
    assert source_key("https://site.test/", "site.test") is None


@pytest.mark.parametrize(("host", "label"), [
    ("example.com", "example"), ("jobs.example.com", "example"), ("example.am", "example"),
    ("jobs.example.co.uk", "example"), ("hr.ex.ru", "ex"), ("localhost", "localhost"),
])
def test_the_site_label_drops_the_zone_and_subdomains(host, label):
    assert site_label(host) == label
