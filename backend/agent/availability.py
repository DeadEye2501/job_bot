"""Чем агенту работать: водитель — Claude Code, браузер — установленный Chromium."""

from adapters.browser import BROWSER_NAMES, InstalledBrowser
from backend.provider_config import LlmProviderConfig, serves_claude_code

NO_DRIVER = "Для агрегаторов нужен Claude Code: выберите его поставщиком чата."
NO_BROWSER = (
    f"Не найден браузер на движке Chromium: {', '.join(BROWSER_NAMES[:-1])} "
    f"или {BROWSER_NAMES[-1]}."
)


def agent_refusal(chat: LlmProviderConfig | None, browser: InstalledBrowser | None) -> str | None:
    """Почему агент сейчас не может работать; пусто — может."""
    if chat is None or not serves_claude_code(chat.base_url):
        return NO_DRIVER
    if browser is None:
        return NO_BROWSER
    return None
