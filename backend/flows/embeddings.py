"""Кэш векторов вакансий: держит их в памяти для отсева повторов."""

import logging

import numpy as np
from sqlalchemy import select

from backend.models import Vacancy

logger = logging.getLogger(__name__)


async def _ensure_embedding_cache(pipeline) -> None:
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


def _append_embedding(pipeline, vacancy_id: int, embedding: list[float]) -> None:
    vec = np.asarray(embedding, dtype=np.float32)
    pipeline._embedding_ids = np.append(pipeline._embedding_ids, vacancy_id)
    if pipeline._embedding_matrix.size == 0:
        pipeline._embedding_matrix = vec.reshape(1, -1)
    else:
        pipeline._embedding_matrix = np.vstack([pipeline._embedding_matrix, vec])


def _drop_embedding(pipeline, vacancy_id: int) -> None:
    idx = np.where(pipeline._embedding_ids == vacancy_id)[0]
    if idx.size == 0:
        return
    pipeline._embedding_ids = np.delete(pipeline._embedding_ids, idx)
    pipeline._embedding_matrix = np.delete(pipeline._embedding_matrix, idx, axis=0)
