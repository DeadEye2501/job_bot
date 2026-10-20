"""Профиль под симуляцией отклика: данные с сайта не уходят, капча проходится."""

from adapters.browser import hold_sending
from tests.fakes.playwright import driven_host


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


async def test_a_profile_opened_not_to_send_holds_every_request(monkeypatch):
    """Удержание ставится при запуске профиля, а не только объявлено: без него
    правило обрыва не видит ни одного запроса."""
    host, playwright = driven_host(monkeypatch)

    await host.open_profile(1, sending=False)
    await host.open_profile(1, sending=True)

    held, free = playwright.contexts
    assert held.routes == [("**/*", hold_sending)] and held.options["service_workers"] == "block"
    assert free.routes == [] and free.options["service_workers"] == "allow"
