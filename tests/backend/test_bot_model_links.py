"""Смена поставщика модели в настройках у живого бота.

Соединения с моделями бот собирает при подъёме, а настройки меняются, пока он
работает. Не переподключись он — ходил бы к прежнему поставщику до
перезапуска приложения, и каждый разбор падал бы с отказом соединения.
Переподключается только сменившееся: Telegram и несменившийся клиент
остаются, иначе файл модели отпечатков грузился бы в память второй раз.
"""

import httpx
import pytest

from adapters import gguf_embed
from backend.flows import embeddings
from tests.fakes.ingestion import FakeIngestion, wire
from tests.fakes.lm_studio import LmClient

_FILE_A = "D:/models/bge-m3.gguf"
_FILE_B = "D:/models/e5.gguf"


class _CountedFile(gguf_embed.ModelFile):
    """Файл модели, который помнит, сколько раз его отпустили насовсем."""

    def __init__(self, path: str) -> None:
        super().__init__(path)
        self.retired = 0

    async def retire(self) -> None:
        self.retired += 1


@pytest.fixture
def files_too(monkeypatch):
    """Соединения стенда, где файл модели — настоящего рода, а не заглушка сервера.

    Ставится после сборки бота: `make_bot` подменяет сборку соединений своей.
    """

    def install() -> None:
        monkeypatch.setattr(
            "adapters.lm_studio.make_client",
            lambda cfg: _CountedFile(cfg.model) if cfg.names_model_file else LmClient(cfg.base_url),
        )

    return install


async def _embed_from(bot, path: str) -> None:
    await bot.rs.set_embed(base_url="", api_key="", model=path)
    await bot.reconnect_models()


async def test_a_changed_chat_provider_reaches_the_pipeline(make_bot):
    """Сменённый поставщик чата доходит до конвейера: разбор идёт к нему."""
    bot = await make_bot()

    await bot.rs.set_chat(base_url="http://новый.test", api_key="", model="sonnet")
    await bot.reconnect_models()

    assert bot.ingestion.lm_client.base_url == "http://новый.test"
    assert bot.ingestion.lm_chat_model == "sonnet"


async def test_a_changed_model_name_keeps_the_connection(make_bot):
    """Сменилось одно имя модели — соединение то же: модель задаётся в запросе."""
    bot = await make_bot(embed_url="http://векторы.test")
    before = bot.ingestion.lm_client

    await bot.rs.set_chat(base_url="http://provider.test", api_key="", model="llama")
    await bot.reconnect_models()

    assert bot.ingestion.lm_client is before
    assert bot.ingestion.lm_chat_model == "llama"


async def test_a_changed_chat_leaves_the_embeddings_connection(make_bot, files_too):
    """Сменённый чат не трогает соединение отпечатков.

    Пересобранное, оно грузило бы файл модели отпечатков в память заново.
    """
    bot = await make_bot(embed_url="http://векторы.test")
    files_too()
    await _embed_from(bot, _FILE_A)
    embed_before = bot.ingestion.lm_embed_client

    await bot.rs.set_chat(base_url="http://новый.test", api_key="", model="sonnet")
    await bot.reconnect_models()

    assert bot.ingestion.lm_embed_client is embed_before
    assert embed_before.retired == 0


async def test_a_chat_moved_to_the_embeddings_address_takes_their_connection(make_bot):
    """Чат, переведённый на адрес отпечатков, садится на их соединение.

    Собранное заново, общее соединение сменило бы клиента отпечатков, и кэш
    векторов перечитывался бы из базы зря.
    """
    bot = await make_bot(embed_url="http://векторы.test")
    embed_before = bot.ingestion.lm_embed_client

    await bot.rs.set_chat(base_url="http://векторы.test", api_key="", model="sonnet")
    await bot.reconnect_models()

    assert bot.ingestion.lm_client is embed_before
    assert bot.ingestion.lm_embed_client is embed_before


