"""Следствия обращения к модели встраиваний.

Ответ чужой формы — не пустой отпечаток, а беда: пустым отпечатком приём
поста считает «этот текст не посчитался» и идёт дальше, а тут отвечать нечем.
"""

import httpx
import pytest

from adapters.lm_embed import embed
from tests.fakes.llm import EMBEDDINGS, provider


async def test_an_embedding_comes_back_as_a_list_of_numbers():
    """Встраивание достаётся из ответа списком чисел."""
    client = provider({
        EMBEDDINGS: httpx.Response(200, json={"data": [{"embedding": [0.1, 0.2]}]}),
    })
    assert await embed(client, "bge-m3", "привет") == [0.1, 0.2]


async def test_an_empty_embedding_response_fails_loudly():
    """Пустой ответ на встраивание — ошибка, а не пустой список."""
    client = provider({EMBEDDINGS: httpx.Response(200, json={"data": []})})
    with pytest.raises(RuntimeError, match="empty data"):
        await embed(client, "bge-m3", "привет")
async def test_an_embedding_without_numbers_fails_loudly():
    """Ответ без самого вектора — тоже ошибка."""
    client = provider({
        EMBEDDINGS: httpx.Response(200, json={"data": [{"embedding": None}]}),
    })
    with pytest.raises(RuntimeError, match="missing/invalid embedding"):
        await embed(client, "bge-m3", "привет")
async def test_embed_raises_when_the_provider_answers_with_an_error():
    """Провайдер ответил ошибкой на встраивание — исключение, а не тихий сбой."""
    client = provider({EMBEDDINGS: httpx.Response(500, text="сломалось")})
    with pytest.raises(httpx.HTTPStatusError):
        await embed(client, "bge-m3", "привет")
