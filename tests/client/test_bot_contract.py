"""Шов имён между мостом и ботом.

Мост зовёт бота по именам, а проверки моста поднимают вместо него подделку
(`tests/fakes/ui_bot.py`). Пока имена совпадают, подделка работает; разойдись
они — проверки останутся зелёными, а окно в бою упрётся в `AttributeError` на
первом же нажатии.

Тот же шов между страницей и мостом сторожит `test_page_contract.py`; здесь —
вторая его половина, со стороны питона. Смотрят на объявления нарочно: сам зов
происходит в бою, и наблюдать тут нечего, кроме совпадения имён.
"""

import ast
import inspect
from pathlib import Path
from typing import get_args

import pytest

from backend.bot import client as client_mod
from backend.bot.client import Bot
from backend.bot.pasted import PastedOutcome
from backend.bot.rerun import RerunOutcome
from backend.flows.hand_outcome import HandOutcome
from client.bridge import lifespan
from client.bridge.refusals import PASTED_REFUSALS, RERUN_REFUSALS, agent_refusals
from tests.fakes.ui_bot import ANSWERS, UiBot


BRIDGE = Path(__file__).resolve().parents[2] / "client" / "bridge"


def _is_the_bot(node: ast.expr) -> bool:
    """Это обращение к боту, а не к чему-то другому по дороге.

    Бот приезжает и сам по себе, и полем хозяйства (`self._hub.bot`), поэтому
    смотрится хвост цепочки, а не только голое имя.
    """
    return (isinstance(node, ast.Name) and node.id == "bot") or (
        isinstance(node, ast.Attribute) and node.attr == "bot"
    )


