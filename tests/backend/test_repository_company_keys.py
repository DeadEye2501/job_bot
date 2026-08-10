"""Следствия приведения имени и сайта компании к сравнимому виду.

Одну компанию объявления называют по-разному: «ПАО Сбербанк», «Сбербанк»,
«Sberbank», «ООО "Сбер"». Чтобы понять, что это одно и то же, имя приводят к
общему виду, а сайт сводят к голому хосту. Сайты-агрегаторы при этом
приравниваются к отсутствию сайта: ссылка на канал в мессенджере о компании
не говорит ничего, а склеила бы по общему хосту всех подряд.
"""

import pytest

from backend.repository.companies_keys import (
    _is_aggregator_host,
    _translit_cyr_to_latin,
    hosts_compatible,
    normalize_company_name,
    normalize_host,
    real_corporate_website,
    signal_host,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        pytest.param("МТС", "mts", id="заглавная кириллица опускается"),
        pytest.param("Щи", "shchi", id="многобуквенные соответствия"),
        pytest.param("Подъезд", "podezd", id="твёрдый знак пропадает"),
        pytest.param("Ёлка", "elka", id="ё сводится к е"),
        pytest.param("Latin", "latin", id="латиница только опускается"),
        pytest.param("МТС-2024", "mts-2024", id="цифры и знаки не трогаются"),
    ],
)
def test_cyrillic_is_transliterated_letter_by_letter(raw, expected):
    """Кириллица переводится в латиницу побуквенно, с опусканием регистра."""
    assert _translit_cyr_to_latin(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        pytest.param(None, "", id="ничего"),
        pytest.param("   ", "", id="одни пробелы"),
        pytest.param("Сбербанк", "sberbank", id="кириллица"),
        pytest.param("ПАО Сбербанк", "sberbank", id="юридическая форма впереди"),
        pytest.param("Sberbank LLC", "sberbank", id="юридическая форма сзади"),
        pytest.param("Acme Ltd.", "acme", id="форма с точкой"),
        pytest.param('ООО "Сбер"', "sber", id="кавычки по краям слова"),
        pytest.param('Сбер"банк', "sberbank", id="кавычка внутри слова"),
        pytest.param("«Сбер»банк", "sberbank", id="ёлочки внутри слова"),
        pytest.param("Acme   Corp   Inc", "acme", id="лишние пробелы"),
        pytest.param("Acme & Co!", "acme co", id="знаки заменяются пробелом"),
        pytest.param("Sberbank", "sberbank", id="уже нормальное"),
    ],
)
def test_a_company_name_is_reduced_to_its_comparable_form(raw, expected):
    """Имя сводится к сравнимому виду: без регистра, кавычек и юридической формы.

    Кавычка проверяется внутри слова, а не только по краям: по краям её
    убирает и последний шаг, заменяющий всё нецифробуквенное пробелом, и
    отдельное вырезание кавычек было бы недоказуемым. Внутри слова разница
    видна — вырезание даёт «sberbank», замена на пробел дала бы «sber bank».
    """
    assert normalize_company_name(raw) == expected


def test_two_spellings_of_one_company_reduce_to_the_same_form():
    """Разные написания одной компании сходятся в одну форму.

    Это и есть предмет приведения: сравнивать «ПАО Сбербанк» с «Sberbank LLC»
    буква в букву бесполезно.
    """
    assert normalize_company_name("ПАО Сбербанк") == normalize_company_name(
        'ООО "Sberbank"'
    )