async def test_another_model_file_gets_its_own_connection(make_bot):
    """Другой файл модели отпечатков — другое соединение.

    У файла адреса нет, и сравни их по адресу с ключом — соединение
    осталось бы прежним, а отпечатки считала бы прежняя модель.
    """
    bot = await make_bot(embed_url="http://векторы.test")
    await _embed_from(bot, _FILE_A)
    first = bot.ingestion.lm_embed_client

    await _embed_from(bot, _FILE_B)

    assert bot.ingestion.lm_embed_client is not first


async def test_a_replaced_model_file_is_unloaded_at_once(make_bot, files_too):
    """Сменённый файл модели выгружается сразу, а не держит память до остановки.

    Выгрузка ждёт начатого вектора, и обрывать ей нечего; оставленная на
    потом, она держала бы в памяти прежнюю модель — а после возврата к ней
    и две её копии.
    """
    bot = await make_bot(embed_url="http://векторы.test")
    files_too()
    await _embed_from(bot, _FILE_A)
    first = bot.ingestion.lm_embed_client

    await _embed_from(bot, _FILE_B)

    assert first.retired == 1


async def test_a_vector_of_the_new_model_lifts_a_cache_of_the_old_one_anew(
    make_bot, monkeypatch
):
    """Первый вектор новой модели поднимает заново кэш, длину которому задала прежняя.

    Вектор прежней модели, посчитанный до смены и дошедший до кэша после,
    иначе оставил бы кэш прежней длины, и ни один вектор новой модели в него
    уже не встал бы — до перезапуска приложения.
    """
    bot = await make_bot(embed_url="http://векторы.test")
    bot.ingestion.embeddings.append(1, [0.1, 0.2, 0.3])

    async def embed(client, model, text):
        return [0.1, 0.2, 0.3, 0.4]

    monkeypatch.setattr("backend.flows.embeddings.lm_embed.embed", embed)
    await bot.rs.set_embed(base_url="http://векторы.test", api_key="", model="новая")
    await bot.reconnect_models()

    vector = await embeddings.embed_text(bot.ingestion, "пост", "проверка")
    bot.ingestion.embeddings.append(2, vector)

    assert bot.ingestion.embeddings.match(vector, threshold=0.9) == 2


async def test_a_failure_of_the_replaced_model_is_asked_again(make_bot, monkeypatch):
    """Беда прежней модели после смены — не беда: вектор считает нынешняя.

    Отданная наверх, она остановила бы пост как молчание поставщика, хотя
    нынешний поставщик в порядке.
    """
    bot = await make_bot(embed_url="http://векторы.test")
    asked: list[str] = []

    async def embed(client, model, text):
        asked.append(model)
        if len(asked) == 1:
            await bot.rs.set_embed(base_url="http://векторы.test", api_key="", model="новая")
            await bot.reconnect_models()
            raise httpx.ConnectError("прежний сервер ушёл")
        return [0.1, 0.2]

    monkeypatch.setattr("backend.flows.embeddings.lm_embed.embed", embed)

    vector = await embeddings.embed_text(bot.ingestion, "пост", "проверка")

    assert asked == ["qwen", "новая"]
    assert vector == [0.1, 0.2]


async def test_coming_back_to_a_server_takes_its_old_connection(make_bot):
    """Возврат к прежнему серверу берёт его же соединение, а не заводит новое.

    Новое при каждом возврате копило бы открытые соединения до остановки бота.
    Взятое снова, оно больше не числится сменённым и закрывается один раз.
    """
    bot = await make_bot(embed_url="http://векторы.test")
    first = bot.ingestion.lm_client

    await bot.rs.set_chat(base_url="http://новый.test", api_key="", model="sonnet")
    await bot.reconnect_models()
    await bot.rs.set_chat(base_url="http://provider.test", api_key="", model="qwen")
    await bot.reconnect_models()
    await bot.models.close()

    assert bot.ingestion.lm_client is first
    assert first.closed == 1