def _touched_on_the_bot() -> set[str]:
    """Всё, что мост берёт у бота: и зовы, и переданное ссылкой.

    Разбором, а не поиском по строкам. Строчный поиск ошибается здесь в обе
    стороны сразу: берёт `bot.chat` из докстроки, которой в бою нет вовсе, и
    не видит имени, отданного без скобок, — а именно так уезжают
    `force_poll_once` и `log_out_session`, оба в чужие руки и оба мимо шва.
    """
    found: set[str] = set()
    for source in BRIDGE.rglob("*.py"):
        for node in ast.walk(ast.parse(source.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Attribute) and _is_the_bot(node.value):
                found.add(node.attr)
    return found


def _asked_of_the_bot() -> list[str]:
    """Имена, которыми мост зовёт бота — из его собственного исходника.

    Не из подделки: перечень, взятый у подделки, сторожит только то, что в нём
    уже есть. Зов, которого подделка не знает, выпадал из шва целиком — и именно
    такие зовы и опасны: в прогоне их не исполняет никто.

    Крючки окна сюда не идут: у них правило обратное — их бот объявляет, а не
    исполняет, — и стережёт их сторож ниже.
    """
    return sorted(one for one in _touched_on_the_bot() if not one.startswith("on_"))


def _hooks_set_in(what) -> set[str]:
    """Крючки окна, которым это тело что-то присваивает.

    Оба перечня — и тот, что заполняет окно, и тот, что объявляет бот, —
    читаются одним способом: другого объявления ни у одного из них нет,
    оба живут присвоениями в теле. Порознь этот разбор расходился бы молча,
    и сторож сравнивал бы найденное одним способом с найденным другим.
    """
    return {
        line.split("bot.", 1)[1].split(" =", 1)[0].strip()
        for line in inspect.getsource(what).splitlines()
        if line.strip().startswith("bot.on_")
    }


def test_there_is_something_to_guard_at_all():
    """Все три перечня непусты — иначе сторож молчал бы ни о чём."""
    assert _asked_of_the_bot()
    assert _hooks_set_in(lifespan._tell_the_window)
    assert _hooks_the_bot_declares()


@pytest.mark.parametrize("name", _asked_of_the_bot())
def test_the_bot_answers_to_the_name_the_bridge_calls(name):
    """У бота есть каждое имя, которое мост зовёт через подделку."""
    assert hasattr(Bot, name), f"мост зовёт {name!r}, а у бота его нет"


def _hooks_the_bot_declares() -> set[str]:
    """Крючки, которые бот заводит у себя пустыми."""
    return _hooks_set_in(client_mod._declare_ui_hooks)


@pytest.mark.parametrize("name", sorted(_hooks_set_in(lifespan._tell_the_window)))
def test_the_bot_declares_every_hook_the_window_fills(name):
    """Бот объявляет каждый крючок, в который вписывается окно.

    Вписаться можно и в неизвестное поле — python не возразит, — и тогда окно
    молча не получит ни одного события этого рода.
    """
    assert name in _hooks_the_bot_declares(), (
        f"окно вписывается в {name!r}, а бот его не объявляет"
    )


@pytest.mark.parametrize("name", _asked_of_the_bot())
def test_the_fake_answers_to_the_name_the_bridge_calls(name):
    """И у подделки есть каждое имя, которым мост зовёт бота.

    Недостающее имя значит, что проверка моста, дошедшая до этого зова,
    упрётся в `AttributeError` вместо ответа. Исполнять зов шов не обещает:
    он сводит имена, а какие из них исполняются в прогоне — дело самих проверок.
    """
    assert hasattr(UiBot, name), f"мост зовёт {name!r}, а у подделки его нет"


def _rerun_outcomes() -> set[str]:
    """Чем повторный разбор может кончиться по объявлению бота."""
    return set(get_args(RerunOutcome))


def test_every_rerun_outcome_has_a_phrase_for_the_human():
    """У каждого исхода повторного разбора есть своя фраза человеку.

    Исходы заводит бэкенд, а переводит их в слова мост, и новый там появляется
    раньше перевода здесь. Непереведённый доедет до человека запасной фразой
    «не удалось — см. логи» на том, что могло кончиться внятно: у вакансии нет
    текста, модель не поднялась, прогон отменили.
    """
    # Сравнение целиком, а не включение: лишняя фраза — такая же беда,
    # только молчаливая с другой стороны: переименуй исход на бэкенде — и
    # старый перевод остался бы здесь навечно, а новый исход шёл бы запасной фразой.
    assert _rerun_outcomes() - {"ok"} == set(RERUN_REFUSALS)


def test_the_fake_answers_the_rerun_with_an_outcome_the_bot_can_return():
    """Заготовленный ответ подделки — из тех же исходов, что и у бота.

    Иначе проверки моста ходили бы по переводу, которого в бою не бывает, а
    настоящий исход шёл бы мимо перевода — и оба конца были бы зелены.
    """
    assert ANSWERS["rerun"] in _rerun_outcomes()


def _pasted_outcomes() -> set[str]:
    """Чем работа заведения может кончиться по объявлению бота."""
    return set(get_args(PastedOutcome))


def _hand_made_outcomes() -> set[str]:
    """Чем кончается само ручное заведение — это окно слышит вестью по ходу."""
    return set(get_args(HandOutcome))


def test_every_pasted_outcome_has_a_phrase_for_the_human():
    """У каждого исхода ручного заведения есть своя фраза человеку.

    Тот же шов, что и у повторного разбора, и та же беда без него: исход
    заводит бэкенд, а переводит мост, и непереведённый доедет запасным «не
    удалось завести» на том, что кончилось внятно — вакансия уже существует,
    статья не скачалась, молчит модель отпечатков. «Сказано» и удача фразы не
    требуют: первое значит, что исход уже ушёл вестью, второе — слово удачи.
    """
    said = _pasted_outcomes() | _hand_made_outcomes()
    assert said - {"ok", "told"} == set(agent_refusals(PASTED_REFUSALS, None))


def test_the_fake_answers_the_pasted_intake_with_an_outcome_the_bot_can_return():
    """Заготовленный ответ подделки — из тех же исходов, что и у бота."""
    assert ANSWERS["pasted"] in _pasted_outcomes()
