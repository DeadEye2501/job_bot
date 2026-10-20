"""Playwright под `BrowserHost`: запуск профиля и события его контекста, без браузера."""

from adapters.browser import BrowserHost
from tests.fakes.browser import CHROME


class DrivenContext:
    """Запущенный профиль: с чем запущен, что перехвачено, кто слушает его события."""

    def __init__(self, path, options):
        self.path, self.options = path, options
        self.routes = []
        self.handlers = {}
        self.closed = False
        self.pages = [_DrivenPage()]

    async def route(self, pattern, handler):
        self.routes.append((pattern, handler))

    def on(self, event, handler):
        self.handlers.setdefault(event, []).append(handler)

    async def close(self):
        self.closed = True
        self.fire("close")

    def fire(self, event):
        """Послать событие контекста его слушателям, как это делает Playwright."""
        for handler in self.handlers.get(event, []):
            handler(self)


class _DrivenPage:
    url = "about:blank"

    def on(self, *_event):
        return None

    async def goto(self, url, **_options):
        self.url = url


class _Playwright:
    def __init__(self):
        self.contexts = []
        self.chromium = self

    async def start(self):
        return self

    async def stop(self):
        return None

    async def launch_persistent_context(self, path, **options):
        self.contexts.append(DrivenContext(path, options))
        return self.contexts[-1]


def driven_host(monkeypatch, on_closed=lambda: None) -> tuple[BrowserHost, _Playwright]:
    """Хозяин браузера на подделке Playwright; второе — она, с запущенными профилями."""
    playwright = _Playwright()
    monkeypatch.setattr("playwright.async_api.async_playwright", lambda: playwright)
    monkeypatch.setattr("adapters.platforms.processes.tie_browser_driver", lambda: None)
    return BrowserHost(CHROME, always_visible=True, on_closed=on_closed), playwright
