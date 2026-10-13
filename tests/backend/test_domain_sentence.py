"""Законченная фраза: точка в конце, если своего знака конца нет."""

import pytest

from backend.domain.sentence import closed_sentence


@pytest.mark.parametrize(
    ("text", "closed"),
    [
        pytest.param("Запустил сервис", "Запустил сервис.", id="без знака — точка"),
        pytest.param("Готово!", "Готово!", id="свой знак остаётся"),
        pytest.param("Причина:", "Причина:", id="двоеточие — тоже конец"),
        pytest.param("Работал в «Директе».»", "Работал в «Директе».»", id="знак за кавычкой"),
        pytest.param("(в т.ч. CI.)", "(в т.ч. CI.)", id="знак за скобкой"),
        pytest.param("Работал с «Директом»", "Работал с «Директом».", id="кавычка без знака"),
    ],
)
def test_a_sentence_ends_with_its_own_mark_or_a_full_stop(text, closed):
    assert closed_sentence(text) == closed
