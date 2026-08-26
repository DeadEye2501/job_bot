"""Следствия разбора профиля и языков в `backend/llm/cv.py`.

Все закрытые разборщики видны только через `parse_cv`: «модель вернула такой
JSON — вышло такое». Ответ подставляется подделкой, путь до разбора настоящий.
"""

import json

import pytest

from backend.llm.cv import parse_cv
from tests.factories import CV_REQUIRED_PROFILE
from tests.fakes.llm import CHAT, chat_response, provider


async def parse_answer(answer: str, text: str = "резюме"):
    """Прогнать готовый ответ модели через настоящий разбор.

    Текст резюме задаётся там, где ответ говорит о языке или грейде: разбор
    сверяет их с текстом и выбрасывает не названное в нём.
    """
    client = provider({CHAT: chat_response(answer)})
    return await parse_cv(text, client, "qwen")


async def parse_profile(text: str = "резюме", **fields):
    """Прогнать профиль с заданными полями, остальное — обязательный минимум.

    Текст резюме задают там, где ответ говорит о грейде, формате работы или
    языке: разбор сверяет их с текстом и выбрасывает не названное в нём.
    """
    return await parse_answer(
        json.dumps({"profile": {**CV_REQUIRED_PROFILE, **fields}}), text=text
    )


async def test_a_minimal_profile_is_enough_for_a_parse():
    """Имя, фамилия, должность и почта — достаточный минимум."""
    parsed = await parse_profile()

    assert parsed is not None
    assert parsed.profile.last_name == "Петров"


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
    parsed = await parse_profile(
        text="Рассматриваю remote или работу в офисе",
        work_format=["Remote", "office", "как получится"],
    )

    assert parsed.profile.work_format == ["remote", "office"]


async def test_a_repeated_work_format_is_kept_once():
    """Повтор формата не удваивается."""
    parsed = await parse_profile(
        text="Формат: remote", work_format=["remote", "REMOTE"]
    )

    assert parsed.profile.work_format == ["remote"]


async def test_a_non_string_inside_work_format_is_dropped():
    """Не строка среди форматов работы выбрасывается, а не роняет разбор.

    Список приходит из ответа модели, где на месте строки может оказаться что
    угодно — число, словарь, `null`. Без этой охраны одно такое значение
    отменяло бы разбор всего резюме.
    """
    parsed = await parse_profile(
        text="Формат: remote", work_format=["remote", 42, None, {"office": True}]
    )

    assert parsed.profile.work_format == ["remote"]


async def test_only_known_grades_survive():
    """Из уровней остаётся только известное."""
    parsed = await parse_profile(
        text="Senior Python Developer, гуру и тимлид",
        grades=["Senior", "гуру", "lead"],
    )

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
    }), text="Иностранные языки: English — b2, читаю документацию свободно")

    assert ("English", "B2") in [(x.language, x.level) for x in parsed.languages]


@pytest.mark.parametrize("native", ["native", "родной"])
async def test_a_native_language_is_recognised_in_both_spellings(native):
    """Родной язык распознаётся и по-русски, и по-английски."""
    parsed = await parse_answer(json.dumps({
        "profile": CV_REQUIRED_PROFILE,
        "languages": [{"language": "Русский", "level": native}],
    }), text="Языки: русский")

    assert parsed.languages[0].level == "native"


async def test_a_language_with_an_unknown_level_keeps_the_highest_one():
    """Уровень невнятен, но язык человек назвал — значит он у него есть.

    Ставится высший: невнятность — не скромность. Уровень уточняет тот, кто в
    языке не уверен.
    """
    parsed = await parse_answer(json.dumps({
        "profile": CV_REQUIRED_PROFILE,
        "languages": [{"language": "Deutsch", "level": "письменный"}],
    }), text="Иностранные языки: Deutsch — письменный")

    assert ("Deutsch", "C2") in [(x.language, x.level) for x in parsed.languages]


async def test_a_language_named_without_any_level_keeps_the_highest_one():
    """Уровня нет вовсе — тот же случай, что и невнятный."""
    parsed = await parse_answer(json.dumps({
        "profile": CV_REQUIRED_PROFILE,
        "languages": [{"language": "Deutsch"}],
    }), text="Иностранные языки: Deutsch")

    assert ("Deutsch", "C2") in [(x.language, x.level) for x in parsed.languages]


async def test_a_language_without_a_name_is_dropped():
    """Язык без названия не попадает в разбор."""
    parsed = await parse_answer(json.dumps({
        "profile": CV_REQUIRED_PROFILE,
        "languages": [{"language": "", "level": "A1"}],
    }), text="Иностранные языки: английский")

    assert [x.language for x in parsed.languages] == ["Русский"]


