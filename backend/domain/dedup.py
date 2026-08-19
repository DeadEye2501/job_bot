"""Отсев повторов: векторы заведённых вакансий и поиск ближайшего к новому."""

import logging
from collections.abc import Iterable

import numpy as np

logger = logging.getLogger(__name__)


def cosine_top_match(
    query: np.ndarray,
    ids: np.ndarray,
    matrix: np.ndarray,
    threshold: float,
) -> int | None:
    """Номер самой похожей вакансии; пусто — похожих нет.

    Порог приходит доводом и умолчания не имеет: живёт он в настройках
    (`dedup_cosine_threshold`), и второе его написание здесь разошлось бы с
    первым молча — в бою сюда всегда приходит настроенное.
    """
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


class EmbeddingCache:
    """Векторы заведённых вакансий в памяти — то, с чем сравнивают новый пост.

    Своей вещью, а не полями конвейера: номера и матрица связаны договором —
    строка матрицы и номер под тем же местом описывают одну вакансию, — а
    держали его четыре функции в двух чужих модулях, по договорённости.
    Здесь договор внутри одной вещи, и снаружи его не разорвать.

    Читать из базы кэш не умеет: это работа конвейера, он и приносит строки
    в `fill`. Здесь только память и сравнение.
    """

    def __init__(self) -> None:
        self.ids = np.empty((0,), dtype=np.int64)
        self.matrix = np.empty((0, 0), dtype=np.float32)
        # Поднимали ли уже. Подъём идёт один раз за жизнь конвейера, и без
        # этой отметки его повторяли бы на каждый пост.
        self.loaded = False

    def fill(
        self, pairs: Iterable[tuple[int, list[float]]], width: int
    ) -> int:
        """Поднять векторы из базы; сказать, сколько отброшено чужой длины.

        Длину задаёт модель отпечатков. Смени её в настройках, и в базе
        окажутся векторы двух длин; собранные в одну матрицу, они роняют
        подъём целиком — то есть отсев повторов перестаёт работать вовсе.
        Отброшенные не потеря: вектор прежней модели живёт в другом
        пространстве, и сравнивать его с нынешними нечем.
        """
        rows = list(pairs)
        fit = [(vacancy_id, vector) for vacancy_id, vector in rows
               if len(vector) == width]
        if fit:
            self.ids = np.array([i for i, _ in fit], dtype=np.int64)
            self.matrix = np.array([v for _, v in fit], dtype=np.float32)
        self.loaded = True
        return len(rows) - len(fit)

    def append(self, vacancy_id: int, vector: list[float]) -> None:
        """Дописать вектор только что заведённой вакансии.

        Дописывается сразу, а не ждёт следующего подъёма: иначе два одинаковых
        поста в одном обходе разошлись бы в две вакансии — второй сравнивали бы
        с памятью, где первого ещё нет.

        Матрица собирается первой, номер дописывается после: вектор чужой
        длины отсюда не принимается вовсе, и допиши мы номер раньше — номера с
        матрицей разъехались бы, а разъехавшись, роняют сравнение с любым
        следующим постом до самого перезапуска.
        """
        vec = np.asarray(vector, dtype=np.float32)
        if self.matrix.size == 0:
            self.matrix = vec.reshape(1, -1)
        else:
            self.matrix = np.vstack([self.matrix, vec])
        self.ids = np.append(self.ids, vacancy_id)

    def drop(self, vacancy_id: int) -> None:
        """Снять вектор вакансии; незнакомый номер кэш не трогает."""
        at = np.where(self.ids == vacancy_id)[0]
        if at.size == 0:
            return
        self.ids = np.delete(self.ids, at)
        self.matrix = np.delete(self.matrix, at, axis=0)

    def match(self, vector: list[float], threshold: float) -> int | None:
        """Номер похожей вакансии; пусто — похожих нет."""
        return cosine_top_match(
            np.asarray(vector, dtype=np.float32), self.ids, self.matrix, threshold
        )
