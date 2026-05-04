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
from backend.log_buffer import install as _install_log_buffer
_install_log_buffer()
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


def main() -> int:
    from backend import bootstrap
    from client.shell import run_ui

    # Schema must be ensured BEFORE the Qt event loop starts because alembic
    # spins its own asyncio.run inside.
    bootstrap.ensure_schema()
    return run_ui()


if __name__ == "__main__":
    sys.exit(main())