async def test_a_failed_close_still_closes_the_rest(make_bot):
    """Сорвавшееся закрытие одного соединения остальные не оставляет открытыми."""
    bot = await make_bot(embed_url="http://векторы.test")
    old = bot.ingestion.lm_client
    await bot.rs.set_chat(base_url="http://новый.test", api_key="", model="sonnet")
    await bot.reconnect_models()

    async def broken() -> None:
        raise OSError("гнездо")

    old.aclose = broken

    with pytest.raises(OSError):
        await bot.models.close()
    assert bot.models.providers.chat_client.closed == 1
    assert bot.models.providers.embed_client.closed == 1


async def test_a_vector_asked_of_the_replaced_model_is_asked_again(make_bot, monkeypatch):
    """Вектор, начатый прежней моделью и законченный после смены, считается заново.

    Попав первым в пустой кэш, он задал бы ему длину прежней модели, и ни
    один вектор новой туда уже не встал бы — до перезапуска приложения.
    """
    bot = await make_bot(embed_url="http://векторы.test")
    asked: list[str] = []

    async def embed(client, model, text):
        asked.append(model)
        if len(asked) == 1:
            await bot.rs.set_embed(base_url="http://векторы.test", api_key="", model="новая")
            await bot.reconnect_models()
            return [0.1, 0.2, 0.3]
        return [0.1, 0.2, 0.3, 0.4]

    monkeypatch.setattr("backend.flows.embeddings.lm_embed.embed", embed)

    vector = await embeddings.embed_text(bot.ingestion, "пост", "проверка")

    assert asked == ["qwen", "новая"]
    assert vector == [0.1, 0.2, 0.3, 0.4]


async def test_the_same_settings_change_nothing(make_bot):
    """Те же настройки бота не трогают: экран присылает их при каждом сохранении."""
    bot = await make_bot()
    before = (bot.ingestion.lm_client, bot.ingestion.embeddings)
    bot.ingestion.embeddings.loaded = True

    await bot.rs.set_chat(base_url="http://provider.test", api_key="", model="qwen")
    await bot.reconnect_models()

    assert (bot.ingestion.lm_client, bot.ingestion.embeddings) == before
    assert bot.ingestion.embeddings.loaded is True


async def test_a_bot_going_down_is_not_reconnected(make_bot):
    """Гаснущий бот не переподключается.

    Его соединения закрывает остановка, и собранные после её начала остались
    бы незакрытыми. Так бывает с ботом, упавшим сам: окно ещё числит его
    живым.
    """
    bot = await make_bot()
    before = bot.ingestion.lm_client
    bot.ingestion.mark_shutting_down()

    await bot.rs.set_chat(base_url="http://новый.test", api_key="", model="sonnet")
    await bot.reconnect_models()

    assert bot.ingestion.lm_client is before


async def test_a_replaced_connection_closes_with_the_bot_not_at_once(make_bot, caught_up):
    """Сменённое соединение с сервером закрывается вместе с ботом, а не в миг смены.

    Закрытое сразу, оно оборвало бы запрос, который по нему ещё идёт: разбор
    поста, начатый до сохранения настроек. Забытое вовсе — держало бы гнездо
    до конца работы приложения.
    """
    bot = await make_bot(embed_url="http://векторы.test")
    old = bot.ingestion.lm_client

    await bot.rs.set_chat(base_url="http://новый.test", api_key="", model="sonnet")
    await bot.reconnect_models()
    closed_at_swap = old.closed
    wire(bot, FakeIngestion())
    await bot.run(once=True)

    assert closed_at_swap == 0
    assert old.closed == 1
    assert bot.models.providers.chat_client.closed == 1


async def test_a_split_shared_connection_stays_with_embeddings_and_closes_once(
    make_bot, caught_up
):
    """Общее соединение, от которого ушёл чат, остаётся отпечаткам и закрывается раз.

    Закрытое при смене, оно оборвало бы отпечатки, которые по нему ходят;
    закрытое дважды — было бы обращением к уже закрытому.
    """
    bot = await make_bot()
    shared = bot.ingestion.lm_client

    await bot.rs.set_chat(base_url="http://новый.test", api_key="", model="sonnet")
    await bot.reconnect_models()
    wire(bot, FakeIngestion())
    await bot.run(once=True)

    assert bot.models.providers.embed_client is shared
    assert shared.closed == 1
