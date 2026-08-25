"""Отпечаток текста: как его считают у поставщика и как поднимают кэш."""

import logging

import httpx
from sqlalchemy import select

from adapters import lm_embed
from backend.models import Vacancy

logger = logging.getLogger(__name__)


# Сколько текста уходит в модель отпечатков. Прежде предел ставил сам Telegram
# — четыре тысячи знаков поста, — и упереться в окно модели было нечем. Теперь
# к посту дописывается статья по ссылке, а она бывает в разы длиннее.
# Переполненное окно поставщик встречает отказом, отказ приходит сюда пустым
# отпечатком, а пустой отпечаток на приёме означает, что объявление не завели
# вовсе и второй раз не увидят — курсор канала уже уехал. Отсеву повторов
# начала текста хватает: два поста, совпавшие первыми шестью тысячами знаков,
# и есть один и тот же пост.
_EMBED_MAX_CHARS = 6000


class ProviderIsSilent(Exception):
    """Поставщик отпечатков не отвечает вовсе — беда не про этот текст.

    Разница дорога приёму поста: не посчитавшийся текст пропускают и идут
    дальше, а молчащего поставщика пропускать нельзя — отметка канала уедет до
    самого свежего поста, и непрочитанные объявления не увидит уже никто.
    """


def _is_about_the_provider(trouble: Exception) -> bool:
    """Беда про поставщика целиком, а не про этот текст.

    Таких две: адрес не отвечает — соединения нет вовсе, — и ответ 404 или
    500-й, то есть модели у поставщика нет либо он сам сломан. Обе приходят на
    каждый текст подряд. Отказ на самом тексте (переполненное окно — 400)
    говорит только об этом тексте, и следующий посчитается.
    """
    if isinstance(trouble, httpx.TransportError):
        return True
    if isinstance(trouble, httpx.HTTPStatusError):
        code = trouble.response.status_code
        return code == 404 or code >= 500
    return False


async def embed_text(pipeline, text: str, what: str) -> list[float] | None:
    """Числовой отпечаток текста; пусто — модель отпечатков его не дала.

    Отказ на самом тексте не роняет ни обход канала, ни прогон вакансии:
    зовущий решает сам, что делать без отпечатка, — а вставать на одном посте
    дороже, чем пропустить его. Чей это текст, говорит `what`: из записи
    журнала иначе не видно, на чём споткнулись.

    Молчание самого поставщика — другое дело, и оно поднимается броском
    `ProviderIsSilent`: пустой отпечаток на приёме означает, что объявление не
    завели и второй раз не увидят, а молчит поставщик сразу для всех постов.
    Записи здесь такой беде нет: пишет её тот, кто ловит, — ему видно, чем
    кончился обход.
    """
    try:
        return await lm_embed.embed(
            pipeline.lm_embed_client,
            pipeline.lm_embed_model,
            text[:_EMBED_MAX_CHARS],
        )
    except Exception as trouble:
        if _is_about_the_provider(trouble):
            raise ProviderIsSilent(what) from trouble
        logger.exception("%s: не вышло посчитать отпечаток, пропускаю", what)
        return None


async def similar_vacancy_id(pipeline, embedding: list[float]) -> int | None:
    """Номер уже заведённой вакансии с таким же отпечатком; пусто — такой нет.

    Заводят вакансию из текста двое — обход канала и человек со вставленным
    объявлением, — и отсев у них общий: перепост и повторная вставка одного и
    того же объявления одинаково не должны давать второй строки. Порог
    близости берётся из настроек, а не из довода: он один на оба входа, и
    разъехавшись, они считали бы перепостом разное.
    """
    await ensure_embedding_cache(pipeline, len(embedding))
    return pipeline.embeddings.match(embedding, pipeline.rs.dedup_cosine_threshold)


async def ensure_embedding_cache(pipeline, width: int) -> None:
    """Поднять векторы вакансий в память один раз за жизнь конвейера.

    Здесь только поход в базу: что делать с векторами чужой длины, решает сам
    кэш (`domain/dedup.EmbeddingCache`). Отброшенные он же и считает — число
    уходит в журнал, потому что вернуть их в дело может только пересчёт,
    прогон заново по каждой вакансии.
    """
    if pipeline.embeddings.loaded:
        return
    async with pipeline.session_factory() as session:
        rows = (
            await session.execute(
                select(Vacancy.id, Vacancy.embedding).where(
                    Vacancy.embedding.is_not(None)
                )
            )
        ).all()
    dropped = pipeline.embeddings.fill(
        ((r.id, r.embedding) for r in rows), width
    )
    if dropped:
        logger.warning(
            "Embedding cache: %d вектор(ов) чужой длины отброшено "
            "(нынешняя %d) — вернёт их только прогон заново",
            dropped, width,
        )
    logger.debug("Embedding cache loaded: %d vectors", len(rows) - dropped)
