"""Следствия запуска приложения из единственной точки входа.

Порядок трёх шагов здесь не случаен и весь про то, чтобы не потерять данные.
Хранилище ключей проверяется первым: с небезопасным или сломанным секреты
уходят на диск открытым текстом либо теряются после первого же запуска — окно
поднимать уже поздно, и отказ выходит текстом в поток ошибок.

Схема базы обновляется вторым, до окна: обновление поднимает собственный цикл
событий, и внутри чужого оно не запустится.

Отказ на первом шаге даёт свой код возврата, отличный от обычного: запуск из
командной строки должен уметь отличить «не смог начать» от «отработал и
вышел».
"""

import pytest

import main as entry


@pytest.fixture
def steps(monkeypatch):
    """Подменяет три шага запуска и записывает их порядок."""
    order: list[str] = []

    def check_keyring():
        order.append("хранилище ключей")

    def ensure_schema():
        order.append("схема базы")

    def run_ui():
        order.append("окно")
        return 0

    monkeypatch.setattr(
        "backend.runtime_settings._check_keyring_backend", check_keyring
    )
    monkeypatch.setattr("backend.bootstrap.ensure_schema", ensure_schema)
    monkeypatch.setitem(
        __import__("sys").modules,
        "client.shell",
        type("Shell", (), {"run_ui": staticmethod(run_ui)}),
    )
    return order


def test_the_launch_goes_through_all_three_steps(steps):
    """Запуск проходит проверку ключей, схему базы и открывает окно."""
    assert entry.main() == 0
    assert steps == ["хранилище ключей", "схема базы", "окно"]


def test_the_schema_is_updated_before_the_window(steps):
    """Схема базы обновляется до окна.

    Обновление поднимает собственный цикл событий; внутри уже
    запущенного оконного цикла оно не стартует вовсе.
    """
    entry.main()

    assert steps.index("схема базы") < steps.index("окно")


def test_a_broken_key_store_stops_the_launch(steps, monkeypatch, capsys):
    """Небезопасное хранилище ключей запуск останавливает.

    С ним секреты ушли бы на диск открытым текстом. Окна ещё нет, и
    показать беду можно только текстом в поток ошибок.
    """

    def refuse():
        raise RuntimeError("хранилище пишет пароли открытым текстом")

    monkeypatch.setattr("backend.runtime_settings._check_keyring_backend", refuse)

    assert entry.main() == 2
    assert steps == []
    assert "хранилище пишет пароли открытым текстом" in capsys.readouterr().err


def test_the_window_return_code_is_passed_through(steps, monkeypatch):
    """Код возврата окна передаётся наружу как есть.

    По нему запускающий отличает нормальный выход от аварийного.
    """
    monkeypatch.setitem(
        __import__("sys").modules,
        "client.shell",
        type("Shell", (), {"run_ui": staticmethod(lambda: 3)}),
    )

    assert entry.main() == 3
