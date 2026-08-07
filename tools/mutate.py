"""Точечные мутации: сломать одну строку, прогнать тесты, откатить.

Запасной путь: `mutmut 3.7.0` на Windows отказывается запускаться вообще —
`mutmut --help` и `mutmut run` падают с "To run mutmut on Windows, please
use the WSL" ещё до разбора аргументов (см. task-6-report.md). Ломает не
наугад: список поломок задаётся руками и содержит то, что легко испортить
случайно — снятый флаг, перевёрнутое сравнение, перепутанный ключ, суженный
диапазон.
"""

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


def run_tests(test_path: str) -> bool:
    done = subprocess.run(
        [sys.executable, "-m", "pytest", test_path, "-q", "-x"],
        capture_output=True,
    )
    return done.returncode == 0


def main() -> int:
    test_path = sys.argv[1]
    silent = []
    for name, before, after in MUTATIONS:
        path = Path(name)
        # newline="" — иначе Windows на записи переводит \n в \r\n, и
        # восстановленный файл байт-в-байт отличается от исходного
        # (обнаружено на живом прогоне: git status показал М после «отката»).
        original = path.read_text(encoding="utf-8", newline="")
        if before not in original:
            print(f"НЕ НАЙДЕНО: {name}: {before!r}")
            continue
        path.write_text(original.replace(before, after, 1), encoding="utf-8", newline="")
        try:
            if run_tests(test_path):
                silent.append((name, before, after))
                print(f"МОЛЧА ПРОШЛА: {name}: {before!r} -> {after!r}")
            else:
                print(f"поймана: {name}: {before!r}")
        finally:
            path.write_text(original, encoding="utf-8", newline="")
    print(f"\nвсего поломок: {len(MUTATIONS)}, прошло молча: {len(silent)}")
    return 1 if silent else 0


if __name__ == "__main__":
    raise SystemExit(main())
