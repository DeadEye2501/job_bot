"""Отпечаток текста: что бывает, когда поставщик отпечатков не отвечает.

Поставщик у отпечатков свой — не тот, что сочиняет и разбирает, — и лежать они
могут порознь. Беды его двух родов, и разводят их здесь. Отказ на самом
тексте отвечает пустотой: зовущий решает сам, что делать без отпечатка, и
разбор вакансии из-за второстепенного шага не умирает. Молчание же поставщика
целиком поднимается броском: оно придёт на каждый следующий текст, а приём
поста, пропустив его, потерял бы объявление навсегда.
"""

import httpx
import pytest

from adapters import gguf_embed
from backend.flows import embeddings
from tests.fakes.gguf import failing_engine, model_file
from tests.fakes.llm import embeddings_refused, embeddings_request


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


async def test_a_text_the_provider_choked_on_gives_no_fingerprint(caplog):
    """Беда об этом тексте отвечает пустотой, а не броском наружу.

    Улетев наружу, она уносила бы с собой и разбор вакансии — работу, ради
    которой человек и нажал кнопку, — а следующий текст посчитается.
    """
    pipeline = _Pipeline(_Provider(RuntimeError("форма ответа кривая")))

    with caplog.at_level("ERROR"):
        assert await embeddings.embed_text(pipeline, "текст", "vacancy 7") is None

    assert "vacancy 7" in caplog.text


@pytest.mark.parametrize(
    "error",
    [
        pytest.param(httpx.ConnectError("адрес молчит"), id="адрес молчит"),
        pytest.param(
            embeddings_refused(404, "model not found"),
            id="модели у поставщика нет",
        ),
        pytest.param(
            embeddings_refused(503, "server error"),
            id="поставщик сломан",
        ),
    ],
)
async def test_a_provider_that_answers_nobody_is_raised_not_swallowed(error):
    """Молчание самого поставщика поднимается броском.

    Оно придёт на каждый следующий текст подряд, и приём поста, приняв его за
    пустой отпечаток, увёл бы отметку канала до самого свежего сообщения —
    объявления между ними не прочтёт уже никто.
    """
    pipeline = _Pipeline(_Provider(error))

    with pytest.raises(embeddings.ProviderIsSilent):
        await embeddings.embed_text(pipeline, "текст", "vacancy 7")


async def test_the_fingerprint_comes_back_when_the_provider_answers():
    """Отвечающий поставщик отдаёт вектор как есть."""

    class _Answering:
        async def post(self, *_args, **_kwargs):
            return httpx.Response(
                200,
                json={"data": [{"embedding": [0.5, 0.25]}]},
                request=embeddings_request(),
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
                request=embeddings_request(),
            )

    pipeline = _Pipeline(_Watching())

    await embeddings.embed_text(pipeline, "я" * 20_000, "vacancy 7")

    assert len(sent[0]) == 6000
    assert sent[0] == "я" * 6000


async def test_a_model_file_that_will_not_load_silences_the_provider(monkeypatch, tmp_path):
    """Незагружаемый файл модели — молчание поставщика, а не беда одного текста.

    Сочти приём её бедой текста — курсор канала уехал бы мимо постов, которые
    не посчитаются, пока файл не вернут на место.
    """
    failing_engine(monkeypatch, ValueError("Failed to load model from file"))
    pipeline = _Pipeline(gguf_embed.ModelFile(model_file(tmp_path)))

    with pytest.raises(embeddings.ProviderIsSilent):
        await embeddings.embed_text(pipeline, "текст", "vacancy 7")
