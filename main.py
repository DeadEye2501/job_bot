"""Job Bot — single CLI entry point.

Run:
    python main.py            — launch the desktop UI (wizard on first run,
                                otherwise the main app window with the bot
                                running in the background).
"""

import logging
import sys
import traceback
from logging.handlers import RotatingFileHandler

from config import get_log_path


def _use_utf8_stdout() -> None:
    """Перенастроить вывод на UTF-8, а неудачу показать, не проглотив.

    Логирование к этому мигу ещё не настроено, поэтому сообщать можно только
    прямо в поток ошибок. Молчать нельзя: без перенастройки вывод ломается на
    кириллице, и виновника потом не найти.

    В оконной сборке потока ошибок нет вовсе, и сообщение пропадёт. Канал,
    переживающий его отсутствие, теперь есть — файл журнала, — но берёт он
    запись журнала, а её к этому мигу ещё не из чего сделать: логирование
    настраивается ниже. Записано в роадмапу отдельным пунктом.
    """
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        if sys.stderr is None:
            return  # оконная сборка: писать некуда, см. роадмапу
        traceback.print_exc()


_use_utf8_stdout()


LOG_BYTES = 5 * 1024 * 1024
LOG_KEPT = 3


def _log_handlers() -> list[logging.Handler]:
    """Куда пишется журнал приложения.

    Файл — всегда: в оконной сборке (`console=False`) `sys.stdout` и
    `sys.stderr` равны `None`, и обработчик, настроенный на поток, теряет всё
    молча. Кольцевой буфер экрана «Логи» тоже не спасает — он в памяти и
    пропадает вместе с окном, а разбирать падение приходится после него.

    Кодировка задаётся явно: без неё файл открылся бы кодировкой системы, а
    в журнал попадают тексты из Telegram — эмодзи и письменности, которых в
    однобайтовой кодировке нет, сорвали бы запись.

    Открытие отложено: без этого пустой файл заводился бы на каждый ввоз
    модуля, в том числе прогоном тестов и инструментами.
    """
    handlers: list[logging.Handler] = [
        RotatingFileHandler(
            get_log_path(),
            maxBytes=LOG_BYTES,
            backupCount=LOG_KEPT,
            encoding="utf-8",
            delay=True,
        )
    ]
    if sys.stdout is not None:
        handlers.append(logging.StreamHandler(sys.stdout))
    return handlers


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=_log_handlers(),
)
# Attach the in-memory buffer handler that backs the UI «Логи» screen.
# Идемпотентно — повторный install() не-op.
from backend.log_buffer import (
    install as _install_log_buffer,
    install_secret_filter as _install_secret_filter,
)
_install_log_buffer()
# Secret-redaction filter ставим ДО первого logger.* и ПОСЛЕ того, как все
# обработчики на месте: он вешается на них, а не на logger. Иначе Bearer-
# токены / api_hash / session-string'и из третьих либ (httpx debug, pyrogram,
# sqlalchemy echo) легли бы в файл журнала как есть — и пережили бы окно.
_install_secret_filter()
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


def main() -> int:
    from backend import bootstrap
    from backend.crypto import _check_keyring_backend
    from client.shell import run_ui

    # Fail-fast если keyring-бэкенд небезопасный (PlaintextKeyring) или
    # сломан (fail.Keyring) — иначе secrets улетят в открытом виде на
    # диск или потеряются после первого старта. Друже сообщение в stderr
    # вместо raw traceback'а — Qt UI ещё не поднят, диалог показать
    # негде, но юзер хотя бы поймёт причину выхода вместо «упало непонятно».
    try:
        _check_keyring_backend()
    except RuntimeError as e:
        logger.critical("keyring pre-flight failed: %s", e)
        print(f"\n[Job Bot] Не удалось запуститься: {e}\n", file=sys.stderr)
        return 2
    # Schema must be ensured BEFORE the Qt event loop starts because alembic
    # spins its own asyncio.run inside.
    bootstrap.ensure_schema()
    return run_ui()


if __name__ == "__main__":
    sys.exit(main())
