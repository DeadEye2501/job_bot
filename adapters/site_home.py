"""Главная страница сайта: как сайт на ней называет сам себя и чем себя обозначает.

От `telegraph` отличается предметом: там из страницы достаётся статья, здесь —
имя сервиса и его значок из шапки. Подсказки к имени две: объявленное имя
(`og:site_name`, `application-name`) и части заголовка вкладки — сайты пишут в
него себя через разделитель рядом с описанием страницы.
"""

import re
from dataclasses import dataclass
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

from adapters.web_page import page_client

# Короткое ожидание: страницу ждёт человек, на глазах у которого заводится
# агрегатор, а без неё имя всё равно найдётся.
FETCH_TIMEOUT_SEC = 8.0

# Обычный браузер, а не имя бота: часть сайтов отдаёт роботу заглушку без
# шапки, и подсказок в ней нет.
_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
)

_TITLE_SEPARATORS_RE = re.compile(r" [-—|] ")

_DECLARING_META = ({"property": "og:site_name"}, {"name": "application-name"})

# Значки по старшинству: значок для экрана телефона крупный и чёткий, обычный
# бывает в 16 точек. Последним — `/favicon.ico`, который браузеры ищут и без
# объявления.
_ICON_RELS = ("apple-touch-icon", "icon", "shortcut icon")
_FALLBACK_ICON = "/favicon.ico"
# Значок вшивается в каждый ответ списка; больше — это не значок, а картинка.
_ICON_LIMIT_BYTES = 256 * 1024


@dataclass(frozen=True)
class SiteHints:
    """Что страница говорит о своём имени: объявленные имена и части заголовка."""

    declared: tuple[str, ...] = ()
    title_parts: tuple[str, ...] = ()


@dataclass(frozen=True)
class SiteHome:
    """Главная страница: подсказки к имени и адреса значков по старшинству."""

    hints: SiteHints
    icons: tuple[str, ...]


def make_client() -> httpx.AsyncClient:
    """Клиент к сайту. Переходы разрешены: главная часто уводит на свой адрес."""
    return page_client(FETCH_TIMEOUT_SEC, _USER_AGENT)


async def fetch_home(client: httpx.AsyncClient, host: str) -> SiteHome:
    """Главная страница сайта, разобранная один раз. Не отдали — беда наружу."""
    response = await client.get(f"https://{host}")
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    return SiteHome(_hints(soup), _icons(soup, str(response.url)))


async def fetch_icon(client: httpx.AsyncClient, urls: tuple[str, ...]) -> bytes | None:
    """Первый из адресов, что отдал картинку; ни один — пусто.

    Картинка — по ответу, а не по адресу: на неизвестный путь сайты отдают
    страницу «не найдено», и часто с кодом 200. Векторная не годится: окно
    вшивает значок картинкой, а не разметкой.
    """
    for url in urls:
        try:
            response = await client.get(url)
        except httpx.HTTPError:
            continue
        kind = response.headers.get("content-type", "")
        if (response.status_code == 200 and kind.startswith("image/") and "svg" not in kind
                and 0 < len(response.content) <= _ICON_LIMIT_BYTES):
            return response.content
    return None


def _icons(soup: BeautifulSoup, base: str) -> tuple[str, ...]:
    links = [tag for tag in soup.find_all("link", href=True) if not _vector(tag)]
    found = [
        urljoin(base, str(tag["href"]))
        for rel in _ICON_RELS
        for tag in links
        if " ".join(tag.get("rel", [])).lower() == rel
    ]
    found.append(urljoin(base, _FALLBACK_ICON))
    return tuple(dict.fromkeys(found))


def _vector(tag) -> bool:
    return "svg" in str(tag.get("type", "")) or str(tag["href"]).lower().endswith(".svg")


def _hints(soup: BeautifulSoup) -> SiteHints:
    declared = []
    for attrs in _DECLARING_META:
        tag = soup.find("meta", attrs=attrs)
        content = str(tag.get("content") or "").strip() if tag is not None else ""
        if content:
            declared.append(content)
    title = soup.title.get_text(" ", strip=True) if soup.title is not None else ""
    parts = tuple(part.strip() for part in _TITLE_SEPARATORS_RE.split(title) if part.strip())
    return SiteHints(declared=tuple(declared), title_parts=parts)
