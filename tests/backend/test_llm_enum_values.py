"""Следствия сверки значения со списком допустимых.

Модель охотно выдумывает уровни вроде «architect» и форматы вроде
«anywhere». Пустить такое в базу значило бы завести значение, которого
экран не знает и показать не сможет.
"""

import pytest

from backend.llm import _normalize_enum


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
    assert _normalize_enum(value, ("junior", "middle", "senior", "lead")) == expected
