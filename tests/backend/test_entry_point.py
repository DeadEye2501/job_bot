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

import sys

import pytest


@pytest.fixture
def entry(clean_root_logger, monkeypatch):
    """Точка входа с подменёнными шагами запуска и возвращённым журналом.

    Ввозится она внутри фикстуры нарочно: при ввозе модуль насовсем правит
    корневой logger — вешает обработчик буфера, фильтр вымарывания секретов
    и меняет уровни уже навешенных обработчиков, включая тот, которым
    pytest ловит записи. На сборке это испортило бы журнал всему прогону.
    """
    import main as module

    order: list[str] = []

    def check_keyring():
        order.append("хранилище ключей")

    def ensure_schema():
        order.append("схема базы")

    def run_ui():
        order.append("окно")
        return 0

    monkeypatch.setattr(
        "backend.crypto._check_keyring_backend", check_keyring
    )
    monkeypatch.setattr("backend.bootstrap.ensure_schema", ensure_schema)
    monkeypatch.setitem(
        sys.modules, "client.shell", type("Shell", (), {"run_ui": staticmethod(run_ui)})
    )
    return module, order


def test_the_launch_goes_through_all_three_steps(entry):
    """Запуск проходит проверку ключей, схему базы и открывает окно."""
    module, order = entry

    assert module.main() == 0
    assert order == ["хранилище ключей", "схема базы", "окно"]


def test_the_schema_is_updated_before_the_window(entry):
    """Схема базы обновляется до окна.

    Обновление поднимает собственный цикл событий; внутри уже
    запущенного оконного цикла оно не стартует вовсе.
    """
    module, order = entry

    module.main()

    assert order.index("схема базы") < order.index("окно")


def test_a_broken_key_store_stops_the_launch(entry, monkeypatch, capsys):
    """Небезопасное хранилище ключей запуск останавливает.

    С ним секреты ушли бы на диск открытым текстом. Окна ещё нет, и
    показать беду можно только текстом в поток ошибок.
    """
    module, order = entry

    def refuse():
        raise RuntimeError("хранилище пишет пароли открытым текстом")

    monkeypatch.setattr("backend.crypto._check_keyring_backend", refuse)

    assert module.main() == 2
    assert order == []
    assert "хранилище пишет пароли открытым текстом" in capsys.readouterr().err


def test_the_window_return_code_is_passed_through(entry, monkeypatch):
    """Код возврата окна передаётся наружу как есть.

    По нему запускающий отличает нормальный выход от аварийного.
    """
    module, _ = entry
    monkeypatch.setitem(
        sys.modules,
        "client.shell",
        type("Shell", (), {"run_ui": staticmethod(lambda: 3)}),
    )

    assert module.main() == 3


def test_a_console_that_refuses_utf8_is_reported(entry, monkeypatch, capsys):
    """Отказ консоли перейти на UTF-8 показывается, а не проглатывается."""
    module, _ = entry

    def refuses(**_kwargs):
        raise OSError("консоль не отдаёт кодировку")

    # Подменяется один вызов, а не весь поток вывода: подмена потока пережила
    # бы тест и оставила бы прогон писать в мёртвый буфер.
    monkeypatch.setattr(sys.stdout, "reconfigure", refuses, raising=False)

    module._use_utf8_stdout()

    assert "консоль не отдаёт кодировку" in capsys.readouterr().err
