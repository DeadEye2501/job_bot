"""Следствия, которые наблюдают тесты поиска похожего вектора.

`cosine_top_match` отвечает на вопрос «есть ли среди известных вакансий та же
самая» — то есть решает, дубль перед нами или новый пост. Поэтому проверяется
не число косинуса, а какой идентификатор вернулся и вернулся ли вообще.
"""

import numpy as np
import pytest

from backend.domain import cosine_top_match

IDS = np.array([10, 20, 30])
MATRIX = np.array([[1.0, 0.0], [0.0, 1.0], [0.9, 0.1]], dtype=np.float32)


def test_an_exact_match_returns_its_identifier():
    """Совпавший вектор возвращается своим идентификатором, а не позицией."""
    assert cosine_top_match(np.array([1.0, 0.0]), IDS, MATRIX) == 10


def test_a_similarity_below_the_threshold_returns_nothing():
    """Похожий, но недостаточно — не совпадение."""
    assert cosine_top_match(np.array([0.6, 0.8]), IDS, MATRIX) is None


def test_lowering_the_threshold_lets_a_weaker_match_through():
    """Порог задаётся вызывающим и решает, что считать тем же самым."""
    assert cosine_top_match(np.array([0.6, 0.8]), IDS, MATRIX, threshold=0.5) == 20


def test_a_zero_query_matches_nothing():
    """Нулевой вектор запроса не совпадает ни с чем и не делит на ноль."""
    assert cosine_top_match(np.array([0.0, 0.0]), IDS, MATRIX) is None


def test_an_empty_index_matches_nothing():
    """Пустой набор известных векторов — совпадать не с чем."""
    got = cosine_top_match(np.array([1.0, 0.0]), np.array([]), np.zeros((0, 2)))
    assert got is None


def test_an_index_of_only_zero_vectors_matches_nothing():
    """Все известные векторы нулевые — совпадения нет, деления на ноль тоже."""
    got = cosine_top_match(
        np.array([1.0, 0.0]), np.array([1, 2]), np.zeros((2, 2), dtype=np.float32)
    )
    assert got is None


def test_a_query_of_the_wrong_width_matches_nothing():
    """Вектор другой размерности не совпадает, а не падает."""
    assert cosine_top_match(np.array([1.0, 0.0, 0.0]), IDS, MATRIX) is None


def test_a_broken_index_fails_loudly_instead_of_returning_garbage():
    """Рассинхрон идентификаторов и матрицы — ошибка вызывающего, и она видна."""
    with pytest.raises(ValueError, match="length mismatch"):
        cosine_top_match(np.array([1.0, 0.0]), np.array([1, 2]), MATRIX)