def test_a_legal_form_inside_a_word_is_not_cut():
    """Юридическая форма внутри слова не вырезается.

    Правило ищет отдельное слово: иначе «Ooolala» превратилось бы в «lala».
    """
    assert normalize_company_name("Ooolala") == "ooolala"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        pytest.param(None, "", id="ничего"),
        pytest.param("", "", id="пустая строка"),
        pytest.param("acme.com", "acme.com", id="голый хост"),
        pytest.param("https://acme.com", "acme.com", id="со схемой"),
        pytest.param("HTTPS://ACME.COM", "acme.com", id="в верхнем регистре"),
        pytest.param("ftp://acme.com", "acme.com", id="другая схема"),
        pytest.param("//acme.com", "acme.com", id="без схемы, с косыми"),
        pytest.param("www.acme.com", "acme.com", id="с www"),
        pytest.param("acme.com:8443", "acme.com", id="с портом"),
        pytest.param("acme.com/jobs/1", "acme.com", id="с путём"),
        pytest.param("acme.com#top", "acme.com", id="с якорем"),
        pytest.param("acme.com.", "acme.com", id="с завершающей точкой"),
        pytest.param("pay.acme.com", "pay.acme.com", id="поддомен сохраняется"),
    ],
)
def test_a_website_is_reduced_to_its_bare_host(raw, expected):
    """Сайт сводится к голому хосту — без схемы, порта, пути и хвостов.

    Поддомен сохраняется нарочно: `pay.acme.com` и `acme.com` — разные
    хозяйства внутри одной группы, и склеивать их по общему домену нельзя.
    """
    assert normalize_host(raw) == expected


def test_a_query_is_cut_even_without_a_path():
    """Запрос срезается и тогда, когда пути перед ним нет.

    Без этого «sber.ru?utm=foo» стал бы хостом целиком и не совпал бы ни с
    чем.
    """
    assert normalize_host("https://sber.ru?utm=foo") == "sber.ru"


@pytest.mark.parametrize(
    ("host", "expected"),
    [
        pytest.param("", False, id="пустой хост"),
        pytest.param("acme.com", False, id="обычный сайт"),
        pytest.param("t.me", True, id="мессенджер"),
        pytest.param("hh.ru", True, id="площадка вакансий"),
        pytest.param("careers.hh.ru", True, id="поддомен площадки"),
        pytest.param("m.linkedin.com", True, id="мобильный поддомен соцсети"),
        pytest.param("nothh.ru", False, id="хост, лишь оканчивающийся так же"),
        pytest.param("hh.ru.acme.com", False, id="имя площадки внутри чужого хоста"),
    ],
)
def test_an_aggregator_host_is_recognised_including_its_subdomains(host, expected):
    """Агрегатор опознаётся вместе с поддоменами, но не по случайному сходству."""
    assert _is_aggregator_host(host) is expected


def test_an_aggregator_host_carries_no_signal_about_a_company():
    """Хост агрегатора приравнивается к отсутствию сайта.

    Иначе жёсткое правило «разные сайты — разные компании» ветировало бы
    сравнение пары «Acme с acme.com» и «Acme со ссылкой на канал», хотя это
    одна компания и решать должно имя.
    """
    assert signal_host("acme.com") == "acme.com"
    assert signal_host("t.me") == ""
    assert signal_host("") == ""


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        pytest.param(None, None, id="ничего"),
        pytest.param("   ", None, id="одни пробелы"),
        pytest.param(
            "https://acme.com/about", "https://acme.com/about", id="корпоративный"
        ),
        pytest.param("https://t.me/acme", None, id="ссылка на канал"),
        pytest.param("hh.ru/employer/1", None, id="страница на площадке"),
    ],
)
def test_only_a_corporate_website_is_worth_storing(raw, expected):
    """В карточку компании попадает только настоящий корпоративный сайт.

    Ссылка на канал, показанная пользователю как «официальный сайт», врёт, и
    будущие сравнения по хосту из неё ничего не извлекут. Возвращается
    исходная строка, а не голый хост: в базе хранят ссылку, по которой можно
    перейти.
    """
    assert real_corporate_website(raw) == expected


@pytest.mark.parametrize(
    ("a", "b", "expected"),
    [
        pytest.param("acme.com", "acme.com", True, id="одинаковые"),
        pytest.param("acme.com", "other.com", False, id="разные"),
        pytest.param("acme.com", "", True, id="второй не указан"),
        pytest.param("", "acme.com", True, id="первый не указан"),
        pytest.param("pay.acme.com", "acme.com", False, id="поддомен против домена"),
    ],
)
def test_different_known_hosts_mean_different_companies(a, b, expected):
    """Разные известные хосты — разные компании; неизвестный сравнению не мешает."""
    assert hosts_compatible(a, b) is expected
