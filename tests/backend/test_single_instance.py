"""Следствия сторожа единственности приложения.

Двум копиям здесь тесно не вообще, а по конкретным местам: обе пишут один файл
журнала и одну базу. Журнал ротируется — переименованием файла, который вторая
копия держит открытым, — и после первой же ротации одна из копий пишет в
никуда: файл переименован, дескриптор указывает на прежний.

Замок взят файловый, а не отметкой с номером процесса: отметку убитая копия
оставляет за собой навсегда, и следующий запуск упирается в мертвеца. Файловый
замок операционная система снимает сама, чем бы копия ни кончилась.
"""

import subprocess
import sys
import time
from pathlib import Path

from backend.single_instance import hold_the_only_copy


def _lock_once_it_is_free(lock_path: Path, seconds: float = 5.0):
    """Дождаться освобождения замка и взять его.

    Ждать приходится потому, что снимает его не наш код: дескрипторы умершего
    процесса закрывает операционная система, и делает она это не в тот же миг,
    когда процесс перестал существовать. Без ожидания проверка была бы
    плавающей — зелёной на быстрой машине и красной на занятой.
    """
    deadline = time.monotonic() + seconds
    while True:
        held = hold_the_only_copy(lock_path)
        if held is not None or time.monotonic() > deadline:
            return held
        time.sleep(0.05)


def test_the_first_copy_takes_the_lock(tmp_path: Path):
    """Первая копия замок получает — иначе приложение не запускалось бы вовсе."""
    held = hold_the_only_copy(tmp_path / "jobbot.lock")

    assert held is not None
    held.close()


def test_a_second_copy_is_refused(tmp_path: Path):
    """Пока первая держит замок, вторая его не получает.

    Ради этого сторож и заведён: две копии делят файл журнала и базу.
    """
    lock = tmp_path / "jobbot.lock"
    first = hold_the_only_copy(lock)

    assert hold_the_only_copy(lock) is None

    first.close()


def test_the_lock_is_free_once_the_copy_lets_it_go(tmp_path: Path):
    """Отпущенный замок берётся следующим запуском.

    Штатный выход не должен запирать приложение до перезагрузки.
    """
    lock = tmp_path / "jobbot.lock"
    hold_the_only_copy(lock).close()

    second = hold_the_only_copy(lock)

    assert second is not None
    second.close()


def test_a_lock_that_cannot_be_taken_does_not_stop_the_launch(tmp_path: Path):
    """Не открывшийся файл замка запуск не отменяет.

    Осечка сторожа — это «сторожить нечем», а не «работать нельзя». Отказ
    здесь превратил бы снятый кем-то атрибут файла в неработающее приложение,
    и починить это человек мог бы только удалением файла, о котором не знает.

    Каталог на месте файла — самый простой отказ открытия, который можно
    устроить одинаково на всех системах.
    """
    instead_of_a_file = tmp_path / "jobbot.lock"
    instead_of_a_file.mkdir()

    with hold_the_only_copy(instead_of_a_file):
        pass


def test_a_killed_copy_does_not_keep_the_lock(tmp_path: Path):
    """Убитая копия замка за собой не оставляет.

    Проверяется настоящим вторым процессом, потому что именно ради него всё и
    написано, и снимает замок не наш код, а операционная система: отметкой с
    номером процесса это место не закрылось бы — прибитая копия оставила бы её
    лежать, и следующий запуск упёрся бы в мертвеца.
    """
    lock = tmp_path / "jobbot.lock"
    holder = subprocess.Popen(
        [
            sys.executable,
            "-c",
            "import sys, time; sys.path.insert(0, sys.argv[1]);"
            " from backend.single_instance import hold_the_only_copy;"
            " held = hold_the_only_copy(sys.argv[2]);"
            " print('taken' if held else 'refused', flush=True);"
            " time.sleep(30)",
            str(Path(__file__).resolve().parents[2]),
            str(lock),
        ],
        stdout=subprocess.PIPE,
        text=True,
    )
    try:
        assert holder.stdout.readline().strip() == "taken"
        assert hold_the_only_copy(lock) is None
    finally:
        holder.kill()
        holder.wait(timeout=10)
        holder.stdout.close()

    after_the_kill = _lock_once_it_is_free(lock)

    assert after_the_kill is not None
    after_the_kill.close()
