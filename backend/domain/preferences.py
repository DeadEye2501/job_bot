"""Строки предпочтений анкеты: кому какой вид.

Каждый потребитель получает только свой вид: проверка запретов — запреты,
проверка места — сведения. Увидев пожелания, проверка запретов принимает их
за запреты и отсеивает вакансии, которых человек не отсекал.
"""

from collections.abc import Iterable

from backend.models import PreferenceKind, ProfilePreference


def of_kind(rows: Iterable[ProfilePreference], kind: PreferenceKind) -> list[str]:
    """Тексты строк одного вида — в порядке анкеты."""
    return [row.text for row in rows if row.kind == kind]


def merged_preferences(
    kept: list[tuple[PreferenceKind, str]], parsed: list[tuple[PreferenceKind, str]]
) -> list[tuple[PreferenceKind, str]]:
    """Лежащие строки и за ними новые из резюме — те, чьего текста ещё нет.

    Лежащие не стираются: их заводит и размечает человек, резюме о
    предпочтениях чаще молчит, и снесённый запрет пропустил бы то, что
    человек отсёк.
    """
    known = {text.casefold() for _, text in kept}
    return kept + [(kind, text) for kind, text in parsed if text.casefold() not in known]
