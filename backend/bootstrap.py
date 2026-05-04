"""First-run bootstrap: ensure DB schema exists.

Schema создаётся / обновляется через Alembic на каждом старте. Сам wizard
сейчас живёт в ``client/web/wizard.html`` + ``client/bridge.WizardApi``;
терминальный CLI-wizard был удалён в Phase 11 как мёртвый код.
"""

import logging
from pathlib import Path

from alembic import command
from alembic.config import Config

from config import get_database_url


logger = logging.getLogger(__name__)


_PROJECT_ROOT = Path(__file__).resolve().parent.parent


def ensure_schema() -> None:
    """Create the SQLite file (if missing) and run all migrations to head.

    Must be called BEFORE entering the asyncio event loop because alembic's
    env.py spins up its own ``asyncio.run`` internally.
    """
    cfg = Config(str(_PROJECT_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(_PROJECT_ROOT / "alembic"))
    cfg.set_main_option("sqlalchemy.url", get_database_url())
    logger.info("Running alembic upgrade head")
    command.upgrade(cfg, "head")
    logger.info("Alembic upgrade complete")
