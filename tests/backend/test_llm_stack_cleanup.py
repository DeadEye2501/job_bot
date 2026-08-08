"""Следствия приведения названий технологий к единому виду.

Модель нарушает инструкцию «без версий» и присылает «Python 3.13», а регистр
пишет как придётся. Хвост с версией срезается, а полностью строчное слово
получает заглавную — но только полностью строчное: у «SQLAlchemy», «iOS» и
«gRPC» вид канонический, и трогать его нельзя.

Короткие имена с цифрой в составе — «Web3», «S3» — от срезания защищены: без
защиты от них осталась бы одна буква.
"""

import pytest

from backend.llm import _capitalize_skill, _clean_stack_items, _strip_version


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
        pytest.param("S3", "S3", id="одна буква после среза"),
        pytest.param("C4", "C4", id="одна буква после среза, вторая"),
        pytest.param("2024", "2024", id="одни цифры"),
    ],
)
def test_a_version_tail_is_cut_unless_it_is_part_of_the_name(raw, expected):
    """Хвост с версией срезается, кроме случаев, когда цифра — часть имени."""
    assert _strip_version(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        pytest.param("Web3", "Web", id="имя, теряющее цифру"),
        pytest.param("Go 1.22+", "Go 1.22+", id="короткое имя, сохраняющее версию"),
        pytest.param("R 4.3", "R 4.3", id="однобуквенное имя с версией"),
    ],
)
def test_the_short_name_guard_misfires_both_ways(raw, expected):
    """Защита коротких имён срабатывает не там, где обещает комментарий кода.

    Порог в три знака выбран, чтобы уберечь «S3» и «C4», где цифра — часть
    имени. Но «Web3» после среза даёт ровно три знака, порог не срабатывает,
    и в стек уходит «Web» — имени такого нет.

    С другой стороны, у двухбуквенных имён версия не срезается вовсе: «Go
    1.22+» так и остаётся, и в стеке заводится тег с версией — ровно то, от
    чего срезание защищает.

    Тест закрепляет сегодняшнее поведение: при починке он покраснеет.
    """
    assert _strip_version(raw) == expected


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
    assert _clean_stack_items(["fastapi 0.110"], set()) == ["Fastapi"]


def test_a_repeat_is_kept_once():
    """Повтор внутри списка остаётся один раз, без учёта регистра."""
    assert _clean_stack_items(["Python", "python", "PYTHON"], set()) == ["Python"]


def test_a_repeat_across_the_two_groups_is_kept_once():
    """Повтор между обязательным и желательным списками тоже один раз.

    Общий набор передаётся между вызовами нарочно: промпт запрещает
    называть один навык дважды, но модель это нарушает, и в карточке
    вакансии он вылезал бы в обеих строках.
    """
    seen: set[str] = set()

    required = _clean_stack_items(["Python", "Docker"], seen)
    preferred = _clean_stack_items(["docker", "Redis"], seen)

    assert required == ["Python", "Docker"]
    assert preferred == ["Redis"]


def test_a_version_and_a_bare_name_collapse_into_one():
    """«Python 3.13» и «Python» рядом схлопываются в одно название."""
    assert _clean_stack_items(["Python 3.13", "Python"], set()) == ["Python"]


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
    assert _clean_stack_items(raw, set()) == expected


def test_junk_inside_the_list_is_skipped():
    """Мусор внутри списка пропускается, а не роняет разбор."""
    assert _clean_stack_items(["Python", 42, None, "   ", ""], set()) == ["Python"]
