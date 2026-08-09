"""Поиск ближайшей вакансии по косинусной близости эмбеддингов."""

import logging

import numpy as np

logger = logging.getLogger(__name__)


def cosine_top_match(
    query: np.ndarray,
    ids: np.ndarray,
    matrix: np.ndarray,
    threshold: float = 0.92,
) -> int | None:
    # Runtime-check вместо `assert` — assert'ы выпиливаются `python -O`
    # и invariant проверки не работают в production. Длина mismatch'а —
    # bug в caller'е (плохая консистентность embedding-cache'а), лучше
    # быстро упасть с понятным сообщением, чем тихо вернуть мусор.
    if len(ids) != matrix.shape[0]:
        raise ValueError(
            f"cosine_top_match: ids/matrix length mismatch ({len(ids)} vs {matrix.shape[0]})"
        )
    if matrix.size == 0:
        return None
    q = np.asarray(query, dtype=np.float32)
    qn = float(np.linalg.norm(q))
    if qn == 0:
        return None
    if matrix.shape[1] != q.shape[0]:
        logger.warning(
            "cosine_top_match: dim mismatch — query %d, matrix %d",
            q.shape[0],
            matrix.shape[1],
        )
        return None
    norms = np.linalg.norm(matrix, axis=1)
    mask = norms > 0
    if not mask.any():
        return None
    sims = np.full(len(ids), -1.0, dtype=np.float32)
    sims[mask] = (matrix[mask] @ q) / (norms[mask] * qn)
    best = int(np.argmax(sims))
    if sims[best] >= threshold:
        return int(ids[best])
    return None
