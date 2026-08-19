"""Следствия подготовки сведений о кандидате для запроса к модели.

Всё, чего нет, обозначается одним прочерком, а не пустой строкой: пустое место
в промпте модель дописывает сама, а прочерк читает как «не указано». По той же
причине язык без уровня пропускается целиком — иначе в строке появился бы
второй прочерк, и модель приняла бы его за уровень.
"""

import pytest

from backend.llm.candidate import (
    CandidateLanguage,
    format_text,
    format_grades,
    format_known_skills,
    format_languages,
    format_work_formats,
)


@pytest.mark.parametrize(
    ("grades", "expected"),
    [
        pytest.param(None, "—", id="ничего"),
        pytest.param([], "—", id="пустой список"),
        pytest.param(["senior"], "senior", id="один уровень"),
        pytest.param(["  SENIOR  "], "senior", id="регистр и пробелы"),
        pytest.param(["middle", "senior"], "middle, senior", id="два уровня"),
        # Единственный уровень, чьё обозначение не совпадает с ключом: без
        # этого случая строку словаря можно удалить, и прогон промолчит.
        pytest.param(["lead"], "lead/team-lead", id="обозначение шире ключа"),
        pytest.param(["architect"], "—", id="уровень не из набора"),
        pytest.param(["senior", "architect"], "senior", id="лишний отсеивается"),
    ],
)
def test_grades_are_named_by_their_known_labels(grades, expected):
    """Уровни называются известными обозначениями, незнакомые отсеиваются."""
    assert format_grades(grades) == expected


@pytest.mark.parametrize(
    ("formats", "expected"),
    [
        pytest.param(None, "—", id="ничего"),
        pytest.param([], "—", id="пустой список"),
        pytest.param(["remote"], "удалёнка", id="один формат"),
        pytest.param(["  REMOTE  "], "удалёнка", id="регистр и пробелы"),
        pytest.param(["remote", "hybrid"], "удалёнка, гибрид", id="два формата"),
        pytest.param(["office"], "офис", id="офис"),
        pytest.param(["anywhere"], "—", id="формат не из набора"),
    ],
)
def test_work_formats_are_named_in_russian(formats, expected):
    """Форматы работы называются по-русски: промпт на русском."""
    assert format_work_formats(formats) == expected


def test_languages_are_listed_with_their_levels():
    """Языки перечисляются с уровнями через тире."""
    got = format_languages(
        [
            CandidateLanguage(name="Русский", level="native"),
            CandidateLanguage(name="Английский", level="B2"),
        ]
    )

    assert got == "Русский — native, Английский — B2"


@pytest.mark.parametrize(
    "languages",
    [
        pytest.param(None, id="ничего"),
        pytest.param([], id="пустой список"),
        pytest.param([CandidateLanguage(name="  ", level="B2")], id="язык без имени"),
        pytest.param(
            [CandidateLanguage(name="Английский", level="  ")], id="язык без уровня"
        ),
    ],
)
def test_a_language_without_both_halves_is_skipped(languages):
    """Язык без имени или без уровня пропускается целиком.

    Строка «Английский — » с пустым уровнем читалась бы моделью как
    настоящий уровень, а не как его отсутствие.
    """
    assert format_languages(languages) == "—"


def test_a_language_without_a_level_does_not_spoil_the_rest():
    """Пропуск одного языка остальных не задевает."""
    got = format_languages(
        [
            CandidateLanguage(name="Русский", level="native"),
            CandidateLanguage(name="Армянский", level=""),
        ]
    )

    assert got == "Русский — native"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        pytest.param(None, "—", id="ничего"),
        pytest.param("   ", "—", id="одни пробелы"),
        pytest.param("  готов к переезду  ", "готов к переезду", id="обрезается"),
    ],
)
def test_a_free_text_slot_is_passed_as_written(text, expected):
    """Свободный текст доезжает до промпта как написан, пустой — прочерком.

    Слотов на этом объявлении три — роль, локация и пожелания, — и прочерк
    у них общий: пустой слот оставил бы в промпте оборванную строку.
    """
    assert format_text(text) == expected


class _Skill:
    """Навык профиля в том виде, в каком его читает подготовка промпта."""

    def __init__(self, name, aliases=None):
        self.name = name
        self.aliases = aliases


def test_known_skills_are_listed_with_their_spellings():
    """Известные навыки перечисляются списком, написания идут через тире.

    Список нужен модели, чтобы она называла технологии так же, как они
    записаны у кандидата, а не своими словами.
    """
    got = format_known_skills(
        [_Skill("PostgreSQL", ["Postgres", "PG"]), _Skill("Python")]
    )

    assert got == "- PostgreSQL — Postgres, PG\n- Python"


@pytest.mark.parametrize(
    "skills",
    [
        pytest.param(None, id="ничего"),
        pytest.param([], id="пустой список"),
        pytest.param([_Skill("   ")], id="навык без имени"),
    ],
)
def test_an_empty_skill_list_becomes_a_dash(skills):
    """Пустой список навыков становится прочерком.

    Пустое место в этом углу промпта оставило бы предложение оборванным.
    """
    assert format_known_skills(skills) == "—"


def test_junk_among_the_spellings_is_skipped():
    """Мусор среди написаний пропускается, а не роняет подготовку."""
    got = format_known_skills([_Skill("Python", ["py", 42, None, "   "])])

    assert got == "- Python — py"
