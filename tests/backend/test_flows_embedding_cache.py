"""Следствия кэша векторов, по которым ищут повторы вакансий.

Каждый новый пост сравнивается со всеми уже собранными вакансиями. Читать их
векторы из базы на каждый пост — это тысячи строк по мегабайту на канал;
поэтому они один раз поднимаются в память и дальше правятся на месте: новая
вакансия дописывается, удалённая вычёркивается.

Загрузка идёт ровно один раз за жизнь конвейера. Повторный заход должен быть
бесплатным: его делает каждый обход каналов.
"""

from backend.flows import embeddings
import numpy as np

from backend.models import Vacancy
from tests.dbio import all_rows, put
from tests.factories import vacancy_row


async def test_the_saved_vectors_are_lifted_into_memory(
    make_pipeline, session_factory
):
    """Векторы сохранённых вакансий поднимаются в память.

    По ним ищут повтор для каждого нового поста; читать их из базы
    каждый раз значило бы тянуть мегабайты на объявление. Вакансия без
    вектора в кэш не идёт: сравнивать у неё нечего — она либо ещё не
    разобрана, либо разбор до векторов не дошёл.
    """
    await put(
        session_factory,
        vacancy_row(title="с вектором", embedding=[0.1, 0.2]),
        vacancy_row(title="без вектора"),
    )
    pipeline = await make_pipeline()

    await embeddings.ensure_embedding_cache(pipeline)

    assert pipeline._embedding_ids.tolist() == [1]
    assert np.allclose(pipeline._embedding_matrix, [[0.1, 0.2]])


async def test_an_empty_base_leaves_the_cache_empty(make_pipeline):
    """На базе без векторов кэш остаётся пустым, а не ломается."""
    pipeline = await make_pipeline()

    await embeddings.ensure_embedding_cache(pipeline)

    assert pipeline._embedding_ids.size == 0
    assert pipeline._embedding_matrix.size == 0


async def test_the_cache_is_loaded_only_once(make_pipeline, session_factory):
    """Второй заход за кэшем базу не трогает.

    Он делается на каждом обходе каналов; перечитывать тысячи векторов
    по расписанию незачем.
    """
    await put(session_factory, vacancy_row(title="первая", embedding=[0.1, 0.2]))
    pipeline = await make_pipeline()
    await embeddings.ensure_embedding_cache(pipeline)

    await put(session_factory, vacancy_row(title="вторая", embedding=[0.3, 0.4]))
    await embeddings.ensure_embedding_cache(pipeline)

    assert pipeline._embedding_ids.tolist() == [1]


async def test_a_new_vacancy_is_added_to_the_cache(make_pipeline):
    """Новая вакансия дописывается в кэш, а не ждёт перезагрузки.

    Иначе два одинаковых поста в одном обходе разошлись бы в две
    вакансии: второй сравнивался бы с памятью, где первого ещё нет.
    """
    pipeline = await make_pipeline()
    await embeddings.ensure_embedding_cache(pipeline)

    embeddings.append_embedding(pipeline, 7, [0.1, 0.2])

    assert pipeline._embedding_ids.tolist() == [7]
    assert np.allclose(pipeline._embedding_matrix, [[0.1, 0.2]])


async def test_a_second_vacancy_is_added_below_the_first(make_pipeline):
    """Вторая вакансия ложится под первую, не затирая её."""
    pipeline = await make_pipeline()
    await embeddings.ensure_embedding_cache(pipeline)

    embeddings.append_embedding(pipeline, 7, [0.1, 0.2])
    embeddings.append_embedding(pipeline, 8, [0.3, 0.4])

    assert pipeline._embedding_ids.tolist() == [7, 8]
    assert np.allclose(pipeline._embedding_matrix, [[0.1, 0.2], [0.3, 0.4]])


async def test_a_deleted_vacancy_leaves_the_cache(make_pipeline):
    """Удалённая вакансия вычёркивается из кэша вместе со своим вектором.

    Оставшись, она сравнивалась бы с новыми постами и объявляла бы их
    повторами того, чего в базе больше нет.
    """
    pipeline = await make_pipeline()
    await embeddings.ensure_embedding_cache(pipeline)
    embeddings.append_embedding(pipeline, 7, [0.1, 0.2])
    embeddings.append_embedding(pipeline, 8, [0.3, 0.4])
    embeddings.append_embedding(pipeline, 9, [0.5, 0.6])

    embeddings.drop_embedding(pipeline, 8)

    assert pipeline._embedding_ids.tolist() == [7, 9]
    assert np.allclose(pipeline._embedding_matrix, [[0.1, 0.2], [0.5, 0.6]])


async def test_dropping_something_absent_changes_nothing(make_pipeline):
    """Вычёркивание того, чего в кэше нет, ничего не меняет и не падает.

    Удалить можно и вакансию без вектора — неразобранную или ту, у
    которой разбор не дошёл до конца.
    """
    pipeline = await make_pipeline()
    await embeddings.ensure_embedding_cache(pipeline)
    embeddings.append_embedding(pipeline, 7, [0.1, 0.2])

    embeddings.drop_embedding(pipeline, 99)

    assert pipeline._embedding_ids.tolist() == [7]
    assert np.allclose(pipeline._embedding_matrix, [[0.1, 0.2]])


async def test_the_cache_survives_being_emptied(make_pipeline):
    """Опустошённый кэш остаётся пригодным: в него снова можно дописывать."""
    pipeline = await make_pipeline()
    await embeddings.ensure_embedding_cache(pipeline)
    embeddings.append_embedding(pipeline, 7, [0.1, 0.2])
    embeddings.drop_embedding(pipeline, 7)

    embeddings.append_embedding(pipeline, 8, [0.3, 0.4])

    assert pipeline._embedding_ids.tolist() == [8]
    assert np.allclose(pipeline._embedding_matrix, [[0.3, 0.4]])


async def test_the_lifted_vectors_keep_their_vacancy_numbers(
    make_pipeline, session_factory
):
    """Поднятые векторы остаются при своих номерах вакансий.

    По номеру найденный повтор и опознаётся; перепутанный порядок
    привязал бы новый пост к чужой вакансии.
    """
    await put(
        session_factory,
        vacancy_row(title="первая", embedding=[0.1, 0.2]),
        vacancy_row(title="вторая", embedding=[0.3, 0.4]),
    )
    pipeline = await make_pipeline()

    await embeddings.ensure_embedding_cache(pipeline)

    lifted = dict(
        zip(pipeline._embedding_ids.tolist(), pipeline._embedding_matrix.tolist())
    )
    expected = {
        row.id: row.embedding for row in await all_rows(session_factory, Vacancy)
    }
    assert lifted.keys() == expected.keys()
    for vacancy_id, vector in lifted.items():
        assert np.allclose(vector, expected[vacancy_id])
