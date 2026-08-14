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


def _strings(module: str, name: str) -> list[str]:
    """Строки перечня в порядке объявления."""
    return re.findall(r"'([^']*)'", _array(module, name))


def _values(module: str, name: str) -> list[str]:
    """Значения перечня, объявленного парами «значение — подпись»."""
    return re.findall(r"value: '([^']*)'", _array(module, name))


def test_statuses_match() -> None:
    """Порядок у окна свой — по воронке, от «новой» к исходам: в нём читают
    кольцо статистики и чипы отбора. Сверяется состав, а не порядок."""
    shown = _strings("stats.js", "STATUS_ORDER")
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
    kinds = re.findall(r"key: '([^']*)'", _array("contacts.js", "BLACKLIST_KINDS"))
    assert kinds[0] == ""
    assert sorted(kinds[1:]) == sorted(BLACKLIST_KINDS)
