"""First-run bootstrap: ensure DB schema exists and run the CLI wizard.

The schema is created/upgraded via Alembic on every startup. The wizard
runs interactively in the terminal whenever ``wizard_completed`` is not
true in app_settings; once a Flet UI ships, ``run_wizard`` is replaced
by the in-app form, but ``ensure_schema`` stays.
"""

import getpass
import logging
import sys
from pathlib import Path

from alembic import command
from alembic.config import Config

from backend.runtime_settings import RuntimeSettings
from config import get_database_url


logger = logging.getLogger(__name__)


_PROJECT_ROOT = Path(__file__).resolve().parent.parent


# OpenAI-compatible providers. Tuple: (label, base_url, api_key_required).
# "Custom" means the user enters base_url and (optionally) api_key by hand.
_LLM_PRESETS: list[tuple[str, str | None, bool]] = [
    ("OpenAI",     "https://api.openai.com/v1",      True),
    ("LM Studio",  "http://localhost:1234",          False),
    ("Ollama",     "http://localhost:11434",         False),
    ("OpenRouter", "https://openrouter.ai/api/v1",   True),
    ("Custom",     None,                              False),
]


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


async def run_wizard(rs: RuntimeSettings) -> None:
    """Walk the user through the minimal first-run setup in the terminal."""
    print()
    print("=" * 60)
    print(" Job Bot — первая настройка")
    print("=" * 60)
    print(
        "\nUI пока нет, настраиваем в терминале. Три шага: Telegram, "
        "чат-LLM, эмбеддинги.\nCtrl-C прерывает; уже введённое сохраняется.\n"
    )

    await _wizard_telegram(rs)
    chat_url, chat_key = await _wizard_llm(rs, kind="chat")
    await _wizard_llm(rs, kind="embed", chat_defaults=(chat_url, chat_key))

    await rs.mark_wizard_completed()
    await rs.reload()
    print("\n✓ Настройка завершена. Запускаю бота...\n")


# --- internals -------------------------------------------------------------


async def _wizard_telegram(rs: RuntimeSettings) -> None:
    print("[1/3] Telegram")
    print("  api_id и api_hash возьми на https://my.telegram.org/apps\n")
    api_id = _ask_int("  api_id: ")
    api_hash = _ask("  api_hash: ").strip()
    while not api_hash:
        api_hash = _ask("  api_hash (нужно ввести): ").strip()
    phone = _ask("  Телефон (с кодом страны, например +71234567890): ").strip()
    password = _ask_secret(
        "  Пароль от Telegram (если есть, иначе Enter): ",
        allow_empty=True,
    )
    # Save credentials now; interactive Pyrogram login happens later in Bot.run().
    await rs.set_tg(
        api_id=api_id,
        api_hash=api_hash,
        phone=phone,
        password=password,
        session_string=None,
    )


async def _wizard_llm(
    rs: RuntimeSettings,
    *,
    kind: str,  # "chat" or "embed"
    chat_defaults: tuple[str, str] | None = None,
) -> tuple[str, str]:
    step_no = 2 if kind == "chat" else 3
    label = "чат" if kind == "chat" else "эмбеддингов"
    print(f"\n[{step_no}/3] LLM для {label}")

    if chat_defaults is not None:
        same = _ask_bool(
            "  Те же креды, что для chat? [Y/n]: ",
            default=True,
        )
        if same:
            base_url, api_key = chat_defaults
            model = _ask("  Модель: ").strip()
            await _save_llm(rs, kind, base_url, api_key, model)
            return base_url, api_key

    base_url, api_key = _pick_provider()
    model = _ask("  Модель: ").strip()
    await _save_llm(rs, kind, base_url, api_key, model)
    return base_url, api_key


async def _save_llm(
    rs: RuntimeSettings, kind: str, base_url: str, api_key: str, model: str
) -> None:
    if kind == "chat":
        await rs.set_chat(base_url=base_url, api_key=api_key, model=model)
    else:
        await rs.set_embed(base_url=base_url, api_key=api_key, model=model)


def _pick_provider() -> tuple[str, str]:
    print("  Провайдер:")
    for i, (label, url, _) in enumerate(_LLM_PRESETS, 1):
        suffix = f"  → {url}" if url else "  (введёшь URL сам)"
        print(f"    {i}. {label}{suffix}")
    while True:
        raw = _ask(f"  выбери [1-{len(_LLM_PRESETS)}]: ").strip()
        if raw.isdigit() and 1 <= int(raw) <= len(_LLM_PRESETS):
            label, url, key_required = _LLM_PRESETS[int(raw) - 1]
            break
        print("  Введи номер из списка.")

    if url is None:
        url = _ask("  base_url: ").strip()
    api_key = _ask(
        "  api_key (Enter если не нужен): "
        if not key_required
        else "  api_key: ",
    ).strip()
    while key_required and not api_key:
        api_key = _ask("  api_key (нужно ввести): ").strip()
    return url, api_key


def _ask(prompt: str) -> str:
    try:
        return input(prompt)
    except EOFError:
        print()
        sys.exit("прервано (EOF)")


def _ask_int(prompt: str) -> int:
    while True:
        raw = _ask(prompt).strip()
        if raw.isdigit():
            return int(raw)
        print("  Нужно целое положительное число.")


def _ask_secret(prompt: str, allow_empty: bool = False) -> str:
    """Hidden input — only for actual passwords (not API keys / hashes)."""
    while True:
        try:
            value = getpass.getpass(prompt)
        except EOFError:
            print()
            sys.exit("прервано (EOF)")
        if value or allow_empty:
            return value
        print("  Поле обязательно.")


def _ask_bool(prompt: str, default: bool) -> bool:
    raw = _ask(prompt).strip().lower()
    if not raw:
        return default
    return raw in ("y", "yes", "д", "да", "true", "1")
