"""Соединения бота с моделями: сборка, подмена на сменённого поставщика, закрытие."""

import logging

from adapters import lm_studio
from adapters.lm_studio import LmClient
from backend.flows.pipeline import LmProviders
from backend.provider_config import LlmProviderConfig

logger = logging.getLogger(__name__)

Link = tuple[LlmProviderConfig, LmClient]
"""Поставщик и соединение, собранное под него."""


def _shares_provider(a, b) -> bool:
    """Two LLM provider configs share the same httpx client if endpoint+auth match.

    Model name is intentionally NOT compared — model is per-request, not on
    the client.
    """
    return (
        a is not None
        and b is not None
        and a.base_url == b.base_url
        and a.api_key == b.api_key
    )


def _fits(had: LlmProviderConfig, wanted: LlmProviderConfig) -> bool:
    """Годится ли соединение, собранное под `had`, для `wanted`.

    Имя модели у сервера едет в каждом запросе, а у файла модели оно и есть
    соединение: другой файл — другая загруженная модель.
    """
    return _shares_provider(had, wanted) and (
        not had.names_model_file or had.model == wanted.model
    )


def _kept_or_new(wanted: LlmProviderConfig, had: list[Link]) -> LmClient:
    """Любое прежнее соединение, которое годится для поставщика, иначе новое.

    Ищется среди всех прежних, а не только своего рода: чат, переведённый на
    адрес отпечатков, садится на их соединение, и кэш векторов не
    перечитывается зря; возврат к прежнему серверу берёт его же соединение,
    а не копит новые до остановки бота.
    """
    for config, client in had:
        if _fits(config, wanted):
            return client
    return lm_studio.make_client(wanted)


def _links(chat: LlmProviderConfig, embed: LlmProviderConfig, had: list[Link]) -> LmProviders:
    """Соединения под поставщиков; прежнее берётся там, где оно годится.

    Пересобранное без нужды соединение отпечатков из файла грузило бы модель
    в память второй раз.
    """
    chat_client = _kept_or_new(chat, had)
    if _shares_provider(chat, embed):
        embed_client = chat_client
    else:
        embed_client = _kept_or_new(embed, had)
    return LmProviders(
        chat_client=chat_client,
        chat_model=chat.model,
        embed_client=embed_client,
        embed_model=embed.model,
    )


class ModelLinks:
    """Соединения с моделями, поставщики, под которых они собраны, и сменённые.

    Сменённое соединение с сервером закрывается вместе с ботом, а не в миг
    смены: по нему может идти начатый запрос — разбор поста, отпечаток, — и
    закрытие оборвало бы его. Сменённый файл модели отпускается сразу
    (`lm_studio.retires_at_once`).
    """

    def __init__(self, chat: LlmProviderConfig, embed: LlmProviderConfig) -> None:
        self._configs = (chat, embed)
        self.providers = _links(chat, embed, [])
        self._retired: list[Link] = []
        self._to_retire: list[LmClient] = []

    def _current(self) -> list[Link]:
        return list(zip(self._configs, (self.providers.chat_client, self.providers.embed_client)))

    def _clients(self) -> dict[int, LmClient]:
        """Нынешние соединения; общее чату и отпечаткам — одно."""
        return {id(client): client for _, client in self._current()}

    def switch_to(self, chat: LlmProviderConfig, embed: LlmProviderConfig) -> bool:
        """Собрать соединения под поставщиков; `False` — те же, менять нечего.

        Сверка идёт с тем, под что собраны соединения, а не с прежней записью
        настроек: сорвись запись посреди двух поставщиков, следующая сверка
        всё равно увидит расхождение.
        """
        if (chat, embed) == self._configs:
            return False
        before = self._current()
        self.providers = _links(chat, embed, before + self._retired)
        self._configs = (chat, embed)
        in_use = self._clients()
        self._retired = [link for link in self._retired if id(link[1]) not in in_use]
        dropped = {id(client): (config, client) for config, client in before
                   if id(client) not in in_use}
        for config, client in dropped.values():
            if lm_studio.retires_at_once(client):
                self._to_retire.append(client)
            else:
                self._retired.append((config, client))
        return True

    async def retire_dropped(self) -> None:
        """Отпустить сменённые файлы моделей: их выгрузка работу не обрывает."""
        while self._to_retire:
            await self._to_retire.pop().retire()

    async def close(self) -> None:
        """Закрыть все соединения: нынешние, сменённые и ждущие выгрузки.

        Сбой одного закрытия остальных не отменяет: каждое незакрытое держит
        гнездо или модель в памяти до конца работы приложения. Первая беда
        поднимается после того, как закрыты все.
        """
        clients = [*self._to_retire, *(c for _, c in self._retired), *self._clients().values()]
        trouble: Exception | None = None
        for client in clients:
            try:
                await client.aclose()
            except Exception as e:
                trouble = trouble or e
        if trouble is not None:
            raise trouble


async def reconnect(bot) -> None:
    """Перевести бота и конвейер на поставщиков, записанных в настройках сейчас.

    Гаснущему боту переподключаться незачем: его соединения закрывает
    остановка, и собранные после её начала остались бы незакрытыми. Так
    бывает с ботом, упавшим сам: в хозяйстве окна он числится, пока его не
    уберёт обработчик падения.

    Конвейер получает новые соединения до выгрузки прежних: к выгружаемому
    файлу модели он уже не обратится.
    """
    if bot.ingestion.shutting_down:
        return
    chat, embed = bot.rs.chat, bot.rs.embed
    if not bot.models.switch_to(chat, embed):
        return
    bot.ingestion.use_models(bot.models.providers)
    logger.info(
        "соединения с моделями переподключены: чат %s, отпечатки %s", chat.model, embed.model
    )
    await bot.models.retire_dropped()
