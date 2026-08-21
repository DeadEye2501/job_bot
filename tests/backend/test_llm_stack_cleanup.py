"""Следствия приведения названий технологий к единому виду.

Модель нарушает инструкцию «без версий» и присылает «Python 3.13», а регистр
пишет как придётся. Хвост с версией срезается, а полностью строчное слово
получает заглавную — но только полностью строчное: у «SQLAlchemy», «iOS» и
«gRPC» вид канонический, и трогать его нельзя.

Имена, у которых цифра своя — «Web3», «S3», «HTML5», — от срезания защищены
поимённым списком: формой их от версии не отличить.

Приведённые названия отсеиваются от повторов тем же ключом, что и навыки
анкеты: иначе одна технология под двумя написаниями дала бы вакансии двойной
балл.
"""

import pytest

from backend.llm.skills import _capitalize_skill, clean_stack_items, _strip_version


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        pytest.param("Python 3.13", "Python", id="версия через пробел"),
        pytest.param("Python3.13", "Python", id="версия без пробела"),
        pytest.param("Java 17", "Java", id="целая версия"),
        pytest.param("PostgreSQL 14.5", "PostgreSQL", id="версия из двух частей"),
        pytest.param("Node.js 20", "Node.js", id="точка в самом имени"),
        pytest.param("Kafka v2.5", "Kafka", id="версия с буквой v"),
        pytest.param("Python", "Python", id="версии нет"),
        pytest.param("Python3", "Python", id="целая версия приклеена"),
        pytest.param("Java17", "Java", id="двузначная версия приклеена"),
        pytest.param("C++11", "C++", id="версия стандарта приклеена"),
        pytest.param("Go 1.22+", "Go", id="двухбуквенное имя с версией"),
        pytest.param("R 4.3", "R", id="однобуквенное имя с версией"),
        pytest.param("Log4j-2.17", "Log4j", id="версия через дефис"),
        pytest.param("Kafka V2.5", "Kafka", id="версия с заглавной V"),
        pytest.param("2024", "2024", id="одни цифры, срезать нечего"),
        pytest.param("1.0 2.0", "1.0 2.0", id="после среза не осталось букв"),
    ],
)
def test_a_version_tail_is_cut_unless_it_is_part_of_the_name(raw, expected):
    """Хвост с версией срезается — в том числе у самых коротких имён.

    Раньше это решала длина остатка: меньше трёх знаков — не срезать. Порог
    путал «цифра входит в имя» с «имя короткое» и ошибался в обе стороны.
    """
    assert _strip_version(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        pytest.param("S3", id="хранилище"),
        pytest.param("C4", id="схема описания"),
        pytest.param("Web3", id="про блокчейн"),
        pytest.param("HTML5", id="разметка"),
        pytest.param("OAuth2", id="протокол доступа"),
        pytest.param("IPv6", id="протокол сети"),
        pytest.param("SHA256", id="хеш"),
        pytest.param("Base64", id="кодирование"),
        pytest.param("UTF-8", id="кодировка через дефис"),
        pytest.param("x86_64", id="разрядность через подчёркивание"),
        pytest.param("Bitrix24", id="платформа с цифрой в имени"),
        pytest.param("Битрикс24", id="она же по-русски"),
        pytest.param("SHA-256", id="хеш через дефис"),
    ],
)
def test_a_name_that_ends_in_a_digit_keeps_it(raw):
    """Имя, у которого цифра своя, сохраняется целиком.

    Формой такие от версии не отличить: «Web3» и «Java17» устроены
    одинаково, и любое правило по виду цифры ошибается на одном из них.
    Поэтому они перечислены поимённо. Ошибка в эту сторону дешевле: лишний
    тег «Web» просто не найдётся в анкете, а срезанная цифра у «Python3»
    ломает сверку и мешает схлопывать повторы.
    """
    assert _strip_version(raw) == raw


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        pytest.param("pytest", "Pytest", id="строчное слово"),
        pytest.param("SQLAlchemy", "SQLAlchemy", id="верблюжий регистр"),
        pytest.param("PostgreSQL", "PostgreSQL", id="заглавные внутри"),
        pytest.param("iOS", "iOS", id="заглавные не в начале"),
        pytest.param("gRPC", "gRPC", id="строчная первая, заглавные дальше"),
        pytest.param(".NET", ".NET", id="имя со знака"),
        pytest.param("c++", "C++", id="строчное со знаками"),
        pytest.param(
            "микросервисная архитектура",
            "Микросервисная Архитектура",
            id="два строчных слова",
        ),
        pytest.param("REST API", "REST API", id="два заглавных слова"),
        pytest.param("", "", id="пусто"),
    ],
)
def test_only_a_fully_lowercase_word_gets_a_capital(raw, expected):
    """Заглавную получает только полностью строчное слово.

    Слово, где заглавная уже есть, остаётся как есть: так сохраняется
    канонический вид названий вроде «SQLAlchemy» и «iOS».
    """
    assert _capitalize_skill(raw) == expected


