"""Профиль под симуляцией отклика: данные с сайта не уходят, капча проходится."""

from adapters.browser import BrowserHost, InstalledBrowser, hold_sending


class _Request:
    def __init__(self, method, url):
        self.method, self.url = method, url


class _Route:
    def __init__(self, method, url):
        self.request = _Request(method, url)
        self.fate = None

    async def abort(self, *_reason):
        self.fate = "aborted"

    async def continue_(self, **_options):
        self.fate = "passed"


async def _fate(method, url):
    route = _Route(method, url)
    await hold_sending(route)
    return route.fate


async def test_a_form_sending_its_data_is_cut_off():
    assert await _fate("POST", "https://company.test/apply") == "aborted"


async def test_every_method_that_carries_data_is_cut_off():
    for method in ("PUT", "PATCH", "DELETE"):
        assert await _fate(method, "https://api.company.test/applications/1") == "aborted"


async def test_reading_pages_goes_on():
    assert await _fate("GET", "https://company.test/jobs/1") == "passed"


async def test_a_captcha_answer_still_goes_out():
    """Капча — проверка человека, а не отклик: без неё форму не пройти и в симуляции."""
    assert await _fate("POST", "https://www.google.com/recaptcha/api2/userverify?k=x") == "passed"
    assert await _fate("POST", "https://api.hcaptcha.com/checkcaptcha/x") == "passed"
    assert await _fate("POST", "https://challenges.cloudflare.com/cdn-cgi/x") == "passed"


async def test_a_lookalike_of_a_captcha_host_is_cut_off():
    assert await _fate("POST", "https://hcaptcha.com.company.test/apply") == "aborted"


async def test_a_google_form_is_an_application_not_a_captcha():
    assert await _fate("POST", "https://docs.google.com/forms/d/e/x/formResponse") == "aborted"
    assert await _fate("POST", "https://www.google.com/forms/x") == "aborted"


async def test_cloudflare_checking_a_human_on_the_site_itself_still_goes_out():
    """Cloudflare проверяет человека и на хосте самого сайта — своим служебным путём."""
    url = "https://company.test/cdn-cgi/challenge-platform/h/b/flow/ov1/x"
    assert await _fate("POST", url) == "passed"


class _Context:
    def __init__(self, options):
        self.options = options
        self.routes = []
        self.init_scripts = []
        self.pages = [_Page()]

    async def route(self, pattern, handler):
        self.routes.append((pattern, handler))

    async def add_init_script(self, script):
        self.init_scripts.append(script)

    def on(self, *_event):
        return None

    async def close(self):
        return None


class _Page:
    url = "about:blank"

    def on(self, *_event):
        return None


class _Playwright:
    def __init__(self):
        self.contexts = []
        self.chromium = self

    async def start(self):
        return self

    async def launch_persistent_context(self, _path, **options):
        self.contexts.append(_Context(options))
        return self.contexts[-1]


async def test_a_profile_opened_not_to_send_holds_every_request(monkeypatch):
    """Удержание ставится при запуске профиля, а не только объявлено: без него
    правило обрыва не видит ни одного запроса."""
    playwright = _Playwright()
    monkeypatch.setattr("playwright.async_api.async_playwright", lambda: playwright)
    monkeypatch.setattr("adapters.app_tied_process.tie_children_named", lambda _name: None)
    host = BrowserHost(InstalledBrowser("Chrome", "chrome", None), always_visible=True)

    await host.open_profile(1, sending=False)
    await host.open_profile(1, sending=True)

    held, free = playwright.contexts
    assert held.routes == [("**/*", hold_sending)] and held.options["service_workers"] == "block"
    assert free.routes == [] and free.options["service_workers"] == "allow"


async def test_a_profile_opened_for_a_human_login_carries_no_automation_mark(monkeypatch):
    """Вход Google отказывает браузеру с пометкой «управляется программой»; входит
    же человек руками, и пометка ему не нужна. Обход идёт с ней, как шёл."""
    playwright = _Playwright()
    monkeypatch.setattr("playwright.async_api.async_playwright", lambda: playwright)
    monkeypatch.setattr("adapters.app_tied_process.tie_children_named", lambda _name: None)
    host = BrowserHost(InstalledBrowser("Chrome", "chrome", None), always_visible=True)

    await host.open_profile(1, as_person=True)
    await host.open_profile(1)

    person, agent = playwright.contexts
    assert "--enable-automation" in person.options["ignore_default_args"]
    # `navigator.webdriver` прячет скрипт страницы, а не флаг: на флаги, которых
    # Chrome не поддерживает, — и на `--no-sandbox` — он вешает над страницей плашку.
    assert any("webdriver" in script for script in person.init_scripts)
    assert not person.options.get("args")
    assert person.options["chromium_sandbox"] is True
    assert not agent.options.get("ignore_default_args") and not agent.init_scripts