async def test_a_repeated_language_keeps_the_first_spelling():
    """Повтор языка не удваивается; остаётся первое написание."""
    parsed = await parse_answer(json.dumps({
        "profile": CV_REQUIRED_PROFILE,
        "languages": [
            {"language": "Русский", "level": "native"},
            {"language": "русский", "level": "C1"},
        ],
    }), text="Языки: русский")

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
    }), text="Владение иностранными языками: English, Deutsch")

    assert [x.language for x in parsed.languages] == ["Русский", "Deutsch"]


async def test_a_named_level_beats_a_missing_one_for_the_same_language():
    """Тот же язык приехал дважды: с невнятным уровнем и с внятным.

    Побеждает внятный, в каком бы порядке они ни пришли. Подставь умолчание
    до отсева повторов — и оно заняло бы место первым, затерев названное.
    """
    parsed = await parse_answer(json.dumps({
        "profile": CV_REQUIRED_PROFILE,
        "languages": [
            {"language": "Английский", "level": "технический"},
            {"language": "Английский", "level": "C1"},
        ],
    }), text="Иностранные языки: английский — C1, технический")

    english = [x for x in parsed.languages if x.language == "Английский"]
    assert [(x.language, x.level) for x in english] == [("Английский", "C1")]


async def test_the_first_spelling_of_a_repeated_language_survives_the_winner():
    """Победил уровень из второй записи, а написание осталось от первой.

    Иначе анкета звалась бы языком в том написании, в каком он приехал
    случайным вторым, — «английский» строчной буквой вместо «Английский».
    """
    parsed = await parse_answer(json.dumps({
        "profile": CV_REQUIRED_PROFILE,
        "languages": [
            {"language": "Английский", "level": "технический"},
            {"language": "английский", "level": "C1"},
        ],
    }), text="Иностранные языки: английский — C1, технический")

    assert ("Английский", "C1") in [(x.language, x.level) for x in parsed.languages]


@pytest.mark.parametrize(
    "named, level",
    [
        ("свободно", "C1"),
        ("Fluent", "C1"),
        ("разговорный", "B1"),
        ("Intermediate", "B1"),
        ("базовый", "A1"),
        ("в совершенстве", "C2"),
    ],
)
async def test_a_level_named_in_words_becomes_the_matching_one(named, level):
    """Уровень, названный словом, переводится в шкалу, а не приравнивается к A1.

    «Свободно» — это названный уровень, просто не по шкале. Считать его нижним
    значило бы отрезать человеку все вакансии, где язык нужен.
    """
    parsed = await parse_answer(json.dumps({
        "profile": CV_REQUIRED_PROFILE,
        "languages": [{"language": "Английский", "level": named}],
    }), text=f"Иностранные языки: английский — {named}")

    assert ("Английский", level) in [(x.language, x.level) for x in parsed.languages]


async def test_a_level_named_by_an_unknown_word_falls_back_to_the_highest():
    """Незнакомое слово — не уровень, и высший тут именно запасной ответ."""
    parsed = await parse_answer(json.dumps({
        "profile": CV_REQUIRED_PROFILE,
        "languages": [{"language": "Английский", "level": "технический"}],
    }), text="Иностранные языки: английский — технический")

    assert ("Английский", "C2") in [(x.language, x.level) for x in parsed.languages]


@pytest.mark.parametrize(
    "named, level",
    [
        ("Свободно.", "C1"),
        ("C1 (advanced)", "C1"),
        ("Upper Intermediate", "B2"),
        ("  fluent  ", "C1"),
    ],
)
async def test_a_level_named_loosely_is_still_understood(named, level):
    """Модель возвращает уровень как в резюме, а там его пишут по-всякому."""
    parsed = await parse_answer(json.dumps({
        "profile": CV_REQUIRED_PROFILE,
        "languages": [{"language": "Английский", "level": named}],
    }), text=f"Иностранные языки: английский — {named}")

    assert ("Английский", level) in [(x.language, x.level) for x in parsed.languages]


async def test_a_level_typed_in_cyrillic_letters_is_understood_by_the_parse():
    """«В2» русскими буквами — тот же B2, и разбору его тоже надо узнать.

    Сверка омоглифы сводит, а разбор — нет, и уровень уезжал в запасной
    высший ещё до неё.
    """
    parsed = await parse_answer(json.dumps({
        "profile": CV_REQUIRED_PROFILE,
        "languages": [{"language": "Английский", "level": "В2"}],
    }), text="Иностранные языки: английский — В2")

    assert ("Английский", "B2") in [(x.language, x.level) for x in parsed.languages]
