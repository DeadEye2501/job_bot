# Платформенная граница и будущая сборка

Состояние на 21.10.2026: выполнено выделение Windows-кода (этап A плана).
CLI `python -m build_tools` пока не реализован. Следующий этап — macOS
на локальном Mac пользователя; Linux и CI добавляются позже.

## Где находятся системные операции

Выбор реализации выполняет `adapters.platforms.implementation(subject)`.
Модули в `adapters/platforms/` предоставляют общие точки входа по предметам.
Windows-реализации находятся в `adapters/platforms/windows/`.

| Предмет | Прежнее место | Общий вход | Windows-реализация |
| --- | --- | --- | --- |
| Поиск браузера и видимого окна | `adapters/browser.py`, `adapters/process_windows.py` | `adapters.platforms.browser` | `windows/browser.py` |
| Job Object, потомки, опции запуска CLI | `adapters/app_tied_process.py`, `adapters/claude_code_process.py` | `adapters.platforms.processes` | `windows/processes.py` |
| Разрешение npm-обёртки Claude Code | `adapters/claude_code.py` | `adapters.platforms.cli` | `windows/cli.py` |
| Открытие и выделение файлов | `client/bridge/desktop.py` | `adapters.platforms.desktop` | `windows/desktop.py` |
| WinForms, MessageBox, права фокуса, AppUserModelID | `client/window_size.py`, `client/trouble_box.py`, `client/raise_window.py`, `client/window.py` | `adapters.platforms.window` | `windows/window.py` |
| Блокировка файла | `backend/single_instance.py` | `adapters.platforms.locking` | `windows/locking.py` |
| Подмена exe и ожидание PID | `backend/updater.py` | `adapters.platforms.updater` | `windows/updater.py` |

`adapters/browser.py` сохраняет работу Playwright, профили и поведение агента.
Описание `InstalledBrowser` и имена браузеров находятся в `browser_types.py`;
публичные импорты типа, списка и `find_browser` из `adapters.browser` сохранены.
`adapters.app_tied_process`, `adapters.process_windows` и `backend.updater`
сохранены как тонкие совместимые входы.

Проверка входных схем/расширений/каталогов и оформление результата открытия
остаются в bridge. Версия, скачивание, контрольная сумма и слот обновления
остаются в backend; WinAPI подмены exe — в Windows-пакете. Чистые файловые
функции обновления вынесены в `adapters.platforms.update_files`, чтобы
Windows-адаптер не импортировал backend.

На остальных ОС пока выбирается `unsupported`: отсутствующие системные
операции явно отказывают. Поиск поддержанного браузера возвращает `None`;
ранее работавший POSIX `flock` и PATH-поиск CLI сохранены. Windows-права
фокуса и AppUserModelID там по-прежнему не требуются. Это не реализация
macOS/Linux-модулей.

## Обновления и упаковка

`can_install_update()` требует одновременно поддержки платформы и
`sys.frozen`. Проверка применяется к UI, боту, скачиванию, запуску подменщика
и режиму `--update`. На неподдержанной ОС очистка остатков ничего не удаляет,
а `--update` возвращает код 2. Windows может проверять наличие новой версии
из исходников, как прежде, но установка требует собранного приложения.

В `JobBot.spec` добавлен сбор hidden imports Windows-пакета: `importlib`
не делает его модули видимыми для статического анализа PyInstaller.
Формат Windows onefile и остальные настройки spec сохранены.

## Проверки архитектурного этапа

На Mac использовано локальное `.venv`, Python 3.13.1. Для тестов установлены
закреплённые runtime-зависимости из `Pipfile`, кроме `llama-cpp-python`
(реальный GGUF-движок заперт тестовым стендом), и pytest/pytest-asyncio/ruff.
`Pipfile` и `Pipfile.lock` не менялись. Это не готовый macOS build lock.

```sh
.venv/bin/python -m pytest -q -p no:cacheprovider --tb=short
.venv/bin/ruff check .
git diff --check
```

Часть pytest использует настоящие локальные сокеты и дочерние процессы.
Sandbox может запрещать их: такой отказ не свидетельствует об ошибке
приложения и требует разрешённого повторного прогона.

Тестовый стенд изолирует каталог данных до импорта адаптеров на любой ОС;
подпроцессы тестов журналирования получают такую же изоляцию отдельно.
Keyring подменён в памяти, обращения к Telegram/Anthropic/Claude Code и
загрузка настоящей GGUF запрещены существующими тестовыми защитами.

Фактические результаты и непроведённые Windows-проверки записаны в
[отчёте архитектурного этапа](../docs/validation/21.10.2026%20Windows%20architecture.md).