def test_the_two_cleanups_are_applied_together():
    """К каждому названию применяются оба приведения подряд.

    Сперва срезается версия, потом поднимается регистр: в обратном порядке
    «fastapi 0.110» осталось бы с версией, потому что поднимать было бы
    нечего в цифрах.
    """
    assert clean_stack_items(["fastapi 0.110"], set()) == ["Fastapi"]


def test_a_repeat_is_kept_once():
    """Повтор внутри списка остаётся один раз, без учёта регистра."""
    assert clean_stack_items(["Python", "python", "PYTHON"], set()) == ["Python"]


def test_a_repeat_across_the_two_groups_is_kept_once():
    """Повтор между обязательным и желательным списками тоже один раз.

    Общий набор передаётся между вызовами нарочно: промпт запрещает
    называть один навык дважды, но модель это нарушает, и в карточке
    вакансии он вылезал бы в обеих строках.
    """
    seen: set[str] = set()

    required = clean_stack_items(["Python", "Docker"], seen)
    preferred = clean_stack_items(["docker", "Redis"], seen)

    assert required == ["Python", "Docker"]
    assert preferred == ["Redis"]


def test_a_version_and_a_bare_name_collapse_into_one():
    """«Python 3.13» и «Python» рядом схлопываются в одно название."""
    assert clean_stack_items(["Python 3.13", "Python"], set()) == ["Python"]


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        pytest.param(
            "Python, Docker", ["Python", "Docker"], id="строка вместо списка"
        ),
        pytest.param(42, [], id="число"),
        pytest.param(None, [], id="ничего"),
        pytest.param({"a": 1}, [], id="объект"),
        pytest.param([], [], id="пустой список"),
    ],
)
def test_anything_but_a_list_is_handled_without_falling(raw, expected):
    """Не-список не роняет разбор: строка делится запятой, прочее даёт пустоту.

    Деление запятой оставлено для старого однострочного вида ответа: модель
    иногда возвращает его вместо списка.
    """
    assert clean_stack_items(raw, set()) == expected


def test_two_spellings_of_one_name_are_kept_once():
    """Разделители внутри названия одного навыка не заводят второй.

    «CI/CD» и «ci cd» — одна технология, и сравнивают её тем же ключом, что
    и навык анкеты. Оставь модель оба написания в стеке — вакансия получила
    бы двойной балл за один навык.
    """
    assert clean_stack_items(["CI/CD", "ci cd"], set()) == ["CI/CD"]


def test_junk_inside_the_list_is_skipped():
    """Мусор внутри списка пропускается, а не роняет разбор."""
    assert clean_stack_items(["Python", 42, None, "   ", ""], set()) == ["Python"]


def test_a_name_made_of_separators_is_not_a_skill():
    """Написание из одних разделителей тегом не становится, сколько бы их ни было.

    Сравнивать такое не с чем: ключ у него пустой. Рядом настоящее название,
    чтобы проверка не прошла на пустом ответе.
    """
    assert clean_stack_items(["///", "-", "Python"], set()) == ["Python"]


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        pytest.param("Опыт работы с Docker", "Docker", id="опыт работы с"),
        pytest.param("Знание CI/CD", "CI/CD", id="знание"),
        pytest.param("Опыт монтажа в Premiere Pro", "Premiere Pro", id="в чём"),
        pytest.param("умение работать с Figma", "Figma", id="умение работать с"),
        pytest.param("Владение Photoshop", "Photoshop", id="владение"),
        pytest.param("Работа с Docker", "Docker", id="работа с"),
        pytest.param(
            "Опыт успешной работы с Docker", "Docker", id="прилагательное внутри"
        ),
        pytest.param("Знание .NET", ".NET", id="имя с точки"),
        pytest.param("Опыт работы с H&M", "H&M", id="имя с амперсандом"),
    ],
)
def test_a_requirement_wrapper_is_stripped_from_a_named_tool(raw, expected):
    """Обёртка требования снимается, когда за ней стоит имя собственное.

    Наставление просит модель отдавать название, а не требование целиком, и
    просьбу эту она исполняет не всегда. В карточке такой тег занимает строку,
    а с анкетой не сходится — ключ у него другой.

    Снимается обёртка только перед именем, написанным латиницей: у русского
    хвоста остаётся падеж («ведения соцсетей»), и починить его срезкой слова
    нельзя — там нужна начальная форма, которой у кода нет.
    """
    assert clean_stack_items([raw], set()) == [expected]


