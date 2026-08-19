"""Отпечаток текста: как его считают у поставщика и как поднимают кэш."""

import logging

from sqlalchemy import select

from adapters import lm_studio
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


async def embed_text(pipeline, text: str, what: str) -> list[float] | None:
    """Числовой отпечаток текста; пусто — модель отпечатков его не дала.

    Беда отпечатка не роняет ни обход канала, ни прогон вакансии: зовущий
    решает сам, что делать без него, — а вставать на одном посте дороже, чем
    пропустить его. Чей это текст, говорит `what`: из записи журнала иначе не
    видно, на чём споткнулись.

    Ловится всё, а не только кривая форма ответа: поставщик отпечатков — не тот
    же, что чат-модель, и лежать они могут порознь. Не отвечающий адрес и
    незагруженная модель приезжают сюда бедами `httpx`, и пропусти мы их мимо —
    прогон вакансии умирал бы целиком из-за второстепенного шага.
    """
    try:
        return await lm_studio.embed(
            pipeline.lm_embed_client,
            pipeline.lm_embed_model,
            text[:_EMBED_MAX_CHARS],
        )
    except Exception:
        logger.exception("%s: не вышло посчитать отпечаток, пропускаю", what)
        return None


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
