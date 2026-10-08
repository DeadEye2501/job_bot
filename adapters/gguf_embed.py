"""Эмбеддинги из GGUF-файла модели, посчитанные в своём процессе без сервера.

Надстройка рядом с OpenAI-совместимым путём: точки входа
(`lm_studio`, `lm_embed`, `lm_models`) узнают этого клиента по типу и отдают
его сюда. Пустой адрес и путь к `.gguf` в настройках — его признак.
"""

import asyncio
import logging
import os
import threading

_log = logging.getLogger(__name__)

# Окно контекста подобрано под bge-m3. Текст режется до 6000 знаков
# (`flows/embeddings`), это две-три тысячи токенов — запас двойной.
CONTEXT_TOKENS = 8192

# Чем движок отвечает на файл, который не грузится: нет библиотеки движка,
# битый или чужой файл, нехватка памяти. Всё это — беда модели целиком.
_LOAD_TROUBLES = (ImportError, OSError, RuntimeError, ValueError)


class ModelUnavailable(Exception):
    """Файла модели нет или движок его не загрузил — беда на каждый текст."""


def _open_model(path: str):
    """Загрузить модель движком.

    Импорт здесь, а не вверху: движок тянет свою библиотеку при импорте, а
    нужен он только тем, кто выбрал файл модели.
    """
    from llama_cpp import Llama

    # Пачка не меньше окна: движок режет текст до размера пачки молча, и
    # при пачке по умолчанию вектор считался бы по первым 512 токенам.
    return Llama(
        model_path=path,
        embedding=True,
        n_ctx=CONTEXT_TOKENS,
        n_batch=CONTEXT_TOKENS,
        n_ubatch=CONTEXT_TOKENS,
        verbose=False,
    )


class ModelFile:
    """Файл модели на диске и загруженная из него модель.

    Загружается при первом тексте: модель весит сотни мегабайт, и держать её,
    пока бот стоит, незачем. Обращения идут по одному под замком: движок не
    рассчитан на одновременные вызовы, а обход канала и прогон заново
    просят вектор независимо друг от друга.
    """

    def __init__(self, path: str) -> None:
        self.path = path
        self._model = None
        self._lock = threading.Lock()

    async def embed(self, text: str) -> list[float]:
        """Вектор текста; счёт в отдельном потоке, петлю бота он не держит."""
        return await asyncio.to_thread(self._embed_now, text)

    def _embed_now(self, text: str) -> list[float]:
        with self._lock:
            if self._model is None:
                self._model = self._load()
            vector = self._model.embed(text)
        # Модель без эмбеддингов — чат-модель в том же формате — отдаёт вектор
        # на каждый токен. Это беда файла, а не текста: так ответит каждый.
        if vector and isinstance(vector[0], list):
            raise ModelUnavailable(f"в файле не модель эмбеддингов: {self.path}")
        return vector

    def _load(self):
        if not os.path.isfile(self.path):
            raise ModelUnavailable(f"файла модели нет: {self.path}")
        try:
            return _open_model(self.path)
        except _LOAD_TROUBLES as e:
            raise ModelUnavailable(f"модель не загрузилась: {self.path}") from e

    def listed(self) -> list[str]:
        """Файл как «перечень моделей»: он сам, пока лежит на диске."""
        return [self.path] if os.path.isfile(self.path) else []

    async def check(self, text: str) -> tuple[bool, str]:
        """Проверка связи: загрузить модель и посчитать вектор пробного текста."""
        try:
            await self.embed(text)
        except ModelUnavailable as e:
            _log.exception("файл модели не прошёл проверку")
            return False, str(e)
        except Exception as e:
            # Сбой движка на пробном тексте: окно ждёт ответа с родом
            # проверки, и брошенное отсюда пришло бы к нему без рода.
            _log.exception("файл модели не посчитал пробный вектор")
            return False, f"{type(e).__name__}: {e}"
        return True, os.path.basename(self.path)

    async def aclose(self) -> None:
        """Выгрузить модель; следующий текст загрузит её заново."""
        await asyncio.to_thread(self._release)

    def _release(self) -> None:
        with self._lock:
            model, self._model = self._model, None
        if model is not None:
            model.close()
