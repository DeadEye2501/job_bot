"""Числовой отпечаток текста у модели встраиваний.

Своим объявлением, а не рядом с чатом: поставщик отпечатков бывает отдельным
от чат-модели и лежать может на другом сервере, а форма ответа у него своя.
Файл модели без сервера считает `adapters/gguf_embed`.
"""

import httpx

from adapters import gguf_embed


async def embed(
    client: httpx.AsyncClient | gguf_embed.ModelFile, model: str, text: str
) -> list[float]:
    if isinstance(client, gguf_embed.ModelFile):
        return await client.embed(text)
    r = await client.post(
        "/v1/embeddings",
        json={"model": model, "input": text},
    )
    r.raise_for_status()
    payload = r.json()
    data = payload.get("data") or []
    if not data:
        raise RuntimeError(f"embed: empty data in response: {payload!r}")
    embedding = data[0].get("embedding")
    if not isinstance(embedding, list) or not embedding:
        raise RuntimeError(
            f"embed: missing/invalid embedding in response: {payload!r}"
        )
    return embedding
