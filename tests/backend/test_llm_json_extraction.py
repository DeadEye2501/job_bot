"""Следствия вырезания ответа-объекта из того, что вернула модель.

Модель редко отвечает одним голым объектом: перед ним бывает рассуждение,
после — извинения или повтор. Берётся последний найденный объект: если модель
сперва показала пример из промпта, а потом дала ответ, ответом будет второе.

Кавычки, которые редакторы и модели ставят «ёлочками» и «лапками», приводятся
к прямым до разбора — иначе разбор JSON падает на своей же кавычке.
"""

import pytest

from backend.llm import _extract_last_json, _normalize_enum


@pytest.mark.parametrize(
    ("answer", "expected"),
    [
        pytest.param('{"a": 1}', '{"a": 1}', id="голый объект"),
        pytest.param(
            'Вот ответ: {"a": 1}. Надеюсь, помог.',
            '{"a": 1}',
            id="объект среди текста",
        ),
        pytest.param(
            'Пример: {"a": 1}\nОтвет: {"a": 2}',
            '{"a": 2}',
            id="берётся последний из двух",
        ),
        pytest.param("", None, id="пустой ответ"),
        pytest.param("совсем без объекта", None, id="объекта нет"),
        pytest.param('{"a": 1', None, id="скобка не закрыта"),
    ],
)
def test_the_last_object_is_taken_from_the_answer(answer, expected):
    """Из ответа берётся последний объект, а без объекта — ничего."""
    assert _extract_last_json(answer) == expected


def test_curly_quotes_are_straightened_before_the_search():
    """Кавычки-ёлочки и лапки выпрямляются до поиска объекта.

    Модель, отвечающая по-русски, ставит их сама, и разбор падал бы на
    первой же такой кавычке.
    """
    assert _extract_last_json('{“a”: ‘b’}') == '{"a": \'b\'}'


def test_a_nested_object_is_not_matched():
    """Вложенный объект целиком не выхватывается.

    Выражение ищет объект без вложенных скобок, поэтому у ответа с
    вложенностью совпадёт только внутренняя часть. Тест закрепляет
    сегодняшнее поведение: разбор такого ответа даст не то, что ждали.
    """
    assert _extract_last_json('{"outer": {"inner": 1}}') == '{"inner": 1}'


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        pytest.param("senior", "senior", id="уже в нужном виде"),
        pytest.param("  SENIOR  ", "senior", id="регистр и пробелы"),
        pytest.param("architect", None, id="не из набора"),
        pytest.param("", None, id="пустая строка"),
        pytest.param(None, None, id="ничего"),
        pytest.param(42, None, id="не строка"),
        pytest.param(["senior"], None, id="список"),
    ],
)
def test_a_value_outside_the_allowed_set_is_dropped(value, expected):
    """Значение вне набора отбрасывается, а годное приводится к нижнему регистру.

    Модель охотно выдумывает уровни вроде «architect», и пустить такое в
    базу значило бы завести статус, которого экран не знает.
    """
    assert _normalize_enum(value, {"junior", "middle", "senior", "lead"}) == expected
