"""Согласие перечней окна с перечнями бэкенда.

Шесть перечней объявлены дважды: раз на питоне, раз в `client/web/state/`.
Свести их в одно объявление сегодня нечем — мост списками их не отдаёт, а
превращать константы окна в данные, приезжающие с моста, значит переписать
шесть модулей состояния и всех их потребителей. Пока этого не сделано,
расхождение ловит этот сторож: он читает объявления окна из файлов и сверяет с
питоновскими.

Расхождение здесь молчаливое и дорогое. Заведись на бэкенде новый статус —
окно не покажет его ни в отборе, ни в смене статуса, и вакансии с ним станут
недостижимы; пропади грейд — анкета перестанет его предлагать, а разбор
продолжит присылать.
"""

from __future__ import annotations

import re
from pathlib import Path

from backend.domain.taxonomy import GRADES, LANGUAGE_LEVELS, WORK_FORMATS
from backend.domain.verdict import (
    EMPTY_SKIP_REASON,
    LLM_SKIP_PREFIX,
    REFUSED_SKIP_REASON,
    TRASH_SKIP_PREFIX,
    TRUNCATED_SKIP_REASON,
    blacklist_refusal,
    decide_vacancy_status,
)
from backend.models.enums import BotMode, VacancyStatus
from backend.models.settings import BLACKLIST_KINDS

STATE = Path(__file__).resolve().parents[2] / "client" / "web" / "state"


def _array(module: str, name: str) -> str:
    """Тело объявления `const <name> = [...]` из модуля окна.

    Разбирать JavaScript целиком незачем: перечни объявлены литералами в одну
    скобку, и берётся ровно она.
    """
    source = (STATE / module).read_text(encoding="utf-8")
    found = re.search(rf"{name} = \[(.*?)\];", source, re.DOTALL)
    assert found is not None, f"в {module} не нашлось объявления {name}"
    return found.group(1)


def _object(module: str, name: str) -> str:
    """Тело объявления `const <name> = {...}` из модуля окна.

    Отдельно от перечней в квадратных скобках: словари объявлены фигурными, и
    один разбор на оба захватывал бы лишнее — в файле рядом стоят и те и другие.
    """
    source = (STATE / module).read_text(encoding="utf-8")
    found = re.search(rf"{name} = {{(.*?)}};", source, re.DOTALL)
    assert found is not None, f"в {module} не нашлось объявления {name}"
    return found.group(1)


def _strings(module: str, name: str) -> list[str]:
    """Строки перечня в порядке объявления."""
    return re.findall(r"'([^']*)'", _array(module, name))


def _values(module: str, name: str) -> list[str]:
    """Значения перечня, объявленного парами «значение — подпись»."""
    return re.findall(r"value: '([^']*)'", _array(module, name))


def _skip_reasons_the_backend_writes() -> set[str]:
    """Причины пропуска, какими их пишет сам приговор, а не переписанный список.

    Две из четырёх сочиняются на месте, литералами в теле, — их и берём у
    приговора зовом: переписанные сюда руками, они разошлись бы с ним молча.
    """
    _, low = decide_vacancy_status(score=-5, threshold=0)
    return {
        blacklist_refusal("Контур"),
        low,
        EMPTY_SKIP_REASON,
        TRUNCATED_SKIP_REASON,
        REFUSED_SKIP_REASON,
        # Мусор и отказ модели собирает разбор (`flows/parse.py`) из приставки
        # и слов модели; сами приставки объявлены рядом с приговором.
        f"{TRASH_SKIP_PREFIX}реклама",
        f"{LLM_SKIP_PREFIX}не вакансия",
    }


def test_the_window_understands_every_skip_reason_the_backend_writes() -> None:
    """Каждую причину пропуска окно узнаёт и переводит человеку.

    Приставку пишет бэкенд, а раскладывает её на слова окно — по своему
    списку приставок и по образцу оценки. Не узнанную оно показывает как
    есть: человек читает в ленте «blacklist: Контур» вместо «Отсев: Контур»,
    а при новой приставке — сырой технический код целиком.
    """
    source = (STATE / "vacancy_card.js").read_text(encoding="utf-8")
    known = set(re.findall(r"starts: '([^']*)'", source))
    known |= set(re.findall(r"startsWith\('([^']*)'\)", source))
    score = re.search(r"SCORE_SKIP = /(.+)/i;", source)
    assert score is not None, "в vacancy_card.js не нашлось образца оценки"

    for reason in _skip_reasons_the_backend_writes():
        # Образец уезжает в питон как есть: классы знаков у обоих пишутся
        # одинаково, и переводить тут нечего.
        recognised = any(reason.startswith(one) for one in known) or re.match(
            score.group(1), reason, re.IGNORECASE
        )
        assert recognised, f"окно не узнаёт причину пропуска {reason!r}"


def test_work_formats_are_the_same_on_both_screens() -> None:
    """Форматы работы у анкеты и у отбора вакансий — одни и те же значения.

    Подписи и порядок у них свои: в анкете человек описывает себя, в отборе
    ищет. Значения же уезжают на мост обоими экранами, и разойдись они —
    отбор молча перестал бы находить то, что анкета записала.
    """
    chosen = _values("vacancy_filter.js", "REMOTE_CHOICES")
    assert sorted(one for one in chosen if one) == sorted(_values("profile.js", "WORK_FORMATS"))


def test_statuses_match() -> None:
    """Порядок у окна свой — по воронке, от «новой» к исходам: в нём читают
    кольцо статистики и чипы отбора. Сверяется состав, а не порядок.

    Читаются две колонки карточки статусов, а не собранный из них порядок
    кольца: окно объявляет статусы именно ими, а кольцо сцепляет их ссылками.
    """
    shown = _strings("stats.js", "MOVING") + _strings("stats.js", "OVER")
    assert sorted(shown) == sorted(one.value for one in VacancyStatus)


def test_modes_match() -> None:
    """Порядок здесь несущий: по нему окно считает, в какую треть дорожки
    переключателя попало нажатие."""
    assert _strings("modes.js", "MODES") == [one.value for one in BotMode]


def test_grades_match() -> None:
    assert _values("profile.js", "GRADES") == list(GRADES)


def test_work_formats_match() -> None:
    assert _values("profile.js", "WORK_FORMATS") == list(WORK_FORMATS)


def test_language_levels_match() -> None:
    """Порядок у окна свой — от высшего к младшему: так их и выбирают. Сверяется
    состав, а не порядок."""
    assert sorted(_strings("profile.js", "LANG_LEVELS")) == sorted(LANGUAGE_LEVELS)


def test_blacklist_kinds_match() -> None:
    """Первый род у окна свой и пустой — «все»: им открывается экран, и на
    мосту его нет."""
    kinds = re.findall(r"key: '([^']*)'", _array("blacklist.js", "BLACKLIST_KINDS"))
    assert kinds[0] == ""
    assert sorted(kinds[1:]) == sorted(BLACKLIST_KINDS)
