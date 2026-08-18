"""Отпечаток текста: что бывает, когда поставщик отпечатков не отвечает.

Поставщик у отпечатков свой — не тот, что сочиняет и разбирает, — и лежать они
могут порознь. Поэтому его беда не должна ронять ни обход канала, ни прогон
вакансии: оба зовущих решают сами, что делать без отпечатка.
"""

import httpx
import pytest

from backend.flows import embeddings


class _Provider:
    """Поставщик отпечатков, который вместо ответа бросает заданное."""

    def __init__(self, error: Exception) -> None:
        self._error = error

    async def post(self, *_args, **_kwargs):
        raise self._error


class _Pipeline:
    """Столько конвейера, сколько нужно счёту отпечатка."""

    def __init__(self, client) -> None:
        self.lm_embed_client = client
        self.lm_embed_model = "bge"


@pytest.mark.parametrize(
    "error",
    [
        pytest.param(httpx.ConnectError("адрес молчит"), id="адрес молчит"),
        pytest.param(RuntimeError("форма ответа кривая"), id="ответ не разобрать"),
    ],
)
async def test_a_provider_that_broke_gives_no_fingerprint(error, caplog):
    """Беда поставщика отвечает пустотой, а не броском наружу.

    Улетев наружу, она уносила бы с собой и разбор вакансии — работу, ради
    которой человек и нажал кнопку.
    """
    pipeline = _Pipeline(_Provider(error))

    with caplog.at_level("ERROR"):
        assert await embeddings.embed_text(pipeline, "текст", "vacancy 7") is None

    assert "vacancy 7" in caplog.text


async def test_the_fingerprint_comes_back_when_the_provider_answers():
    """Отвечающий поставщик отдаёт вектор как есть."""

    class _Answering:
        async def post(self, *_args, **_kwargs):
            return httpx.Response(
                200,
                json={"data": [{"embedding": [0.5, 0.25]}]},
                request=httpx.Request("POST", "http://provider.test/v1/embeddings"),
            )

    pipeline = _Pipeline(_Answering())

    assert await embeddings.embed_text(pipeline, "текст", "vacancy 7") == [0.5, 0.25]


async def test_a_very_long_text_is_cut_before_it_goes_to_the_provider():
    """Длинный текст режется до отправки, а не отвергается поставщиком.

    К посту дописывается статья по ссылке, и вместе они перерастают окно
    модели отпечатков. Отказ поставщика приходит наверх пустым отпечатком, а
    пустой отпечаток на приёме означает, что объявление не завели вовсе —
    и второй раз его не увидят, курсор канала уже уехал.
    """
    sent = []

    class _Watching:
        async def post(self, _path, json=None, **_kwargs):
            sent.append(json["input"])
            return httpx.Response(
                200,
                json={"data": [{"embedding": [0.5]}]},
                request=httpx.Request("POST", "http://provider.test/v1/embeddings"),
            )

    pipeline = _Pipeline(_Watching())

    await embeddings.embed_text(pipeline, "я" * 20_000, "vacancy 7")

    assert len(sent[0]) == 6000
    assert sent[0] == "я" * 6000
