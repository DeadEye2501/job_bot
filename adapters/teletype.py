"""Статья teletype: сходить по адресу и достать из страницы её текст.

Объявления в каналах сплошь и рядом умещают в пост одну шапку, а всё
остальное выносят в статью — «ПОСМОТРЕТЬ», ссылка, и там уже требования,
условия и способ отклика. Разбирать в таком объявлении без статьи нечего.

Страница разбирается по разметке, а не поиском по строке: teletype размечает
заголовок и тело статьи по schema.org (`itemprop`), и это переживает
перевёрстку, от которой поиск по именам стилей рассыпается.
"""

import logging
import re

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# Адрес статьи: «https://teletype.in/@автор/ключ». Ключ обязателен: без него
# это страница автора, она стоит в подвале каждого поста канала и статьи за
# ней нет никогда.
#
# Хвост адреса кончается не на чём попало. Закрывающая скобка в него не
# входит — за подписью ссылки адрес дописывают именно в скобках
# (см. `extract_post_text`). Точка и запятая — тоже: адрес, набранный в тексте
# словами, кончается точкой конца предложения, и утащенная в адрес точка ведёт
# в никуда.
ARTICLE_URL_RE = re.compile(
    r"https?://teletype\.in/@[^\s)\]/]+/[^\s)\]]*[^\s)\].,;:!?…»\"']"
)

# Своё время ожидания, не общее с языковой моделью: там ждут работы, здесь —
# отдачи страницы, и минуты ожидания чужого сайта задержали бы весь обход
# каналов.
FETCH_TIMEOUT_SEC = 20.0

_USER_AGENT = "Mozilla/5.0 (compatible; JobBot/1.0)"


def make_client() -> httpx.AsyncClient:
    """Клиент к teletype. Переходы разрешены: короткие адреса ведут через них."""
    return httpx.AsyncClient(
        timeout=FETCH_TIMEOUT_SEC,
        follow_redirects=True,
        headers={"User-Agent": _USER_AGENT},
    )


def _article_text(html: str) -> str | None:
    """Заголовок и тело статьи со страницы; пусто — статьи на ней нет.

    Пусто бывает не только от перевёрстки: по адресу статьи может лежать
    страница автора или весть о том, что статью снесли, и тела у неё нет.
    """
    soup = BeautifulSoup(html, "html.parser")
    body = soup.find(attrs={"itemprop": "articleBody"})
    if body is None:
        return None
    headline = soup.find(attrs={"itemprop": "headline"})
    parts = [
        part
        for part in (
            headline.get_text(" ", strip=True) if headline else "",
            body.get_text("\n", strip=True),
        )
        if part
    ]
    return "\n\n".join(parts) or None


async def fetch_article(client: httpx.AsyncClient, url: str) -> str | None:
    """Текст статьи по адресу; пусто — статьи там нет. Не отдали — беда наружу.

    Два исхода разведены нарочно, и разница у них во времени. «Статьи там
    нет» — навсегда: её снесли, или адрес ведёт на страницу автора. «Не
    отдали» — на час: сайт лежит, сеть оборвалась, к утру всё вернётся.
    Зовущему это решает разное — переписывать ли сохранённый текст вакансии
    тем, что вышло собрать сейчас.
    """
    response = await client.get(url)
    response.raise_for_status()
    text = _article_text(response.text)
    if text is None:
        logger.info("teletype: на странице %s статьи не нашлось", url)
    return text
