"""Следствия счёта векторов из файла модели; настоящая модель не грузится.

Зовущие видят только `lm_studio.make_client`, `lm_embed.embed` и `lm_models`,
поэтому и проверки идут через них: файл модели должен попасть в свой
адаптер сам, по пустому адресу и пути к `.gguf` в настройках. Подменён один
вход в движок — `gguf_embed._open_model`.
"""

import asyncio
import time

import pytest

from adapters import lm_embed, lm_models
from adapters.gguf_embed import ModelFile, ModelUnavailable
from adapters.lm_studio import make_client
from backend.provider_config import LlmProviderConfig
from tests.fakes.gguf import Model, engine, engine_journal, failing_engine, model_file


@pytest.fixture
def journal(monkeypatch):
    """Журнал загрузок и закрытий подставной модели."""
    return engine_journal(monkeypatch)


def test_an_empty_address_with_a_model_file_gets_the_file_client(tmp_path):
    """Пустой адрес и путь к `.gguf` дают клиента файла, а не httpx."""
    path = model_file(tmp_path)

    client = make_client(LlmProviderConfig("", "", path))

    assert isinstance(client, ModelFile) and client.path == path


async def test_the_model_is_loaded_once_for_many_texts(journal, tmp_path):
    """Модель грузится при первом тексте и служит всем следующим."""
    path = model_file(tmp_path)
    client = ModelFile(path)

    assert await lm_embed.embed(client, path, "раз") == [3.0, 1.0]
    await lm_embed.embed(client, path, "два")

    assert journal == ["загружена"]


async def test_texts_asked_at_once_share_one_load(monkeypatch, tmp_path):
    """Тексты, попросившие вектор разом, не грузят модель каждый себе.

    Обход канала и прогон заново просят вектор независимо, и без замка каждый
    грузил бы свою копию в сотни мегабайт. Загрузка здесь нарочно медленная:
    мгновенная прошла бы по очереди и без замка.
    """
    happened: list[str] = []

    def slow(_path):
        time.sleep(0.05)
        return Model(happened)

    engine(monkeypatch, slow)
    client = ModelFile(model_file(tmp_path))

    await asyncio.gather(*(client.embed(str(n)) for n in range(5)))

    assert happened == ["загружена"]


async def test_a_missing_file_is_the_whole_model_unavailable(journal, tmp_path):
    """Файла нет — беда всей модели, и движок даже не зовётся."""
    client = ModelFile(str(tmp_path / "пропал.gguf"))

    with pytest.raises(ModelUnavailable):
        await client.embed("текст")

    assert journal == []


@pytest.mark.parametrize(
    "trouble",
    [
        pytest.param(ValueError("Failed to load model from file"), id="битый файл"),
        pytest.param(OSError("llama.dll not found"), id="нет библиотеки движка"),
        pytest.param(ImportError("No module named 'llama_cpp'"), id="нет движка"),
        pytest.param(RuntimeError("failed to create context"), id="сбой движка"),
    ],
)
async def test_a_file_the_engine_cannot_load_is_unavailable_too(monkeypatch, tmp_path, trouble):
    """Файл, который движок не грузит, — та же беда всей модели.

    Уйди она наружу как есть, приём поста счёл бы её бедой одного текста и
    шёл бы дальше, теряя посты, пока файл не починят.
    """
    failing_engine(monkeypatch, trouble)

    with pytest.raises(ModelUnavailable):
        await ModelFile(model_file(tmp_path)).embed("текст")


async def test_a_model_without_embeddings_is_unavailable(monkeypatch, tmp_path):
    """Чат-модель в том же формате — беда файла, а не текста.

    Она отдаёт вектор на каждый токен, и так она ответит на каждый пост.
    """
    engine(monkeypatch, lambda _path: Model([], per_token=True))
    path = model_file(tmp_path)

    with pytest.raises(ModelUnavailable):
        await ModelFile(path).embed("текст")
    ok, _detail = await lm_models.check_model(ModelFile(path), path, "embed")

    assert not ok


async def test_closing_frees_the_model_and_the_next_text_loads_it_again(journal, tmp_path):
    """Закрытие выгружает модель; следующий текст загружает её заново."""
    client = ModelFile(model_file(tmp_path))

    await client.embed("раз")
    await client.aclose()
    await client.embed("два")

    assert journal == ["загружена", "закрыта", "загружена"]


async def test_the_file_is_listed_only_while_it_is_on_disk(tmp_path):
    """Лампочка спрашивает перечень: файл в нём, пока лежит на диске."""
    path = model_file(tmp_path)
    gone = str(tmp_path / "пропал.gguf")

    assert await lm_models.model_listed(ModelFile(path), path) == (True, [path])
    assert (await lm_models.model_listed(ModelFile(gone), gone))[0] is False


async def test_a_check_loads_the_model_and_names_the_file(journal, tmp_path):
    """Проверка связи грузит модель и называет файл."""
    path = model_file(tmp_path)

    ok, detail = await lm_models.check_model(ModelFile(path), path, "embed")

    assert (ok, detail) == (True, "модель.gguf")
    assert journal == ["загружена"]


async def test_a_check_of_a_missing_file_says_so(tmp_path):
    """Проверка отсутствующего файла отвечает причиной, а не исключением."""
    gone = str(tmp_path / "пропал.gguf")

    ok, detail = await lm_models.check_model(ModelFile(gone), gone, "embed")

    assert not ok and "файла модели нет" in detail


async def test_an_engine_failure_on_the_probe_text_is_answered_not_raised(monkeypatch, tmp_path):
    """Сбой движка на пробном тексте — ответ проверки, а не исключение.

    Окно ждёт ответа с родом проверки; брошенное пришло бы без рода, и
    ожидание в окне не погасло бы.
    """

    class Failing(Model):
        def embed(self, text: str) -> list:
            raise RuntimeError(f"llama_decode returned -1 on {len(text)} chars")

    engine(monkeypatch, lambda _path: Failing([]))
    path = model_file(tmp_path)

    ok, detail = await lm_models.check_model(ModelFile(path), path, "embed")

    assert not ok and "llama_decode" in detail
