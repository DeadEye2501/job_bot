"""Подъём кэша векторов из базы — то, чем занят сам конвейер.

Каждый новый пост сравнивается со всеми уже собранными вакансиями. Читать их
векторы из базы на каждый пост — это тысячи строк по мегабайту на канал;
поэтому они один раз поднимаются в память и дальше правятся на месте.

Здесь только поход в базу и его следствия. Что кэш делает с поднятым — в
`test_domain_embedding_cache.py`.
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

    await embeddings.ensure_embedding_cache(pipeline, width=2)

    assert pipeline.embeddings.ids.tolist() == [1]
    assert np.allclose(pipeline.embeddings.matrix, [[0.1, 0.2]])


async def test_an_empty_base_leaves_the_cache_empty(make_pipeline):
    """На базе без векторов кэш остаётся пустым, а не ломается."""
    pipeline = await make_pipeline()

    await embeddings.ensure_embedding_cache(pipeline, width=2)

    assert pipeline.embeddings.ids.size == 0
    assert pipeline.embeddings.matrix.size == 0


async def test_the_cache_is_loaded_only_once(make_pipeline, session_factory):
    """Второй заход за кэшем базу не трогает.

    Он делается на каждом обходе каналов; перечитывать тысячи векторов
    по расписанию незачем.
    """
    await put(session_factory, vacancy_row(title="первая", embedding=[0.1, 0.2]))
    pipeline = await make_pipeline()
    await embeddings.ensure_embedding_cache(pipeline, width=2)

    await put(session_factory, vacancy_row(title="вторая", embedding=[0.3, 0.4]))
    await embeddings.ensure_embedding_cache(pipeline, width=2)

    assert pipeline.embeddings.ids.tolist() == [1]


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

    await embeddings.ensure_embedding_cache(pipeline, width=2)

    lifted = dict(
        zip(pipeline.embeddings.ids.tolist(), pipeline.embeddings.matrix.tolist())
    )
    expected = {
        row.id: row.embedding for row in await all_rows(session_factory, Vacancy)
    }
    assert lifted.keys() == expected.keys()
    for vacancy_id, vector in lifted.items():
        assert np.allclose(vector, expected[vacancy_id])


async def test_the_dropped_vectors_are_counted_out_loud(
    make_pipeline, session_factory, caplog
):
    """Про отброшенные векторы чужой длины конвейер говорит в журнал.

    Отбор делает сам кэш, но узнать о нём можно только отсюда: вернуть такие
    векторы в дело может лишь прогон заново по каждой вакансии, и человеку
    нужен повод об этом задуматься.
    """
    await put(
        session_factory,
        vacancy_row(title="прежняя модель", embedding=[0.1, 0.2, 0.3]),
        vacancy_row(title="нынешняя модель", embedding=[0.4, 0.5]),
    )
    pipeline = await make_pipeline()

    with caplog.at_level("WARNING"):
        await embeddings.ensure_embedding_cache(pipeline, width=2)

    assert pipeline.embeddings.ids.tolist() == [2]
    assert np.allclose(pipeline.embeddings.matrix, [[0.4, 0.5]])
    assert "1" in caplog.text
