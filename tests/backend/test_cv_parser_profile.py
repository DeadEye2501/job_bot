"""Следствия разбора профиля и языков в `backend/cv_parser.py`.

Все закрытые разборщики видны только через `parse_cv`: «модель вернула такой
JSON — вышло такое». Ответ подставляется подделкой, путь до разбора настоящий.
"""

import json

import pytest

from backend.cv_parser import parse_cv
from tests.factories import CV_REQUIRED_PROFILE
from tests.fakes.llm import CHAT, chat_response, provider


async def parse_answer(answer: str):
    """Прогнать готовый ответ модели через настоящий разбор."""
    client = provider({CHAT: chat_response(answer)})
    return await parse_cv("резюме", client, "qwen")


async def parse_profile(**fields):
    """Прогнать профиль с заданными полями, остальное — обязательный минимум."""
    return await parse_answer(json.dumps({"profile": {**CV_REQUIRED_PROFILE, **fields}}))


async def test_a_minimal_profile_is_enough_for_a_parse():
    """Имя, фамилия, должность и почта — достаточный минимум."""
    parsed = await parse_profile()

    assert parsed is not None
    assert parsed.profile.last_name == "Фролов"


@pytest.mark.parametrize("missing", ["first_name", "last_name", "title", "email"])
async def test_a_profile_without_a_required_field_kills_the_whole_parse(missing):
    """Без любого обязательного поля разбора нет вовсе — не только профиля."""
    fields = {k: v for k, v in CV_REQUIRED_PROFILE.items() if k != missing}

    assert await parse_answer(json.dumps({"profile": fields})) is None


async def test_an_answer_without_a_profile_yields_no_parse():
    """Ответ без профиля — не резюме."""
    assert await parse_answer('{"languages": []}') is None


async def test_blank_optional_fields_become_absent():
    """Пустая строка в необязательном поле — это отсутствие, а не пустота."""
    parsed = await parse_profile(phone="   ", location="")

    assert parsed.profile.phone is None
    assert parsed.profile.location is None


async def test_a_non_string_optional_field_becomes_absent():
    """Число вместо строки — тоже отсутствие, а не падение."""
    parsed = await parse_profile(github_url=42)

    assert parsed.profile.github_url is None


async def test_only_known_work_formats_survive():
    """Из формата работы остаётся только известное, в нижнем регистре."""
    parsed = await parse_profile(work_format=["Remote", "office", "как получится"])

    assert parsed.profile.work_format == ["remote", "office"]


async def test_a_repeated_work_format_is_kept_once():
    """Повтор формата не удваивается."""
    parsed = await parse_profile(work_format=["remote", "REMOTE"])

    assert parsed.profile.work_format == ["remote"]


async def test_a_non_string_inside_work_format_is_dropped():
    """Не строка среди форматов работы выбрасывается, а не роняет разбор.

    Список приходит из ответа модели, где на месте строки может оказаться что
    угодно — число, словарь, `null`. Без этой охраны одно такое значение
    отменяло бы разбор всего резюме.
    """
    parsed = await parse_profile(work_format=["remote", 42, None, {"office": True}])

    assert parsed.profile.work_format == ["remote"]


async def test_only_known_grades_survive():
    """Из уровней остаётся только известное."""
    parsed = await parse_profile(grades=["Senior", "гуру", "lead"])

    assert parsed.profile.grades == ["senior", "lead"]


@pytest.mark.parametrize("raw", ["remote", 42])
async def test_a_non_list_work_format_becomes_empty(raw):
    """Не список вместо формата работы — пустой список, а не падение.

    Число взято вторым входом нарочно: строку перебор проходит по буквам и
    без охраны, а по числу спотыкается — на нём и видно, что охрана есть.
    """
    parsed = await parse_profile(work_format=raw)

    assert parsed.profile.work_format == []


async def test_language_levels_come_back_uppercase():
    """Уровень языка приводится к общему виду."""
    parsed = await parse_answer(json.dumps({
        "profile": CV_REQUIRED_PROFILE,
        "languages": [{"language": "English", "level": "b2"}],
    }))

    assert [(x.language, x.level) for x in parsed.languages] == [("English", "B2")]


@pytest.mark.parametrize("native", ["native", "родной"])
async def test_a_native_language_is_recognised_in_both_spellings(native):
    """Родной язык распознаётся и по-русски, и по-английски."""
    parsed = await parse_answer(json.dumps({
        "profile": CV_REQUIRED_PROFILE,
        "languages": [{"language": "Русский", "level": native}],
    }))

    assert parsed.languages[0].level == "native"


async def test_a_language_with_an_unknown_level_is_dropped():
    """Язык с невнятным уровнем не попадает в разбор."""
    parsed = await parse_answer(json.dumps({
        "profile": CV_REQUIRED_PROFILE,
        "languages": [{"language": "Deutsch", "level": "нулевой"}],
    }))

    assert parsed.languages == []


async def test_a_language_without_a_name_is_dropped():
    """Язык без названия не попадает в разбор."""
    parsed = await parse_answer(json.dumps({
        "profile": CV_REQUIRED_PROFILE,
        "languages": [{"language": "", "level": "A1"}],
    }))

    assert parsed.languages == []


async def test_a_repeated_language_keeps_the_first_spelling():
    """Повтор языка не удваивается; остаётся первое написание."""
    parsed = await parse_answer(json.dumps({
        "profile": CV_REQUIRED_PROFILE,
        "languages": [
            {"language": "Русский", "level": "native"},
            {"language": "русский", "level": "C1"},
        ],
    }))

    assert [(x.language, x.level) for x in parsed.languages] == [("Русский", "native")]


async def test_json_is_pulled_out_of_a_code_fence():
    """JSON достаётся из заборчика, которым модель его обрамила."""
    answer = "Вот результат:\n```json\n" + json.dumps({"profile": CV_REQUIRED_PROFILE}) + "\n```"

    assert await parse_answer(answer) is not None


async def test_curly_quotes_do_not_break_the_parse():
    """Кавычки-ёлочки, которые подставляет модель, не ломают разбор."""
    answer = json.dumps({"profile": CV_REQUIRED_PROFILE}).replace('"', "“", 1)

    assert await parse_answer(answer) is not None


async def test_a_json_object_with_a_syntax_error_yields_no_parse():
    """Блок JSON найден, но не разбирается — тоже не разбор."""
    assert await parse_answer('{"profile": {"first_name": "A",}}') is None


async def test_a_language_that_is_not_an_object_is_dropped():
    """Не объект вместо языка отбрасывается, а не роняет разбор."""
    parsed = await parse_answer(json.dumps({
        "profile": CV_REQUIRED_PROFILE,
        "languages": ["English", None, {"language": "Deutsch", "level": "B2"}],
    }))

    assert [x.language for x in parsed.languages] == ["Deutsch"]
