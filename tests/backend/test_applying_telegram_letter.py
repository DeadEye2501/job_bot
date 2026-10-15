"""Ссылка на канал в письме HR: с собачкой или никакой."""

import pytest

from backend.applying.telegram_letter import format_channel_ref


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        pytest.param("pyjobs", "@pyjobs", id="без собачки"),
        pytest.param("@pyjobs", "@pyjobs", id="с собачкой"),
        pytest.param("  pyjobs  ", "@pyjobs", id="с пробелами по краям"),
        pytest.param(None, None, id="канала нет"),
        pytest.param("", None, id="имя пустое"),
        pytest.param("   ", None, id="одни пробелы"),
    ],
)
def test_a_channel_reference_is_normalised_or_dropped(raw, expected):
    """Ссылка на канал приводится к виду с собачкой либо пропадает совсем.

    Пропадает именно отсутствием: строку «Канал: …» составитель письма
    тогда не пишет вовсе, а не показывает HR «Канал: None».
    """
    assert format_channel_ref(raw) == expected
