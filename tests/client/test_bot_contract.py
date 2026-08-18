"""Шов имён между мостом и ботом.

Мост зовёт бота по именам, а проверки моста поднимают вместо него подделку
(`tests/fakes/ui_bot.py`). Пока имена совпадают, подделка работает; разойдись
они — проверки останутся зелёными, а окно в бою упрётся в `AttributeError` на
первом же нажатии.

Тот же шов между страницей и мостом сторожит `test_page_contract.py`; здесь —
вторая его половина, со стороны питона. Смотрят на объявления нарочно: сам зов
происходит в бою, и наблюдать тут нечего, кроме совпадения имён.
"""

import inspect

import pytest

from backend.bot import client as client_mod
from backend.bot.client import Bot
from client.bridge import lifespan
from tests.fakes.ui_bot import UiBot


def _asked_of_the_bot() -> list[str]:
    """Имена, которые подделка обещает мосту вместо бота."""
    return [
        name
        for name, _ in inspect.getmembers(UiBot, callable)
        if not name.startswith("_")
    ]


def _hooks_the_window_fills() -> list[str]:
    """Крючки, в которые окно вписывает свои отклики.

    Читаются из тела `_tell_the_window`: оно присваивает их литералами, и
    другого перечня у них нет.
    """
    source = inspect.getsource(lifespan._tell_the_window)
    return sorted(
        {
            line.split("bot.", 1)[1].split(" =", 1)[0].strip()
            for line in source.splitlines()
            if line.strip().startswith("bot.on_")
        }
    )


def test_there_is_something_to_guard_at_all():
    """Все три перечня непусты — иначе сторож молчал бы ни о чём."""
    assert _asked_of_the_bot()
    assert _hooks_the_window_fills()
    assert _hooks_the_bot_declares()


@pytest.mark.parametrize("name", _asked_of_the_bot())
def test_the_bot_answers_to_the_name_the_bridge_calls(name):
    """У бота есть каждое имя, которое мост зовёт через подделку."""
    assert hasattr(Bot, name), f"мост зовёт {name!r}, а у бота его нет"


def _hooks_the_bot_declares() -> set[str]:
    """Крючки, которые бот заводит у себя пустыми."""
    source = inspect.getsource(client_mod._declare_ui_hooks)
    return {
        line.split("bot.", 1)[1].split(" =", 1)[0].strip()
        for line in source.splitlines()
        if line.strip().startswith("bot.on_")
    }


@pytest.mark.parametrize("name", _hooks_the_window_fills())
def test_the_bot_declares_every_hook_the_window_fills(name):
    """Бот объявляет каждый крючок, в который вписывается окно.

    Вписаться можно и в неизвестное поле — python не возразит, — и тогда окно
    молча не получит ни одного события этого рода.
    """
    assert name in _hooks_the_bot_declares(), (
        f"окно вписывается в {name!r}, а бот его не объявляет"
    )
