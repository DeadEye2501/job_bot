"""Векторы вакансий: как их считают и как держат в памяти для отсева повторов."""

import logging

import numpy as np
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
            pipeline._lm_embed_client,
            pipeline._lm_embed_model,
            text[:_EMBED_MAX_CHARS],
        )
    except Exception:
        logger.exception("%s: не вышло посчитать отпечаток, пропускаю", what)
        return None


async def ensure_embedding_cache(pipeline) -> None:
    if pipeline._embedding_cache_loaded:
        return
    async with pipeline._session_factory() as session:
        rows = (
            await session.execute(
                select(Vacancy.id, Vacancy.embedding).where(
                    Vacancy.embedding.is_not(None)
                )
            )
        ).all()
    if rows:
        pipeline._embedding_ids = np.array(
            [r.id for r in rows], dtype=np.int64
        )
        pipeline._embedding_matrix = np.array(
            [r.embedding for r in rows], dtype=np.float32
        )
    pipeline._embedding_cache_loaded = True
    logger.debug("Embedding cache loaded: %d vectors", len(rows))


def append_embedding(pipeline, vacancy_id: int, embedding: list[float]) -> None:
    vec = np.asarray(embedding, dtype=np.float32)
    pipeline._embedding_ids = np.append(pipeline._embedding_ids, vacancy_id)
    if pipeline._embedding_matrix.size == 0:
        pipeline._embedding_matrix = vec.reshape(1, -1)
    else:
        pipeline._embedding_matrix = np.vstack([pipeline._embedding_matrix, vec])


def drop_embedding(pipeline, vacancy_id: int) -> None:
    idx = np.where(pipeline._embedding_ids == vacancy_id)[0]
    if idx.size == 0:
        return
    pipeline._embedding_ids = np.delete(pipeline._embedding_ids, idx)
    pipeline._embedding_matrix = np.delete(pipeline._embedding_matrix, idx, axis=0)
