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


def test_a_cache_of_another_width_is_lifted_anew():
    """Кэш, длина которого разошлась с нынешней моделью, поднимается заново.

    Первым в кэш мог попасть вектор прежней модели, посчитанный до её смены:
    оставленный, такой кэш не принял бы ни одного вектора новой.
    """
    cache = EmbeddingCache()
    cache.fill([(1, [1.0, 0.0])], width=2)

    cache.settle_width(3)
    cache.append(2, [0.0, 0.0, 1.0])

    assert cache.loaded is False
    assert cache.match([0.0, 0.0, 1.0], threshold=0.9) == 2


def test_the_same_width_keeps_the_cache():
    """Та же длина кэш не трогает: подъём из базы идёт один раз за жизнь."""
    cache = EmbeddingCache()
    cache.fill([(1, [1.0, 0.0])], width=2)

    cache.settle_width(2)

    assert cache.loaded is True
    assert cache.match([1.0, 0.0], threshold=0.9) == 1


def test_a_vector_added_while_lifting_survives_the_lift():
    """Вектор, дописанный, пока шло чтение базы, подъём не стирает.

    Чтение начато до того, как вакансию записали, и её в прочитанном нет;
    стёртый, её вектор не узнал бы перепоста до перезапуска.
    """
    cache = EmbeddingCache()
    cache.append(2, [0.0, 1.0])

    cache.fill([(1, [1.0, 0.0])], width=2)

    assert cache.match([0.0, 1.0], threshold=0.9) == 2
    assert cache.match([1.0, 0.0], threshold=0.9) == 1


def test_a_lift_drops_a_vector_of_another_width_added_meanwhile():
    """Подъём выбрасывает дописанный за время чтения вектор чужой длины.

    Его посчитала прежняя модель, а длину кэшу уже назвала нынешняя:
    оставленный, он не дал бы встать ни одному вектору новой модели.
    """
    cache = EmbeddingCache()
    cache.append(2, [0.0, 1.0])

    cache.fill([], width=3)
    cache.append(3, [0.0, 0.0, 1.0])

    assert cache.match([0.0, 0.0, 1.0], threshold=0.9) == 3


def test_a_lift_keeps_the_vector_recounted_while_reading():
    """Вектор, пересчитанный прогоном заново за время чтения, не уступает прочитанному.

    Прочитанное из базы старее: чтение начато до записи нового вектора, и
    взявший его кэш узнавал бы вакансию по тексту, которого у неё уже нет.
    """
    cache = EmbeddingCache()
    cache.append(1, [0.0, 1.0])

    cache.fill([(1, [1.0, 0.0])], width=2)

    assert cache.match([1.0, 0.0], threshold=0.9) is None
    assert cache.match([0.0, 1.0], threshold=0.9) == 1
