"""Job Bot — single CLI entry point.

Run:
    python main.py            — launch the desktop UI (wizard on first run,
                                otherwise the main app window with the bot
                                running in the background).
"""

import logging
import sys


try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
)
# Attach the in-memory buffer handler that backs the UI «Логи» screen.
# Идемпотентно — повторный install() не-op.
from backend.log_buffer import (
    install as _install_log_buffer,
    install_secret_filter as _install_secret_filter,
)
_install_log_buffer()
# Secret-redaction filter ставим ДО первого logger.* — чтобы Bearer-
# токены / api_hash / session-string'и из третьих либ (httpx debug,
# pyrogram, sqlalchemy echo) маскировались до stdout и UI-buffer'а.
_install_secret_filter()
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


def main() -> int:
    from backend import bootstrap
    from backend.runtime_settings import _check_keyring_backend
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
