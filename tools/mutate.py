"""Точечные мутации: сломать одну строку, прогнать тесты, откатить.

Запасной путь: `mutmut 3.7.0` на Windows отказывается запускаться вообще —
`mutmut --help` и `mutmut run` падают с "To run mutmut on Windows, please
use the WSL" ещё до разбора аргументов. `mutmut 2.4.5` стартует в
одноразовом окружении (см. task-6-report.md) — решение по нему отдельное.
Ломает не наугад: список поломок задаётся руками и содержит то, что легко
испортить случайно — снятый флаг, перевёрнутое сравнение, перепутанный
ключ, суженный диапазон.

Снимок каждого мутируемого файла читается один раз до цикла и хранится
байтами (`read_bytes`/`write_bytes` — точность не зависит от того, что
кодирование и декодирование UTF-8 обратны друг другу, и от перевода строк).
После каждого восстановления и ещё раз в конце файл сверяется с этим
снимком байт-в-байт; расхождение — фатальная ошибка, а не тихий переход
к следующей мутации.

Снимок живёт только в памяти работающего процесса, поэтому смерть
интерпретатора между записью мутации и восстановлением оставила бы боевой
файл сломанным, и на диске не было бы ничего, из чего его вернуть. Отсюда
предполётная проверка: мутируемые файлы обязаны быть чистыми по
`git status`. Тогда `git restore` — всегда верное и однозначное
восстановление, а оператор не спутает порчу с собственной незакоммиченной
работой. Эту же команду инструмент печатает на каждом аварийном выходе.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

# Консоль по умолчанию тут в cp1251 — «↪» и часть кириллицы не кодируются,
# без этого print падает на середине списка мутаций.
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# (файл, что заменить, на что заменить) — по одной осмысленной поломке.
MUTATIONS = [
    # extract_text: пропадает запасной вариант через caption
    (
        "backend/helpers.py",
        'return (msg.text or msg.caption or "").strip()',
        'return (msg.text or "").strip()',
    ),
    # _media_placeholder: ветка «Фото» никогда не срабатывает
    (
        "backend/helpers.py",
        'if getattr(msg, "photo", None):\r\n        return "[Фото]"',
        'if False:\r\n        return "[Фото]"',
    ),
    # _media_placeholder: ветка «Документ» никогда не срабатывает
    (
        "backend/helpers.py",
        'if getattr(msg, "document", None):\r\n        return "[Документ]"',
        'if False:\r\n        return "[Документ]"',
    ),
    # extract_dm_text: голосовое больше не распознаётся
    (
        "backend/helpers.py",
        'body = extract_text(msg)\r\n    if getattr(msg, "voice", None):',
        "body = extract_text(msg)\r\n    if False:",
    ),
    # extract_dm_text: подпись голосового теряется
    (
        "backend/helpers.py",
        'body = f"Голосовое сообщение: {body}" if body else "Голосовое сообщение"',
        'body = "Голосовое сообщение"',
    ),
    # extract_dm_text: перевёрнутая проверка родителя
    (
        "backend/helpers.py",
        "if parent is None:\r\n        return body",
        "if parent is not None:\r\n        return body",
    ),
    # extract_dm_text: переводы строк в цитате не схлопываются
    (
        "backend/helpers.py",
        'quote = quote.replace("\\n", " ").strip()',
        "quote = quote.strip()",
    ),
    # extract_dm_text: порог обрезки цитаты расширен на порядок
    (
        "backend/helpers.py",
        "if len(quote) > 80:",
        "if len(quote) > 800:",
    ),
    # extract_dm_text: пустое тело больше не даёт «голую» цитату
    (
        "backend/helpers.py",
        'return f"↪ {quote}\\n\\n{body}" if body else f"↪ {quote}"',
        'return f"↪ {quote}\\n\\n{body}"',
    ),
    # normalize_username: http:// перестаёт распознаваться
    (
        "backend/helpers.py",
        'for prefix in ("https://", "http://"):',
        'for prefix in ("https://",):',
    ),
    # normalize_username: префикс t.me/ не снимается
    (
        "backend/helpers.py",
        'if s.startswith("t.me/"):\r\n        s = s[len("t.me/"):]',
        'if False:\r\n        s = s[len("t.me/"):]',
    ),
    # normalize_username: хвостовой слэш не срезается
    (
        "backend/helpers.py",
        's = s.lstrip("@").strip().rstrip("/")',
        's = s.lstrip("@").strip()',
    ),
    # normalize_username: при лишнем сегменте пути берётся не тот кусок
    (
        "backend/helpers.py",
        'if "/" in s:\r\n        s = s.split("/", 1)[0]',
        'if "/" in s:\r\n        s = s.split("/", 1)[-1]',
    ),
    # normalize_username: телефоны с «+» больше не отсеиваются
    (
        "backend/helpers.py",
        'if not s or s.startswith("+"):',
        "if not s:",
    ),
    # normalize_username: служебные пути Telegram (joinchat/c/...) не отсеиваются
    (
        "backend/helpers.py",
        "if s.lower() in _TG_RESERVED_PATHS:",
        "if False:",
    ),
    # fetch_telegram_avatar: перепутан приоритет small/big file_id
    (
        "backend/helpers.py",
        'file_id = getattr(photo, "small_file_id", None) or getattr(photo, "big_file_id", None)',
        'file_id = getattr(photo, "big_file_id", None) or getattr(photo, "small_file_id", None)',
    ),
    # resolve_hr_telegram: удалённый аккаунт больше не отсеивается
    (
        "backend/helpers.py",
        'if getattr(user, "is_bot", False) or getattr(user, "is_deleted", False):',
        'if getattr(user, "is_bot", False):',
    ),
]


def _child_env() -> dict[str, str]:
    """Окружение для pytest в подпроцессе."""
    env = dict(os.environ)
    # Кэш байткода CPython считает `.pyc` свежим по времени правки исходника
    # в целых секундах плюс его размеру. Мутация small_file_id → big_file_id
    # длину файла не меняет, а прогон укладывается в секунду — дочерний
    # процесс успел бы взять старый `.pyc`, мутация не подействовала бы, а
    # инструмент отчитался бы «поймана». Ложное «поймана» — единственный
    # вывод, которого этот инструмент не имеет права давать: весь проход
    # существует ради проверки тестов, писавшихся без красной фазы.
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    # Без этого дочерний pytest пишет в трубу локальной кодировкой (cp1251)
    # и со strict-обработкой ошибок: докстринги проверок с «↪» или тире
    # обрывают его вывод `UnicodeEncodeError`'ом на середине. А это ровно
    # тот вывод, по которому оператор разбирает выжившего мутанта.
    # Родительская сторона декодирует явно тем же utf-8 (см. `run_tests`).
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def run_tests(test_path: str) -> tuple[bool, str]:
    done = subprocess.run(
        [sys.executable, "-m", "pytest", test_path, "-q", "-x"],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        env=_child_env(),
    )
    return done.returncode == 0, done.stdout + done.stderr


def drop_bytecode_cache(names: list[str]) -> None:
    """Сносит `__pycache__` мутируемых модулей.

    `PYTHONDONTWRITEBYTECODE` не даёт писать новые `.pyc`, но уже лежащий
    рядом устаревший всё равно был бы прочитан. Достаточно одного раза до
    цикла: писать их дальше уже некому.
    """
    for cache in {Path(name).resolve().parent / "__pycache__" for name in names}:
        shutil.rmtree(cache, ignore_errors=True)


def restore_command(names: list[str]) -> str:
    """Команда, которой оператор возвращает боевые файлы на место."""
    return "git restore -- " + " ".join(Path(name).as_posix() for name in names)


def dirty_files(names: list[str]) -> list[str] | None:
    """Строки `git status --porcelain` по мутируемым файлам; None — git не ответил."""
    done = subprocess.run(
        ["git", "status", "--porcelain", "--", *names],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
    )
    if done.returncode != 0:
        return None
    return [line for line in done.stdout.splitlines() if line.strip()]


def restore(path: Path, snapshot: bytes, context: str) -> None:
    """Возвращает файл к снимку; падает, если результат разошёлся байтами."""
    path.write_bytes(snapshot)
    if path.read_bytes() != snapshot:
        print(f"ФАТАЛЬНО: {path} не восстановлен байт-в-байт после {context}")
        print(f"Боевой файл сломан. Восстановить: {restore_command([str(path)])}")
        raise SystemExit(3)


def preflight(targets: list[str]) -> bool:
    """Пускать ли инструмент к боевым файлам.

    Единственная страховка от смерти интерпретатора посреди мутации —
    `git restore`, а он однозначен только пока в дереве нет незакоммиченной
    работы: иначе оператор не отличит порчу от своих правок и
    восстановлением снесёт их вместе с ней.
    """
    dirty = dirty_files(targets)
    if dirty is None:
        print("git не ответил на `git status` — отказываюсь работать.")
        print("Восстановление после аварии опирается на git, и без него")
        print("сломанный боевой файл будет неоткуда вернуть.")
        return False
    if dirty:
        print("мутируемые файлы изменены в рабочем дереве — отказываюсь работать:")
        for line in dirty:
            print(f"  {line}")
        print("\nИнструмент правит боевой исходник, и восстановление после аварии")
        print("опирается на `git restore`. Пока в дереве есть незакоммиченная")
        print("работа, отличить её от порчи невозможно. Закоммитьте или спрячьте:")
        print(f"  git stash push -- {' '.join(Path(n).as_posix() for n in targets)}")
        return False
    return True


def main() -> int:
    test_path = sys.argv[1]

    targets = sorted({name for name, _before, _after in MUTATIONS})

    if not preflight(targets):
        return 4

    # Устаревший `.pyc` перевернул бы вердикт: мутация не подействовала бы,
    # а инструмент отчитался бы «поймана». Сносим один раз до цикла.
    drop_bytecode_cache(targets)

    baseline_ok, baseline_output = run_tests(test_path)
    if not baseline_ok:
        print("тесты красные ДО мутаций — дальше нет смысла, сначала чинить набор:\n")
        print(baseline_output)
        return 2

    # Снимок каждого файла — один раз, до цикла. Он же служит эталоном
    # восстановления и на всём протяжении прогона больше не перечитывается
    # с диска: перечитывание позволило бы испорченному состоянию одной
    # итерации стать «эталоном» для следующей.
    snapshots: dict[str, bytes] = {name: Path(name).read_bytes() for name in targets}

    silent = []
    not_found = []
    ambiguous = []

    for name, before, after in MUTATIONS:
        path = Path(name)
        snapshot = snapshots[name]
        text = snapshot.decode("utf-8")
        occurrences = text.count(before)
        if occurrences == 0:
            print(f"НЕ НАЙДЕНО: {name}: {before!r}")
            not_found.append((name, before))
            continue
        if occurrences > 1:
            print(f"НЕОДНОЗНАЧНО ({occurrences}x): {name}: {before!r}")
            ambiguous.append((name, before))
            continue
        mutated = text.replace(before, after, 1).encode("utf-8")
        try:
            path.write_bytes(mutated)
            if run_tests(test_path)[0]:
                silent.append((name, before, after))
                print(f"МОЛЧА ПРОШЛА: {name}: {before!r} -> {after!r}")
            else:
                print(f"поймана: {name}: {before!r}")
        finally:
            restore(path, snapshot, f"мутации {before!r}")

    # Финальная сверка каждого затронутого файла со снимком — на случай,
    # если что-то обошло восстановление внутри цикла способом, который тут
    # не предусмотрен.
    for name, snapshot in snapshots.items():
        if Path(name).read_bytes() != snapshot:
            print(f"ФАТАЛЬНО: {name} не совпадает со снимком после прогона")
            print(f"Боевой файл сломан. Восстановить: {restore_command([name])}")
            return 3

    print(
        f"\nвсего поломок: {len(MUTATIONS)}, прошло молча: {len(silent)}, "
        f"не найдено: {len(not_found)}, неоднозначно: {len(ambiguous)}"
    )
    return 1 if (silent or not_found or ambiguous) else 0


if __name__ == "__main__":
    raise SystemExit(main())
