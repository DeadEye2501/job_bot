"""Таблица процессов мака по `ps`: номер, номер родителя и один столбец."""

import subprocess


def process_table(column: str) -> list[tuple[int, int, str]]:
    """Все процессы системы: номер, номер родителя и значение столбца `column` у `ps`.

    Столбец идёт последним и делится не дальше второго пробела: в пути к
    программе и во времени старта пробелы свои.
    """
    out = subprocess.run(
        ["ps", "-A", "-o", f"pid=,ppid=,{column}="], capture_output=True, text=True, check=True,
    ).stdout
    rows = []
    for line in out.splitlines():
        pid, parent, value = line.split(None, 2)
        rows.append((int(pid), int(parent), value.strip()))
    return rows
