"""Подделка главной страницы сайта: настоящий клиент поверх подставного транспорта.

Подменяется сборка клиента (`adapters.site_home.make_client`), а разбор
страницы остаётся боевым: проверки видят те подсказки, которые достал бы
настоящий код. Сеть тестов не заперта, и без подмены заведение агрегатора
ушло бы на живой сайт.
"""

import httpx

from tests.fakes.http import serve

HOME = ("GET", "/")


def serve_home(
    monkeypatch, prepared: httpx.Response | BaseException, pages: dict | None = None
) -> None:
    """Главная страница отвечает заготовленным; исключение — сеть не дотянулась.

    `pages` — другие пути сайта (значок) и их ответы; незаданный путь отвечает бедой.
    """
    routes = {HOME: prepared, **{("GET", path): answer for path, answer in (pages or {}).items()}}
    serve(monkeypatch, "adapters.site_home.make_client", routes)


def home_page(*, head: str = "") -> httpx.Response:
    """Главная страница с заданной шапкой и пустым телом."""
    return httpx.Response(200, text=f"<html><head>{head}</head><body></body></html>")
