"""Следствия запуска приложения из единственной точки входа.

Порядок трёх шагов здесь не случаен и весь про то, чтобы не потерять данные.
Хранилище ключей проверяется первым: с небезопасным или сломанным секреты
уходят на диск открытым текстом либо теряются после первого же запуска.

Схема базы обновляется вторым, до окна: обновление поднимает собственный цикл
событий, и внутри чужого оно не запустится.

Отказ на этом пути даёт свой код возврата, отличный от обычного: запуск из
командной строки должен уметь отличить «не смог начать» от «отработал и
вышел». Показать беду человеку можно только окном системы — в оконной сборке
нет ни консоли, ни потока ошибок.

Журнал и необработанные падения — предмет соседа, `test_entry_point_log.py`.
"""

import sqlite3
import sys

import pytest


@pytest.fixture
def shown(monkeypatch):
    """Что показали человеку окном системы, когда своего окна ещё нет."""
    said: list[str] = []
    monkeypatch.setattr(
        "client.trouble_box.show_trouble", lambda text: said.append(text)
    )
    return lambda: " ".join(said)


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


def test_a_second_copy_does_not_start(entry, capsys, monkeypatch):
    """Вторая копия не начинает работу, а просит показать уже открытое окно.

    Замок берётся до всех шагов: обе копии делят файл журнала, а тот
    поворачивается переименованием — после первой же ротации одна из копий
    пишет в переименованный файл, который сотрут следующей.

    Человеку при этом не говорится ничего: он нажал ярлык, ожидая окна, а не
    объяснений, и показать их всё равно негде — в оконной сборке нет ни
    консоли, ни потока ошибок. Молчание здесь проверяется наравне с просьбой:
    сообщение, ушедшее в никуда, выглядело бы работающим.

    Код возврата свой: запускающему из командной строки «уже запущено» — не то
    же, что «отработал и вышел», и не то же, что сломанное хранилище ключей.
    """
    module, order = entry
    from backend.single_instance import hold_the_only_copy

    asked: list[bool] = []
    monkeypatch.setattr(
        "client.raise_window.ask_to_raise", lambda: asked.append(True)
    )
    first = hold_the_only_copy(module.get_lock_path())

    assert module.main() == 3
    assert order == []
    assert asked == [True]
    assert capsys.readouterr().err == ""

    first.close()


def test_the_lock_is_let_go_when_the_window_closes(entry):
    """Закрытое окно замок отпускает.

    Иначе второй запуск после штатного выхода упирался бы в самого себя —
    замок сняла бы только перезагрузка.
    """
    module, _ = entry
    from backend.single_instance import hold_the_only_copy

    module.main()

    after_the_window = hold_the_only_copy(module.get_lock_path())

    assert after_the_window is not None
    after_the_window.close()


def test_a_broken_key_store_stops_the_launch(entry, monkeypatch, shown):
    """Небезопасное хранилище ключей запуск останавливает и говорит об этом.

    С ним секреты ушли бы на диск открытым текстом. Окна ещё нет, и в оконной
    сборке нет ни консоли, ни потока ошибок — сказать можно только окном
    системы.
    """
    module, order = entry

    def refuse():
        raise RuntimeError("хранилище пишет пароли открытым текстом")

    monkeypatch.setattr("backend.crypto._check_keyring_backend", refuse)

    assert module.main() == 2
    assert order == []
    assert "хранилище пишет пароли открытым текстом" in shown()


def test_a_launch_that_broke_before_the_window_is_shown_to_the_person(
    entry, monkeypatch, shown
):
    """Всякая беда до окна показывается человеку, а не только известная.

    До окна стоят четыре работы, и ни одна не была прикрыта: любая превращала
    нажатие на ярлык в «ничего не произошло», и повторялось это столько раз,
    сколько человек нажмёт. Догадаться заглянуть в журнал мог только тот, кто
    писал приложение.
    """
    module, order = entry

    def broken():
        raise sqlite3.DatabaseError("файл базы повреждён")

    monkeypatch.setattr("backend.bootstrap.ensure_schema", broken)

    assert module.main() == 2
    assert order == ["хранилище ключей"]
    assert "файл базы повреждён" in shown()


def test_the_window_return_code_is_passed_through(entry, monkeypatch):
    """Код возврата окна передаётся наружу как есть.

    По нему запускающий отличает нормальный выход от аварийного.
    """
    module, _ = entry
    monkeypatch.setitem(
        sys.modules,
        "client.window",
        type("Window", (), {"run_ui": staticmethod(lambda: 3)}),
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
