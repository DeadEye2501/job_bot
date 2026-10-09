"""Браузер агента с заданными страницами: что открыто, что нажато, что отказало."""

from playwright.async_api import Error as PlaywrightError
from playwright.async_api import TimeoutError as PlaywrightTimeout


class _Chooser:
    def __init__(self, page):
        self._page = page

    async def set_files(self, files, **_options):
        self._page.calls.append(("chooser", files))


class _ChooserInfo:
    """Ожидание окна выбора файла: открылось ли оно за время блока `async with`."""

    def __init__(self, page):
        self._page = page

    async def __aenter__(self):
        self._page.chooser_opened = False
        return self

    async def __aexit__(self, kind, *_rest):
        if kind is None and not self._page.chooser_opened:
            raise PlaywrightTimeout("Timeout 15000ms exceeded while waiting for event \"filechooser\"")
        return False

    @property
    def value(self):
        async def _chooser():
            return _Chooser(self._page)
        return _chooser()


class _Locator:
    def __init__(self, page, selector):
        self._page, self._selector = page, selector

    async def aria_snapshot(self, **_options):
        self._page.fail_if_asked(self._selector)
        return self._page.pages.get(self._page.url, ("", ""))[1]


class FakePage:
    """Страница: `pages` — адрес → (заголовок, снимок); `failures` — селектор → ошибка;
    `choosers` — селекторы, нажатие на которые открывает окно выбора файла."""

    def __init__(self, pages=None, failures=None, choosers=()):
        self.pages = pages or {}
        self.failures = failures or {}
        self.choosers = set(choosers)
        self.url = "about:blank"
        self.calls: list[tuple] = []
        self.chooser_opened = False

    def fail_if_asked(self, selector):
        if selector in self.failures:
            raise PlaywrightError(self.failures[selector])

    async def goto(self, url, **_options):
        self.fail_if_asked(url)
        self.calls.append(("goto", url))
        self.url = url

    async def title(self):
        return self.pages.get(self.url, ("", ""))[0]

    def locator(self, selector):
        return _Locator(self, selector)

    async def click(self, selector, **_options):
        self.fail_if_asked(selector)
        self.calls.append(("click", selector))
        self.chooser_opened = self.chooser_opened or selector in self.choosers

    async def fill(self, selector, text, **_options):
        self.fail_if_asked(selector)
        self.calls.append(("fill", selector, text))

    async def select_option(self, selector, value, **_options):
        self.fail_if_asked(selector)
        self.calls.append(("select", selector, value))

    async def set_input_files(self, selector, files, **_options):
        self.fail_if_asked(selector)
        self.calls.append(("input_files", selector, files))

    def expect_file_chooser(self, **_options):
        return _ChooserInfo(self)

    async def go_back(self, **_options):
        self.calls.append(("back",))


class FakeBrowser:
    """Хозяин браузера: отдаёт одну и ту же страницу и помнит, показывали ли окно."""

    def __init__(self, page: FakePage | None = None):
        self._page = page or FakePage()
        self.calls: list[str] = []

    async def page(self):
        return self._page

    async def show(self):
        self.calls.append("show")

    async def hide_back(self):
        self.calls.append("hide")
