"""Итоги и отказы, которые окно показывает человеку строкой или плашкой, — без
точки на конце: одним видом на всё окно. Внутренние точки в сообщении из
нескольких фраз остаются."""

import ast
from pathlib import Path

from backend.bot import work
from client.bridge import refusals

BRIDGE = Path(refusals.__file__).parent
LAUNCHERS = {"launched", "launched_on_bot", "_launch"}


def _texts_of(module) -> list[str]:
    """Строки модуля и значения его наборов: фразы, которые уходят в окно."""
    texts = []
    for name, value in vars(module).items():
        if name.startswith("_"):
            continue
        if isinstance(value, str):
            texts.append(value)
        elif isinstance(value, dict):
            texts += [one for one in value.values() if isinstance(one, str)]
    return texts


def _launch_texts() -> list[str]:
    """Строки, которые мост передаёт в пущенную работу: итог «готово» среди них."""
    texts = []
    for path in BRIDGE.glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Call) and getattr(node.func, "attr", getattr(node.func, "id", "")) in LAUNCHERS:
                texts += [arg.value for arg in node.args
                          if isinstance(arg, ast.Constant) and isinstance(arg.value, str)]
    return texts


def test_no_refusal_or_run_note_ends_with_a_dot():
    ending = [text for text in _texts_of(refusals) + _texts_of(work) if text.endswith(".")]

    assert ending == []


def test_no_action_outcome_of_the_bridge_ends_with_a_dot():
    assert [text for text in _launch_texts() if text.endswith(".")] == []
