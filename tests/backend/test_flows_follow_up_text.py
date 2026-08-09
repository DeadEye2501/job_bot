"""Следствия составления короткого письма про очередную вакансию.

Полное письмо с резюме пишется один раз. Если тому же HR за две недели уже
писали, вторая вакансия уходит короткой припиской: повторять всё заново
значило бы завалить человека одинаковыми простынями.

Приписка знает, в который раз пишет: «А вот ещё одну» на второй вакансии и
«И ещё одну» на третьей и дальше. Название и ссылка на канал подставляются,
если есть; их отсутствие письмо не отменяет — отправить отклик важнее, чем
точно его подписать.
"""

import pytest

from backend.flows.apply import _build_short_text, _format_channel_ref


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
    assert _format_channel_ref(raw) == expected


def test_the_second_vacancy_is_introduced_as_one_more():
    """Вторая вакансия подаётся как «ещё одна»."""
    assert _build_short_text("Python-разработчик", None, 1) == (
        "А вот я увидел ещё одну интересную вакансию: Python-разработчик"
    )


@pytest.mark.parametrize("prior", [2, 3, 7])
def test_the_third_and_later_are_introduced_more_briefly(prior):
    """С третьей вакансии приписка становится короче.

    Восторг «интересную» на седьмом письме подряд читается издевательски.
    """
    assert _build_short_text("Python-разработчик", None, prior) == (
        "И ещё одну: Python-разработчик"
    )


@pytest.mark.parametrize(
    ("prior", "expected"),
    [
        pytest.param(1, "А вот я увидел ещё одну вашу вакансию", id="вторая"),
        pytest.param(2, "И ещё одну вашу вакансию", id="третья"),
    ],
)
def test_a_vacancy_without_a_title_is_still_written_about(prior, expected):
    """Вакансия без названия всё равно получает письмо.

    Название берётся из разбора и иногда не выходит; отменять из-за него
    отклик значило бы менять сделанное дело на подпись к нему.
    """
    assert _build_short_text("", None, prior) == expected


def test_the_channel_is_named_on_its_own_line():
    """Канал называется отдельной строкой под вводной."""
    got = _build_short_text("Python-разработчик", "@pyjobs", 1)

    assert got == (
        "А вот я увидел ещё одну интересную вакансию: Python-разработчик"
        "\nКанал: @pyjobs"
    )


def test_a_vacancy_without_a_channel_gets_no_channel_line():
    """Без канала строки о канале в письме нет."""
    assert "\n" not in _build_short_text("Python-разработчик", None, 1)