@pytest.mark.parametrize(
    "raw",
    [
        pytest.param("Опыт ведения соцсетей", id="русский хвост"),
        pytest.param("Опыт", id="одна обёртка"),
        pytest.param("Знание кассовой дисциплины", id="русский хвост из двух слов"),
    ],
)
def test_a_wrapper_over_a_russian_tail_is_left_to_the_model(raw):
    """Обёртка над русским хвостом остаётся как есть.

    Срезав слово, код получил бы «ведения соцсетей» — падеж без начальной
    формы, а это хуже исходного: тег читается как обрывок. Такое чинит
    наставление, а не код.
    """
    assert clean_stack_items([raw], set()) == [_capitalize_skill(raw)]


def test_a_whole_requirement_without_a_name_is_not_a_skill_tag():
    """Длинное требование, не назвавшее ни одного имени, тегом не становится.

    Признаков два, и работают они только вместе: строка начата словом-
    обёрткой, и за обёрткой не название, а фраза длиннее четырёх слов. Такое
    приходит из строки требований: с анкетой оно не сойдётся никогда, а место
    в карточке займёт. Назови такая строка инструмент — он был бы взят из неё
    отдельным тегом.
    """
    long_one = "Опыт ведения переговоров с поставщиками сырья и логистами"

    assert clean_stack_items([long_one, "Python"], set()) == ["Python"]


@pytest.mark.parametrize(
    "raw",
    [
        pytest.param(
            "Монтаж систем вентиляции и кондиционирования", id="строитель"
        ),
        pytest.param(
            "Настройка контекстной рекламы Яндекс Директ", id="маркетолог"
        ),
        pytest.param("Составление букетов в европейском стиле", id="флорист"),
    ],
)
def test_a_long_name_without_a_wrapper_stays(raw):
    """Длинное название, начатое не с обёртки, остаётся тегом.

    Названия навыков коротки не во всякой профессии: у строителя, маркетолога
    и флориста они бывают в пять-шесть слов и при этом остаются названиями, а
    не переписанным требованием. Отсев по одной длине выбрасывал их вместе с
    мусором.
    """
    assert clean_stack_items([raw], set()) == [_capitalize_skill(raw)]


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        pytest.param("Опыт работы в Excel и Word", ["Excel", "Word"], id="союз «и»"),
        pytest.param(
            "Опыт работы с Docker, Kubernetes", ["Docker", "Kubernetes"], id="запятая"
        ),
        pytest.param(
            "Знание CI/CD и Terraform", ["CI/CD", "Terraform"], id="косая внутри имени"
        ),
    ],
)
def test_names_listed_in_one_requirement_become_separate_tags(raw, expected):
    """Из требования с перечислением берутся все названные имена, а не ноль.

    Хвост «Excel и Word» именем целиком не является — внутри союз, — и прежде
    строка признавалась требованием и выбрасывалась вместе с обоими
    названиями. Терять названное в тексте хуже, чем оставить лишний тег.
    """
    assert clean_stack_items([raw], set()) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        pytest.param(
            "Опыт работы с Docker в продакшене", ["Docker"], id="уточнение после имени"
        ),
        pytest.param("Знания по Kafka", ["Kafka"], id="другая форма обёртки"),
        pytest.param("Навыки работы во Figma", ["Figma"], id="предлог «во»"),
        pytest.param("Понимание работы на Kubernetes", ["Kubernetes"], id="предлог «на»"),
    ],
)
def test_a_name_is_found_even_with_words_around_it(raw, expected):
    """Имя достаётся из требования, даже когда вокруг него русские слова.

    Хвост требования не кончается именем: «с Docker в продакшене» — то же
    требование про Docker, а поиск по последнему предлогу уводил в
    «продакшене» и терял названный инструмент вместе со всей строкой.
    """
    assert clean_stack_items([raw], set()) == expected


def test_a_wrapped_requirement_of_four_words_is_still_a_tag():
    """Требование ровно в четыре слова остаётся тегом.

    Порог назван предельным, а не запретным: на самой границе строка ещё
    похожа на название, и выбрасывать её не за что.
    """
    assert clean_stack_items(["Знание основ вёрстки текста"], set()) == [
        "Знание Основ Вёрстки Текста"
    ]
