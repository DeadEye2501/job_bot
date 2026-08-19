"""Следствия кэша отпечатков, по которым отсеиваются повторы вакансий.

Кэш держит две вещи парой: номера вакансий и матрицу их векторов. Договор
между ними несущий — строка матрицы и номер под тем же местом обязаны
описывать одну вакансию, — и проверяется он здесь косвенно: через то, чей
номер отдаёт поиск похожего.

Векторы чужой длины — не выдумка: длину задаёт модель отпечатков, и стоит
сменить её в настройках, как в базе оказываются две.
"""

import pytest

from backend.domain.dedup import EmbeddingCache


def test_an_empty_cache_finds_nobody():
    """Пустому кэшу сравнивать не с чем, и он молчит, а не падает."""
    assert EmbeddingCache().match([0.1, 0.2], threshold=0.9) is None


def test_an_added_vector_is_found_by_its_own_number():
    """Добавленный вектор находится, и находится под своим номером."""
    cache = EmbeddingCache()
    cache.append(7, [1.0, 0.0])

    assert cache.match([1.0, 0.0], threshold=0.9) == 7


def test_a_stranger_is_not_found():
    """Непохожий вектор похожим не считается."""
    cache = EmbeddingCache()
    cache.append(7, [1.0, 0.0])

    assert cache.match([0.0, 1.0], threshold=0.9) is None


def test_a_dropped_vector_is_no_longer_found():
    """Снятый вектор больше не находится: вакансию удалили из базы."""
    cache = EmbeddingCache()
    cache.append(7, [1.0, 0.0])
    cache.drop(7)

    assert cache.match([1.0, 0.0], threshold=0.9) is None


def test_dropping_shifts_the_rest_together_with_their_numbers():
    """Снятие сдвигает и номера, и строки матрицы — вместе.

    Разъедься они, поиск отдал бы номер соседней вакансии, и объявление
    отсеялось бы как повтор чужого.
    """
    cache = EmbeddingCache()
    cache.append(1, [1.0, 0.0])
    cache.append(2, [0.0, 1.0])
    cache.append(3, [1.0, 1.0])

    cache.drop(1)

    assert cache.match([0.0, 1.0], threshold=0.9) == 2


def test_dropping_something_absent_changes_nothing():
    """Снятие незнакомого номера кэш не трогает."""
    cache = EmbeddingCache()
    cache.append(7, [1.0, 0.0])

    cache.drop(999)

    assert cache.match([1.0, 0.0], threshold=0.9) == 7


def test_filling_keeps_only_the_current_width():
    """При подъёме из базы берутся только векторы нынешней длины.

    Собранные в одну матрицу, разные длины роняют подъём целиком — то есть
    отсев повторов перестаёт работать вовсе.
    """
    cache = EmbeddingCache()

    dropped = cache.fill([(1, [1.0, 0.0, 0.0]), (2, [0.0, 1.0])], width=2)

    assert dropped == 1
    assert cache.match([0.0, 1.0], threshold=0.9) == 2


def test_a_filled_cache_says_it_is_filled():
    """Кэш помнит, что его уже поднимали: подъём идёт один раз за жизнь."""
    cache = EmbeddingCache()
    assert cache.loaded is False

    cache.fill([], width=2)

    assert cache.loaded is True


def test_a_vector_of_another_width_leaves_the_cache_whole():
    """Не принятый вектор чужой длины кэш не разъезжает.

    Длина задана моделью отпечатков, и сменить её можно посреди работы.
    Дописка такого вектора не удаётся — но номера и матрица обязаны остаться
    парой: разъехавшись, они роняют сравнение с любым следующим постом, и
    отсев повторов не работает до перезапуска, а посты канала уходят мимо.
    """
    cache = EmbeddingCache()
    cache.append(1, [1.0, 0.0])

    with pytest.raises(ValueError):
        cache.append(2, [1.0, 0.0, 0.0])

    assert cache.match([1.0, 0.0], threshold=0.9) == 1


def test_an_emptied_cache_takes_new_vectors():
    """Опустевший кэш принимает новые векторы, а не остаётся сломанным."""
    cache = EmbeddingCache()
    cache.append(1, [1.0, 0.0])
    cache.drop(1)

    cache.append(2, [0.0, 1.0])

    assert cache.match([0.0, 1.0], threshold=0.9) == 2
