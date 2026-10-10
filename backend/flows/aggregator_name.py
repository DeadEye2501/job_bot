"""Имя и значок агрегатора: как сервис зовут люди и чем он себя обозначает.

Ищутся вне сделки с базой: страница и модель отвечают секундами, и всё это
время база стояла бы запертой для обхода и окна. Ни сайт, ни модель заведению
не мешают — без них имя берётся из того, что осталось, а значка просто нет.
"""

import logging
from contextlib import aclosing

import httpx

from adapters import lm_studio, site_home
from backend.domain.hosts import normalize_host, site_label
from backend.llm.site_name import ask_site_name
from backend.models import Aggregator
from backend.provider_config import LlmProviderConfig
from backend.repository import aggregators as repo

logger = logging.getLogger(__name__)


async def _named(host: str, hints: site_home.SiteHints, chat: LlmProviderConfig | None) -> str:
    """Имя сервиса с большой буквы: слово модели, имя из шапки, часть заголовка, имя в хосте.

    Порядок — от того, что знает, как сервис зовут, к тому, что только
    угадывает: модель видит и подсказки, и адрес; шапка объявляет имя сама;
    заголовок смешивает имя с описанием страницы.
    """
    spoken = await _model_name(host, [*hints.declared, *hints.title_parts], chat)
    declared = hints.declared[0] if hints.declared else None
    name = spoken or declared or _site_like_part(host, hints.title_parts) or site_label(host)
    return name[:1].upper() + name[1:]


async def create_named_aggregator(
    session_factory, address: str, chat: LlmProviderConfig | None
) -> tuple[Aggregator | None, str]:
    """Завести агрегатор под именем сервиса и с его значком; уже заведённый
    сайт не спрашивает вовсе."""
    host = normalize_host(address)
    if not host:
        return None, "invalid"
    async with session_factory() as session:
        known = await repo.find_aggregator(session, host)
    if known is not None:
        return known, "exists"
    hints, icon = await _site(host)
    name = await _named(host, hints, chat)
    async with session_factory() as session:
        async with session.begin():
            return await repo.create_aggregator(session, host, name, icon)


async def _site(host: str) -> tuple[site_home.SiteHints, bytes | None]:
    """Подсказки к имени и значок — одним клиентом: значок лежит на том же сайте."""
    async with site_home.make_client() as client:
        try:
            home = await site_home.fetch_home(client, host)
        except httpx.HTTPError as e:
            logger.info("site_name: главная %s не отдалась: %s: %s", host, type(e).__name__, e)
            return site_home.SiteHints(), None
        return home.hints, await site_home.fetch_icon(client, home.icons)


async def _model_name(host: str, hints: list[str], chat: LlmProviderConfig | None) -> str | None:
    if chat is None:
        return None
    # Сборка клиента спотыкается о негодный адрес поставщика, набранный в
    # настройках, — заведение агрегатора от этого стоять не должно.
    try:
        client = lm_studio.make_client(chat)
    except Exception:
        logger.exception("site_name: не собрался клиент поставщика %s", chat.base_url)
        return None
    async with aclosing(client):
        return await ask_site_name(host, hints, client, chat.model)


def _site_like_part(host: str, parts: tuple[str, ...]) -> str | None:
    """Часть заголовка, похожая на имя сайта: с именем из хоста, иначе самая короткая.

    Заголовок из одной части — описание страницы, а не имя: имя сайты
    отделяют от описания разделителем.
    """
    if len(parts) < 2:
        return None
    label = site_label(host).casefold()
    return next((part for part in parts if label in part.casefold()), min(parts, key=len))
