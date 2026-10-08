# План: Claude для чата и эмбеддинги из файла модели

> **Исполнителю:** задачи идут слайсами по скиллу `free-hands:keeping-code-clean`:
> тест до кода и виден красным → код → зелёное → пересборка карт → ревью агентами
> (`superpowers:requesting-code-review`) → правки → коммит (`git add . && git commit`).
> Шаги отмечаются `- [ ]`. Мутаций нет ни между слайсами, ни в итоговом ревью.

**Цель:** чат идёт через Claude по официальному SDK Anthropic, эмбеддинги — из GGUF-файла
внутри приложения. Нынешний путь через OpenAI-совместимый сервер не меняется.

**Устройство:**
- Два новых модуля в `adapters/`: `claude.py` (SDK-клиент и разговор с Claude) и
  `gguf_embed.py` (файл модели и счёт векторов).
- Нынешние точки входа выбирают их по типу клиента одной строкой в начале функции:
  `lm_studio.make_client`, `lm_chat.chat`, `lm_models.list_models`, `lm_models.check_model`,
  `lm_embed.embed`. Тела нынешних функций ниже этой строки не меняются.
- Признаки поставщика:
  - Claude — хост адреса `api.anthropic.com`;
  - файл модели — пустой адрес и путь `*.gguf` в поле модели.

**Стек:** `anthropic==1.12.1` (ходит через `httpx2`, а не `httpx`); `llama-cpp-python` 0.3.19,
готовое колесо под процессор для cp313 win_amd64; pytest и pytest-asyncio; Svelte 5 и Vitest.

**Спека:** `docs/Спека — Claude и эмбеддинги из файла.md`

## Состояние

- Задачи 1, 1б, 3 сделаны и прошли полное ревью; код ушёл от плана там, где ревью нашло
  беды, — интерфейсы ниже записаны на момент плана, правда в коде.
- Задача 2: замер сделан через Claude Code, выбран `EFFORT = "high"`; предел заменён
  запасом `THINKING_ROOM`, прибавляемым к пределу обращения.
- Задача 4: векторы совпали с записанными (косинус ≥ 0.9997), чужие GGUF отбиваются;
  живой прогон бота ждёт переключения чата в окне.
- Отказ модели отвечать отдаёт вакансию человеку, как обрыв ответа (`REFUSED_SKIP_REASON`).
- `JobBot.spec` поправлен под движок и SDK; сама сборка — по команде человека.
- Признаки поставщиков — `backend/provider_config.py`: `serves_claude`, `serves_claude_code`,
  `names_model_file`, `provider_complete`. Эмбеддинги на адресе Claude бэкенд не принимает.

**Задаче 5 от бэкенда:**
- пресеты Anthropic (`https://api.anthropic.com`) и Claude Code (служебный адрес `claude-code`,
  без ключа); проверка формы не должна требовать URL и ключ у Claude Code;
- галочка «как у чата» недоступна и для Anthropic, и для Claude Code;
- у Anthropic без ключа перечень моделей отвечает отказом — не спрашивать его, пока ключ пуст;
- файл модели: `settings.pick_model_file`, затем `settings.save` с пустым адресом.

## Общие ограничения

- Путь OpenAI и LM Studio не меняет поведения. Существующие тесты `tests/adapters/test_lm_*.py`
  зеленеют без правок.
- Промпты и константы пределов в `backend/llm/*` не трогаются.
- Схема базы не меняется, миграций нет.
- Боевые зависимости в Pipfile закрепляются точными версиями, как остальные.
- Тесты не дотягиваются до настоящего API Anthropic и не грузят настоящую модель.
- Питоновские тесты гоняются через `pipenv run pytest`, фронтовые — `npm test` в `client/web`.
- Тексты окна — на «вы», без жаргона.
- Вид окна утверждает человек: экран показывается ему до ревью и коммита.

## На что смотреть в ревью

1. **Пустой ключ Anthropic.** SDK подставляет ключ из `ANTHROPIC_API_KEY`, только если ключ не
   передан вовсе. Пустая строка — явный ключ, запрос получит 401, а не уйдёт с чужим ключом из
   окружения. Тест в задаче 1.
2. **Чат переключили на Anthropic, а эмбеддинги стояли «как у чата».** Эмбеддинги не должны
   переехать на адрес Anthropic. Задача 5: галочка скрыта, адрес не зеркалится.
3. **Файл модели удалили или перенесли после настройки.** Обход канала останавливается, а не
   теряет посты. Лампочка EMB гаснет. Тесты в задаче 3.
4. **Модель грузится и одновременно считает.** Обход и прогон заново могут попросить вектор в
   один миг. Обращения идут по одному, модель грузится один раз. Тест в задаче 3.
5. **Выбран не тот файл.** Выбран `.gguf` чат-модели, а не эмбеддингов. Проверка связи должна
   показать ошибку, а не повесить приложение. Ручная проверка в задаче 4: настоящую модель
   тесты не грузят.

---

### Задача 1. Адаптер Claude

**Файлы:**
- Создать: `adapters/claude.py`, `tests/fakes/claude.py`, `tests/adapters/test_claude.py`.
- Изменить: `adapters/lm_studio.py` (`make_client`), `adapters/lm_chat.py` (`chat`),
  `adapters/lm_models.py` (`list_models`, `check_model`), `tests/conftest.py` (запор),
  `tests/test_harness_safety.py`, `Pipfile`, `Pipfile.lock`.

**Интерфейсы:**
- `adapters.claude.ClaudeClient(anthropic.AsyncAnthropic)`, метод `aclose()`.
- `adapters.claude.serves(base_url: str) -> bool`.
- `adapters.claude.make_client(config: LlmProviderConfig, *, timeout: float) -> ClaudeClient`.
- `adapters.claude.ask(client, model, request, log) -> tuple[str | None, str | None, str | None]`
  — текст, признак окончания в словаре OpenAI, ошибка.
- `adapters.claude.list_models(client, kind: str | None) -> list[str]`.
- `adapters.claude.check_model(client, model, kind) -> tuple[bool, str]`.
- Константы `EFFORT` и `MIN_MAX_TOKENS` уточняет задача 2.

- [ ] **Шаг 1. Зависимость.**
  ```
  pipenv install anthropic==1.12.1
  ```
  Проверить, что в `[packages]` встало `anthropic = "==1.12.1"` и что версии прочих пакетов в
  `Pipfile.lock` не уехали (`git diff Pipfile.lock` — только добавления).

- [ ] **Шаг 2. Запор сети для SDK — тест красным.** Дописать в `tests/test_harness_safety.py`:
  ```python
  async def test_a_call_into_real_anthropic_blows_up():
      """Обращение к настоящему API Anthropic из теста взрывается.

      SDK ходит своим клиентом `httpx2`, мимо подделок `tests/fakes/llm.py`, и
      без запора тест с забытой подделкой ушёл бы к настоящей модели — за
      деньги, по ключу из окружения.
      """
      client = ClaudeClient(api_key="sk-test", max_retries=0)

      with pytest.raises(ProviderReached):
          await client.messages.create(
              model="claude-sonnet-5-5",
              max_tokens=1,
              messages=[{"role": "user", "content": "ping"}],
          )
  ```
  Импорты: `from adapters.claude import ClaudeClient`, `from tests.conftest import ProviderReached`.
  Прогон: `pipenv run pytest tests/test_harness_safety.py -q`. Ожидается падение при импорте:
  модуля `adapters.claude` и `ProviderReached` ещё нет.

- [ ] **Шаг 3. Запор в `tests/conftest.py`**, рядом с `TelegramReached`:
  ```python
  class ProviderReached(BaseException):
      """Тест дотянулся до настоящего API Anthropic.

      Наследник `BaseException` по той же причине, что у `TelegramReached`:
      боевой адаптер ловит ошибки SDK, и наследника `Exception` проглотил бы.
      """


  @pytest.fixture(autouse=True)
  def _anthropic_is_unreachable(monkeypatch):
      """Настоящий транспорт `httpx2` заперт; подделки ходят через `MockTransport`."""

      async def _refuse(*_args, **_kwargs):
          raise ProviderReached(
              "тест дотянулся до настоящего API Anthropic. Передайте в проверяемый "
              "код подделку из tests/fakes/claude.py."
          )

      monkeypatch.setattr(httpx2.AsyncHTTPTransport, "handle_async_request", _refuse)
  ```
  `import httpx2` — вверху файла, рядом с прочими импортами.

- [ ] **Шаг 4. Подделка `tests/fakes/claude.py`.**
  ```python
  """Подделка API Anthropic: настоящий клиент SDK поверх подставного транспорта.

  Устроена как `tests/fakes/llm.provider`, и правила у неё те же: незаданный
  путь отвечает 599 со своим именем, исключение бросается, список отвечает по
  очереди. Отдельной подделкой, а не той же: SDK ходит через `httpx2`, и
  транспорт с ответами у него свои.
  """

  import httpx2
  from anthropic import DefaultAsyncHttpxClient

  from adapters.claude import ClaudeClient
  from tests.fakes.llm import _picker

  MESSAGES = ("POST", "/v1/messages")
  MODELS = ("GET", "/v1/models")


  def claude(routes: dict, *, api_key: str = "sk-test") -> ClaudeClient:
      """Клиент к поддельному Anthropic; ушедшие запросы копятся в `client.sent`."""
      sent: list[httpx2.Request] = []
      pick = _picker(routes)

      def handle(request: httpx2.Request) -> httpx2.Response:
          sent.append(request)
          key = (request.method, request.url.path)
          prepared = pick(key)
          if prepared is None:
              return httpx2.Response(599, text=f"тест не задал ответ для {key[0]} {key[1]}")
          if isinstance(prepared, BaseException):
              if isinstance(prepared, httpx2.RequestError):
                  prepared.request = request
              raise prepared
          return prepared

      client = ClaudeClient(
          api_key=api_key,
          base_url="https://api.anthropic.com",
          max_retries=0,
          http_client=DefaultAsyncHttpxClient(transport=httpx2.MockTransport(handle)),
      )
      client.sent = sent
      return client


  def message(text: str, *, stop_reason: str = "end_turn") -> httpx2.Response:
      """Ответ модели: блок размышления и блок текста, как отвечает Sonnet."""
      return httpx2.Response(200, json={
          "id": "msg_test", "type": "message", "role": "assistant",
          "model": "claude-sonnet-5-5",
          "content": [
              {"type": "thinking", "thinking": "", "signature": "sig"},
              {"type": "text", "text": text},
          ],
          "stop_reason": stop_reason, "stop_sequence": None,
          "usage": {"input_tokens": 1, "output_tokens": 1},
      })


  def refusal(category: str = "cyber") -> httpx2.Response:
      """Отказ модели отвечать: код 200, причина в `stop_details`."""
      return httpx2.Response(200, json={
          "id": "msg_test", "type": "message", "role": "assistant",
          "model": "claude-sonnet-5-5", "content": [],
          "stop_reason": "refusal", "stop_sequence": None,
          "stop_details": {"type": "refusal", "category": category, "explanation": "нет"},
          "usage": {"input_tokens": 1, "output_tokens": 0},
      })


  def model_list(*ids: str) -> httpx2.Response:
      """Ответ `/v1/models` в форме Anthropic."""
      return httpx2.Response(200, json={
          "data": [
              {"type": "model", "id": one, "display_name": one,
               "created_at": "2026-01-01T00:00:00Z"}
              for one in ids
          ],
          "has_more": False,
          "first_id": ids[0] if ids else None,
          "last_id": ids[-1] if ids else None,
      })
  ```

- [ ] **Шаг 5. Тесты адаптера — красным.** `tests/adapters/test_claude.py`. Проверки идут через
  нынешние точки входа (`lm_chat.chat`, `lm_models.*`, `lm_studio.make_client`): зовущие видят
  только их.
  ```python
  """Следствия разговора с Claude через нынешние точки входа адаптеров."""

  import json
  import logging

  import httpx2
  import pytest

  from adapters import lm_models
  from adapters.claude import ClaudeClient
  from adapters.lm_chat import ChatRequest, chat
  from adapters.lm_studio import make_client
  from backend.runtime_settings import LlmProviderConfig
  from tests.fakes.claude import MESSAGES, MODELS, claude, message, model_list, refusal

  LOG = logging.getLogger("tests.claude")


  def _request(**over) -> ChatRequest:
      fields = {
          "purpose": "разбор вакансии",
          "messages": [
              {"role": "system", "content": "правила"},
              {"role": "user", "content": "текст"},
          ],
          "max_tokens": 1200,
      }
      fields.update(over)
      return ChatRequest(**fields)


  def _body(client) -> dict:
      return json.loads(client.sent[-1].content)


  def test_an_anthropic_address_gets_the_claude_client_with_its_key():
      client = make_client(LlmProviderConfig("https://api.anthropic.com", "sk-1", "claude-sonnet-5-5"))
      assert isinstance(client, ClaudeClient)
      assert client.api_key == "sk-1"


  def test_an_empty_key_stays_empty_instead_of_the_environment_one(monkeypatch):
      monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-из-окружения")
      client = make_client(LlmProviderConfig("https://api.anthropic.com", "", "claude-sonnet-5-5"))
      assert client.api_key == ""


  async def test_the_system_prompt_travels_apart_from_the_turns():
      client = claude({MESSAGES: message("ок")})
      await chat(client, "claude-sonnet-5-5", _request(), LOG)
      body = _body(client)
      assert body["system"] == "правила"
      assert body["messages"] == [{"role": "user", "content": "текст"}]


  async def test_no_temperature_is_sent_and_thinking_has_room():
      client = claude({MESSAGES: message("ок")})
      await chat(client, "claude-sonnet-5-5", _request(temperature=0.5), LOG)
      body = _body(client)
      assert "temperature" not in body
      assert body["thinking"] == {"type": "adaptive"}
      assert body["max_tokens"] > 1200


  async def test_the_answer_is_the_text_without_the_thinking():
      client = claude({MESSAGES: message("готово")})
      answer = await chat(client, "claude-sonnet-5-5", _request(), LOG)
      assert (answer.text, answer.error) == ("готово", None)


  async def test_an_answer_cut_by_the_limit_reads_as_length_and_names_itself(caplog):
      client = claude({MESSAGES: message('{"a":', stop_reason="max_tokens")})
      with caplog.at_level(logging.WARNING, logger="tests.claude"):
          answer = await chat(client, "claude-sonnet-5-5", _request(), LOG)
      assert answer.finish_reason == "length"
      assert "разбор вакансии: модель упёрлась в предел токенов" in caplog.text


  async def test_a_refusal_is_an_error_with_its_category_in_the_log(caplog):
      client = claude({MESSAGES: refusal("cyber")})
      with caplog.at_level(logging.WARNING, logger="tests.claude"):
          answer = await chat(client, "claude-sonnet-5-5", _request(), LOG)
      assert answer.text is None and answer.error == "refusal"
      assert "cyber" in caplog.text


  @pytest.mark.parametrize(
      ("prepared", "error"),
      [
          pytest.param(
              httpx2.Response(500, json={"type": "error", "error": {"type": "api_error", "message": "x"}}),
              "llm_http_error: 500", id="отказ кодом",
          ),
          pytest.param(httpx2.ConnectError("сеть"), "llm_request_error: APIConnectionError", id="обрыв"),
      ],
  )
  async def test_provider_troubles_carry_the_same_marks_as_the_openai_path(prepared, error):
      client = claude({MESSAGES: prepared})
      answer = await chat(client, "claude-sonnet-5-5", _request(), LOG)
      assert answer.error == error


  async def test_a_request_with_its_own_deadline_carries_it():
      client = claude({MESSAGES: message("ок")})
      await chat(client, "claude-sonnet-5-5", _request(timeout=300.0), LOG)
      assert client.sent[-1].extensions["timeout"]["read"] == 300.0


  async def test_chat_models_come_from_the_key_and_embeddings_are_none():
      client = claude({MODELS: model_list("claude-sonnet-5-5")})
      assert await lm_models.list_models(client, kind="chat") == ["claude-sonnet-5-5"]
      assert await lm_models.list_models(client, kind="embed") == []


  async def test_a_listed_model_that_answers_passes_the_check():
      client = claude({MODELS: model_list("claude-sonnet-5-5"), MESSAGES: message("pong")})
      assert await lm_models.check_model(client, "claude-sonnet-5-5", "chat") == (True, "claude-sonnet-5-5")


  async def test_an_unlisted_model_fails_the_check_by_name():
      client = claude({MODELS: model_list("claude-haiku-5-5")})
      ok, detail = await lm_models.check_model(client, "claude-sonnet-5-5", "chat")
      assert not ok and "claude-sonnet-5-5" in detail


  async def test_an_embedding_check_against_anthropic_says_why():
      client = claude({})
      ok, detail = await lm_models.check_model(client, "что-угодно", "embed")
      assert not ok and "эмбеддинг" in detail


  async def test_closing_the_client_closes_its_connection():
      client = claude({})
      await client.aclose()
      assert client.is_closed()
  ```
  Прогон: `pipenv run pytest tests/adapters/test_claude.py -q`. Ожидается падение при импорте:
  `adapters.claude` нет.

- [ ] **Шаг 6. `adapters/claude.py`.**
  ```python
  """Разговор с Claude через официальный SDK Anthropic.

  Надстройка рядом с OpenAI-совместимым путём: нынешние точки входа
  (`lm_studio`, `lm_chat`, `lm_models`) узнают этот клиент по типу и отдают
  его сюда. Всё, чем Claude отличается, остаётся здесь: системный промпт
  отдельным параметром, отсутствие temperature, блоки в ответе, отказ модели.
  """

  import logging
  from urllib.parse import urlsplit

  import anthropic

  from backend.runtime_settings import LlmProviderConfig

  _log = logging.getLogger(__name__)

  CLAUDE_HOST = "api.anthropic.com"

  # Размышление расходует тот же предел, что и ответ. Пределы в `backend/llm`
  # подобраны под локальную модель без размышления, и Claude обрывался бы на
  # них, не дойдя до ответа. Величина и уровень — по замеру (задача 2 плана).
  MIN_MAX_TOKENS = 16000
  EFFORT = "medium"

  # Признак окончания в словаре OpenAI: по нему зовущие решают про обрыв.
  _FINISH = {"max_tokens": "length", "end_turn": "stop"}


  class ClaudeClient(anthropic.AsyncAnthropic):
      """Клиент SDK, который закрывается так же, как httpx-клиент соседей."""

      async def aclose(self) -> None:
          await self.close()


  def serves(base_url: str) -> bool:
      """Ведёт ли адрес к Anthropic."""
      return urlsplit(base_url).hostname == CLAUDE_HOST


  def make_client(config: LlmProviderConfig, *, timeout: float) -> ClaudeClient:
      """Клиент Anthropic по настройкам поставщика.

      Ключ передаётся всегда, даже пустой: без него SDK взял бы ключ из
      окружения, и приложение ходило бы к модели по чужому ключу.
      """
      return ClaudeClient(api_key=config.api_key, base_url=config.base_url, timeout=timeout)


  def _params(model: str, request) -> dict:
      """Тело запроса: системные сообщения — в `system`, остальные — в `messages`."""
      system = "\n\n".join(m["content"] for m in request.messages if m["role"] == "system")
      params = {
          "model": model,
          "max_tokens": max(request.max_tokens, MIN_MAX_TOKENS),
          "messages": [m for m in request.messages if m["role"] != "system"],
          "thinking": {"type": "adaptive"},
          "output_config": {"effort": EFFORT},
      }
      if system:
          params["system"] = system
      return params


  async def ask(client: ClaudeClient, model: str, request, log: logging.Logger):
      """Спросить модель: текст, признак окончания и ошибка — одно из двух пусто.

      Ошибки называются теми же метками, что у OpenAI-пути (`lm_chat._post_chat`):
      по ним зовущие выбирают откат, и второй словарь меток развёл бы их.
      """
      target = client if request.timeout is None else client.with_options(timeout=request.timeout)
      try:
          reply = await target.messages.create(**_params(model, request))
      except anthropic.APIStatusError as e:
          log.warning("%s: провайдер ответил HTTP %s", request.purpose, e.status_code)
          return None, None, f"llm_http_error: {e.status_code}"
      except anthropic.APIConnectionError as e:
          log.warning("%s: запрос не дошёл: %s: %s", request.purpose, type(e).__name__, e)
          return None, None, f"llm_request_error: {type(e).__name__}"
      if reply.stop_reason == "refusal":
          category = reply.stop_details.category if reply.stop_details else None
          log.warning("%s: модель отказалась отвечать (%s)", request.purpose, category)
          return None, None, "refusal"
      text = "".join(block.text for block in reply.content if block.type == "text")
      return text, _FINISH.get(reply.stop_reason, reply.stop_reason), None


  async def list_models(client: ClaudeClient, kind: str | None = None) -> list[str]:
      """Модели, доступные ключу. Эмбеддингов у Anthropic нет — для них пусто."""
      if kind == "embed":
          return []
      return [one.id async for one in client.models.list()]


  async def check_model(client: ClaudeClient, model: str, kind: str) -> tuple[bool, str]:
      """Есть ли модель у ключа и отвечает ли она — для кнопки проверки связи."""
      if kind == "embed":
          return False, "У Anthropic нет моделей эмбеддингов"
      try:
          models = await list_models(client)
      except anthropic.APIError as e:
          _log.exception("Anthropic не отдал список моделей")
          return False, f"{type(e).__name__}: {e}"
      if model not in models:
          return False, f"{model!r} not available (have: {', '.join(models[:3]) or 'no models'})"
      try:
          await client.messages.create(
              model=model, max_tokens=16, messages=[{"role": "user", "content": "ping"}]
          )
      except anthropic.APIError as e:
          _log.exception("пробный запрос к модели %s не прошёл", model)
          return False, f"{model} (ping failed: {type(e).__name__})"
      return True, model
  ```

- [ ] **Шаг 7. Развилки в точках входа.**
  - `adapters/lm_studio.py`: `from adapters import claude`. Первые строки `make_client`:
    ```python
        if claude.serves(config.base_url):
            return claude.make_client(config, timeout=LLM_REQUEST_TIMEOUT_SEC)
    ```
  - `adapters/lm_chat.py`: `from adapters import claude`. Первая строка `chat`:
    ```python
        if isinstance(client, claude.ClaudeClient):
            return await _chat_with_claude(client, model, request, log)
    ```
    И рядом новая функция:
    ```python
    async def _chat_with_claude(client, model: str, request: ChatRequest, log) -> ChatAnswer:
        """Разговор с Claude, сведённый к тому же ответу, что у OpenAI-пути.

        Жалоба на обрыв и проверка на пустоту — общие: беды у ответа те же, и
        вторые их копии разошлись бы с первыми.
        """
        content, finish_reason, error = await claude.ask(client, model, request, log)
        if error is not None:
            return ChatAnswer(error=error)
        _warn_if_truncated(finish_reason, request.purpose, log)
        return _answer_or_empty(content, finish_reason, request.purpose, log)
    ```
  - `adapters/lm_models.py`: `from adapters import claude`. Первые строки `list_models`:
    ```python
        if isinstance(client, claude.ClaudeClient):
            return await claude.list_models(client, kind)
    ```
    Первые строки `check_model`:
    ```python
        if isinstance(client, claude.ClaudeClient):
            return await claude.check_model(client, model, kind)
    ```
  - Докстроки модулей `lm_studio`, `lm_chat`, `lm_models` говорят «провайдер любой
    OpenAI-совместимый». Дописать одной фразой, что клиент Anthropic уходит в `adapters/claude`.

- [ ] **Шаг 8. Зелёное.** `pipenv run pytest tests/adapters tests/test_harness_safety.py -q` — всё
  зелёное, включая нетронутые `test_lm_*.py`. Затем полный набор `pipenv run pytest -q`:
  `lm_client` используют `bot`, `health` и мост.

- [ ] **Шаг 9. Карты.**
  ```
  pipenv run python "C:/Users/deade/.claude/skills/free-hands/skills/keeping-code-clean/tools/module_map.py"
  ```

- [ ] **Шаг 10. Ревью** — три агента по `superpowers:requesting-code-review` (дубликаты, манифест,
  ошибки) и тестовый агент, раз слайс писал тесты. Правки по находкам.

- [ ] **Шаг 11. Коммит.** `git add . && git commit`, сообщение — что стало возможно:
  «чат умеет ходить к Claude через SDK Anthropic; путь LM Studio и OpenAI не тронут».

---

### Задача 1б. Claude Code по подписке

Добавлена после того, как выяснилось, что API оплачивается отдельно от подписки. Спека — часть 1б.

**Файлы:**
- Создать: `adapters/claude_code.py`, `tests/fakes/claude_code.py`, `tests/adapters/test_claude_code.py`.
- Изменить:
  - `adapters/lm_studio.py`, `adapters/lm_chat.py`, `adapters/lm_models.py` — развилки;
  - `adapters/claude.py` — признак конца становится общим;
  - `tests/conftest.py` — запор запуска процесса;
  - `tests/test_harness_safety.py`.

**Интерфейсы:**
- `adapters.claude_code.serves(base_url) -> bool` — адрес `claude-code`.
- `adapters.claude_code.ClaudeCodeClient(timeout: float)` с `aclose()`.
- `adapters.claude_code.make_client(config, *, timeout) -> ClaudeCodeClient`.
- `adapters.claude_code.ask(client, model, request, log) -> (text, finish_reason)`; беды — `CliTrouble(label)`.
- `adapters.claude_code.list_models(client, kind) -> list[str]`, `ping(client, model) -> (bool, str)`.
- `adapters.claude_code._run_cli(argv, stdin, env, timeout) -> (code, stdout, stderr)` — единственный
  запуск процесса; стенд его запирает.

Шаги по слайсу: тесты красным → код → зелёное → карты → ревью → коммит.

### Задача 2. Замер уровня размышления

Делается через Claude Code по подписке: стоит не денег, а части лимита Max — порядка
десятка вакансий × восемь запросов × три уровня. Скрипт живёт в каталоге
scratchpad, в репозиторий не попадает.

- [ ] **Шаг 1.** Взять из базы (только чтение) 10 вакансий разных исходов (`New`, `Not Fit`,
  мусор) и их `raw_text`.
- [ ] **Шаг 2.** Скрипт в scratchpad: для каждой вакансии и каждого `effort` из `low`, `medium`,
  `high` прогнать через `adapters.claude` боевые запросы — `llm/genre`, `llm/vacancy`, три
  `llm/fit_*`, `llm/cover_letter`, `llm/factcheck`. `EFFORT` подменяется на время прогона.
  Записать время, `usage.input_tokens` и `usage.output_tokens`, итоговый вердикт.
- [ ] **Шаг 3.** Таблица вам: время и цена на вакансию по уровням, расхождения вердиктов между
  уровнями и с записанным в базе (его выносила локальная модель).
- [ ] **Шаг 4.** По вашему выбору поставить `EFFORT` и `MIN_MAX_TOKENS` в `adapters/claude.py`.
  Если окажется нужен разный уровень для разных запросов — это отдельное решение, оно трогает
  `ChatRequest`.
- [ ] **Шаг 5.** Коммит константы с выводом замера в сообщении.

---

### Задача 3. Эмбеддинги из файла модели (бэкенд и мост)

**Файлы:**
- Создать: `adapters/gguf_embed.py`, `tests/fakes/gguf.py`, `tests/adapters/test_gguf_embed.py`.
- Изменить:
  - `adapters/lm_studio.py`, `adapters/lm_embed.py`, `adapters/lm_models.py` — развилки;
  - `backend/runtime_settings.py` — признак файла модели и подъём строки без адреса;
  - `backend/flows/embeddings.py` — `_is_about_the_provider`;
  - `client/bridge/llm.py` — `read_llm_creds`, новый `pick_model_file`;
  - `Pipfile`, `Pipfile.lock`;
  - тесты: `tests/backend/test_runtime_settings_load.py`,
    `tests/backend/test_flows_embedding_text.py`, `tests/client/test_bridge_llm.py`,
    `tests/backend/test_health.py`.

**Интерфейсы:**
- `backend.runtime_settings.names_model_file(base_url: str | None, model: str | None) -> bool`.
- Свойство `LlmProviderConfig.names_model_file -> bool`.
- `adapters.gguf_embed.ModelFile(path: str)`: `async embed(text) -> list[float]`,
  `listed(kind) -> list[str]`, `async check(kind) -> tuple[bool, str]`, `async aclose()`, поле `path`.
- `adapters.gguf_embed.ModelUnavailable(Exception)`.
- `adapters.gguf_embed._open_model(path)` — единственное место, где грузится движок; тесты
  подменяют его.
- `tests.fakes.gguf.Model(journal: list)` — подделка движка; `tests.fakes.gguf.model_file(tmp_path)`
  — путь к пустышке `*.gguf` на диске.
- Мост: `settings.pick_model_file()` → `{"ok": {"path": str}}` или `{"ok": {"cancelled": True}}`.

- [ ] **Шаг 1. Зависимость.** В `[packages]` Pipfile:
  ```toml
  # Готовое колесо под процессор: на PyPI только исходники, их сборка требует компилятора C++.
  llama-cpp-python = {file = "https://github.com/abetlen/llama-cpp-python/releases/download/v0.3.19/llama_cpp_python-0.3.19-cp313-cp313-win_amd64.whl"}
  ```
  Затем `pipenv install`. Проверить `pipenv run python -c "import llama_cpp"` и что `numpy` в
  замке остался `2.4.4`.

- [ ] **Шаг 2. Подделка движка `tests/fakes/gguf.py`.**
  ```python
  """Подделка движка эмбеддингов: настоящая модель в тестах не грузится.

  Нужна двоим — тестам адаптера и тестам моста, — поэтому живёт не у кого-то одного.
  """


  class Model:
      """Модель-подделка: пишет в журнал загрузки и закрытия, вектор — длина текста."""

      def __init__(self, journal: list) -> None:
          self.journal = journal
          journal.append("загружена")

      def embed(self, text: str) -> list[float]:
          return [float(len(text)), 1.0]

      def close(self) -> None:
          self.journal.append("закрыта")


  def model_file(folder) -> str:
      """Пустышка `*.gguf` на диске: файл есть, движок его не читает."""
      path = folder / "bge-m3-q8_0.gguf"
      path.write_bytes(b"GGUF")
      return str(path)
  ```

- [ ] **Шаг 3. Тесты — красным.**

  `tests/adapters/test_gguf_embed.py`:
  ```python
  """Следствия счёта векторов из файла модели; настоящая модель не грузится."""

  import asyncio

  import pytest

  from adapters import gguf_embed, lm_embed, lm_models
  from adapters.gguf_embed import ModelFile, ModelUnavailable
  from adapters.lm_studio import make_client
  from backend.runtime_settings import LlmProviderConfig
  from tests.fakes.gguf import Model, model_file


  @pytest.fixture
  def journal(monkeypatch):
      happened: list[str] = []
      monkeypatch.setattr(gguf_embed, "_open_model", lambda _path: Model(happened))
      return happened


  def test_an_empty_address_with_a_model_file_gets_the_file_client(tmp_path):
      path = model_file(tmp_path)
      client = make_client(LlmProviderConfig("", "", path))
      assert isinstance(client, ModelFile) and client.path == path


  async def test_the_model_is_loaded_once_for_many_texts(journal, tmp_path):
      path = model_file(tmp_path)
      client = ModelFile(path)
      assert await lm_embed.embed(client, path, "раз") == [3.0, 1.0]
      await lm_embed.embed(client, path, "два")
      assert journal == ["загружена"]


  async def test_texts_asked_at_once_share_one_load(journal, tmp_path):
      client = ModelFile(model_file(tmp_path))
      await asyncio.gather(*(client.embed(str(n)) for n in range(5)))
      assert journal == ["загружена"]


  async def test_a_missing_file_is_the_whole_model_unavailable(journal, tmp_path):
      client = ModelFile(str(tmp_path / "нет.gguf"))
      with pytest.raises(ModelUnavailable):
          await client.embed("текст")
      assert journal == []


  async def test_a_file_the_engine_cannot_load_is_unavailable_too(monkeypatch, tmp_path):
      def broken(_path):
          raise ValueError("Failed to load model from file")

      monkeypatch.setattr(gguf_embed, "_open_model", broken)
      with pytest.raises(ModelUnavailable):
          await ModelFile(model_file(tmp_path)).embed("текст")


  async def test_closing_frees_the_model_and_the_next_text_loads_it_again(journal, tmp_path):
      client = ModelFile(model_file(tmp_path))
      await client.embed("раз")
      await client.aclose()
      await client.embed("два")
      assert journal == ["загружена", "закрыта", "загружена"]


  async def test_the_file_is_listed_only_while_it_is_on_disk(tmp_path):
      path = model_file(tmp_path)
      assert await lm_models.model_listed(ModelFile(path), path) == (True, [path])
      gone = str(tmp_path / "нет.gguf")
      assert (await lm_models.model_listed(ModelFile(gone), gone))[0] is False


  async def test_a_check_loads_the_model_and_names_the_file(journal, tmp_path):
      path = model_file(tmp_path)
      ok, detail = await lm_models.check_model(ModelFile(path), path, "embed")
      assert ok and detail == "bge-m3-q8_0.gguf"
      assert journal == ["загружена"]


  async def test_a_check_of_a_missing_file_says_so(tmp_path):
      gone = str(tmp_path / "нет.gguf")
      ok, detail = await lm_models.check_model(ModelFile(gone), gone, "embed")
      assert not ok and "нет" in detail
  ```

  В `tests/backend/test_runtime_settings_load.py`:
  ```python
  async def test_a_model_file_without_an_address_is_a_provider(session_factory):
      """Эмбеддинги из файла: адреса нет, в модели путь к `.gguf`."""
      await put(session_factory, llm_config_row(
          LlmConfigKind.EMBED, base_url=None, model=r"d:\Models\bge-m3-q8_0.gguf",
      ))
      embed = (await RuntimeSettings.load(session_factory)).embed
      assert (embed.base_url, embed.model) == ("", r"d:\Models\bge-m3-q8_0.gguf")
  ```
  Существующий `test_a_provider_without_an_address_is_not_a_provider` (модель `qwen`)
  остаётся и зеленеет.

  В `tests/backend/test_flows_embedding_text.py`:
  ```python
  async def test_a_model_file_that_will_not_load_silences_the_provider(monkeypatch, tmp_path):
      """Незагружаемый файл модели — молчание поставщика, а не беда одного текста.

      Пропусти приём его как беду текста — курсор канала уехал бы мимо постов,
      которые не посчитаются, пока файл не вернут на место.
      """
      def broken(_path):
          raise ValueError("Failed to load model from file")

      monkeypatch.setattr(gguf_embed, "_open_model", broken)
      pipeline = _Pipeline(ModelFile(model_file(tmp_path)))

      with pytest.raises(embeddings.ProviderIsSilent):
          await embeddings.embed_text(pipeline, "текст", "vacancy 7")
  ```
  Импорты: `from adapters import gguf_embed`, `from adapters.gguf_embed import ModelFile`,
  `from tests.fakes.gguf import model_file`.

  В `tests/client/test_bridge_llm.py`:
  ```python
  async def test_a_model_file_check_needs_no_address(api, ask, monkeypatch, tmp_path):
      path = model_file(tmp_path)
      monkeypatch.setattr(gguf_embed, "_open_model", lambda _p: Model([]))
      answer = await ask(api.settings.probe_model, {"kind": "embed", "base_url": "", "model": path})
      assert answer["ok"]["model"] == path


  async def test_a_model_file_is_saved_and_read_back(api, ask, tmp_path):
      path = model_file(tmp_path)
      await ask(api.settings.save, {"embed": {"base_url": "", "api_key": "", "model": path}})
      assert (await ask(api.settings.get))["ok"]["embed"]["model"] == path


  async def test_picking_a_model_file_names_the_path_without_saving(api, ask, hub, tmp_path):
      chosen = str(tmp_path / "m.gguf")
      hub.window = WindowThatPicks([chosen])
      answer = await ask(api.settings.pick_model_file)
      assert answer["ok"]["path"] == chosen
      assert (await ask(api.settings.get))["ok"]["embed"]["model"] != chosen


  async def test_a_closed_model_dialog_changes_nothing(api, ask, hub):
      hub.window = WindowThatPicks(None)
      assert (await ask(api.settings.pick_model_file))["ok"]["cancelled"] is True
  ```
  `WindowThatPicks` — из `tests/client/conftest.py`.

  В `tests/backend/test_health.py` — лампа EMB по файлу:
  ```python
  async def test_a_model_file_lamp_follows_the_file_on_disk(tmp_path):
      path = model_file(tmp_path)
      assert await model_alive(LlmProviderConfig("", "", path), "embed") is True
      os.remove(path)
      assert await model_alive(LlmProviderConfig("", "", path), "embed") is False
  ```

  Прогон всех файлов шага — красные: нет модуля, нет метода, строка без адреса не читается.

- [ ] **Шаг 4. Признак файла модели** в `backend/runtime_settings.py`, рядом с `LlmProviderConfig`:
  ```python
  MODEL_FILE_SUFFIX = ".gguf"


  def names_model_file(base_url: str | None, model: str | None) -> bool:
      """Строка поставщика указывает не на сервер, а на файл модели на диске.

      Адреса у такой строки нет, а в поле модели — путь к GGUF. Признак один на
      троих — подъём из базы, мост и выбор клиента: разъедься он, строка,
      принятая окном, не поднималась бы ботом.
      """
      return not base_url and bool(model) and model.lower().endswith(MODEL_FILE_SUFFIX)
  ```
  Свойство в `LlmProviderConfig`:
  ```python
      @property
      def names_model_file(self) -> bool:
          return names_model_file(self.base_url, self.model)
  ```
  В `_from_llm_row` заменить `if not row.base_url or not row.model:` на
  ```python
      if not row.model or not (row.base_url or names_model_file(row.base_url, row.model)):
  ```
  и `base_url=row.base_url` на `base_url=row.base_url or ""`.

- [ ] **Шаг 5. `adapters/gguf_embed.py`.**
  ```python
  """Эмбеддинги из GGUF-файла модели, посчитанные в своём процессе без сервера."""

  import asyncio
  import logging
  import os
  import threading

  _log = logging.getLogger(__name__)

  # Окно контекста bge-m3. Текст режется до 6000 знаков (`flows/embeddings`),
  # с дописанной статьёй это две-три тысячи токенов — запас двойной.
  CONTEXT_TOKENS = 8192


  class ModelUnavailable(Exception):
      """Файла модели нет или движок его не загрузил — беда на каждый текст."""


  def _open_model(path: str):
      """Загрузить модель движком.

      Импорт здесь, а не вверху: движок тянет свою библиотеку при импорте, а
      нужен он только тем, кто выбрал файл модели.
      """
      from llama_cpp import Llama

      return Llama(model_path=path, embedding=True, n_ctx=CONTEXT_TOKENS, verbose=False)


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
              return self._model.embed(text)

      def _load(self):
          if not os.path.isfile(self.path):
              raise ModelUnavailable(f"файла модели нет: {self.path}")
          try:
              return _open_model(self.path)
          except ValueError as e:
              raise ModelUnavailable(f"модель не загрузилась: {self.path}") from e

      def listed(self, kind: str | None) -> list[str]:
          """Файл как «перечень моделей»: он сам, пока лежит на диске."""
          if kind == "chat" or not os.path.isfile(self.path):
              return []
          return [self.path]

      async def check(self, kind: str) -> tuple[bool, str]:
          """Проверка связи: загрузить модель и посчитать пробный вектор."""
          if kind != "embed":
              return False, "Файл модели годится только для эмбеддингов"
          try:
              await self.embed("ping")
          except ModelUnavailable as e:
              _log.exception("файл модели не прошёл проверку")
              return False, str(e)
          return True, os.path.basename(self.path)

      async def aclose(self) -> None:
          """Выгрузить модель; следующий текст загрузит её заново."""
          await asyncio.to_thread(self._release)

      def _release(self) -> None:
          with self._lock:
              model, self._model = self._model, None
          if model is not None:
              model.close()
  ```

- [ ] **Шаг 6. Развилки.**
  - `adapters/lm_studio.make_client`, после развилки Claude:
    ```python
        if config.names_model_file:
            return gguf_embed.ModelFile(config.model)
    ```
  - `adapters/lm_embed.embed`, первые строки:
    ```python
        if isinstance(client, gguf_embed.ModelFile):
            return await client.embed(text)
    ```
  - `adapters/lm_models.list_models` и `check_model`, после развилки Claude:
    ```python
        if isinstance(client, gguf_embed.ModelFile):
            return client.listed(kind)
    ```
    ```python
        if isinstance(client, gguf_embed.ModelFile):
            return await client.check(kind)
    ```
  - `backend/flows/embeddings._is_about_the_provider`, первые строки:
    ```python
        if isinstance(trouble, ModelUnavailable):
            return True
    ```
    Докстроку дополнить третьей бедой: «файла модели нет или он не грузится».

- [ ] **Шаг 7. Мост** `client/bridge/llm.py`.
  - В `read_llm_creds`: `if not base_url or not model:` →
    `if not model or not (base_url or names_model_file(base_url, model)):`.
  - Метод в класс `Llm`, по образцу `Cv.pick`:
    ```python
    _MODEL_FILTER = "Модель GGUF (*.gguf)"

        def pick_model_file(self) -> dict:
            """Спросить у человека файл модели эмбеддингов диалогом самого окна.

            Только называет путь, не записывает: записывает страница тем же
            `settings.save`, что и адрес сервера, — в настройках сразу, в
            мастере по «Дальше». Закрытый диалог — не отказ, а передумал.
            """
            chosen = self._hub.window.create_file_dialog(
                webview.OPEN_DIALOG, file_types=(_MODEL_FILTER,)
            )
            if not chosen:
                return {"ok": {"cancelled": True}}
            return {"ok": {"path": chosen[0]}}
    ```

- [ ] **Шаг 8. Зелёное.** Файлы шага 3 — `pipenv run pytest <файлы> -q`, затем
  `pipenv run pytest -q` целиком. `tests/client/test_page_contract.py` сверяет только зовы
  страницы с мостом, поэтому метод моста, который страница начнёт звать в задаче 5, его не роняет.

- [ ] **Шаги 9–11.** Карты (`module_map.py`), ревью (четыре агента), коммит: «эмбеддинги
  считаются из GGUF-файла внутри приложения, без LM Studio».

---

### Задача 4. Сверка векторов и живая проверка

Ручная, кода в репозитории не оставляет. База — только чтение.

- [ ] **Шаг 1.** Скрипт в scratchpad: 10 вакансий из базы с непустым `embedding`. Для каждой
  посчитать вектор `raw_text[:6000]` через `ModelFile(r"d:\Models\Embedding\bge-m3-Q8_0-GGUF\bge-m3-q8_0.gguf")`
  и сравнить косинусом с записанным.
  - У вакансий со статьёй Telegraph в базе вектор текста со статьёй: их отметить отдельно или
    взять вакансии без ссылок.
- [ ] **Шаг 2.** Итог вам. Косинус ≥ 0.99 — старые векторы в деле. Ниже — решение за вами
  (прогон заново).
- [ ] **Шаг 3.** Проверка «не тот файл»: взять в `ModelFile` GGUF чат-модели, если такой есть
  на диске, и нажать проверку. Ожидается ошибка в ответе, а не зависание. Если движок падает
  иначе — завести тест и починку в задаче 3, до коммита задачи 5.
- [ ] **Шаг 4.** С вашим ключом: приложение из исходников (`pipenv run python main.py`).
  Настройки → чат на Anthropic и Sonnet, эмбеддинги из файла. Лампочки CHT и EMB горят. Ручной
  прогон в режиме Full проходит без ошибок в журнале.

---

### Задача 5. Окно: пресет Anthropic и «Файл модели»

Слайс фронта. По памяти проекта: собрать → показать вам → правки по вашим словам, пока не
примете → ревью → коммит. Вид — черновой, его утверждаете вы.

**Файлы:**
- Изменить:
  - `client/web/state/settings.js`;
  - `client/web/state/wizard.js`;
  - `client/web/components/LlmSection.svelte`;
  - `client/web/app/SettingsScreen.svelte`;
  - `client/web/app/WizardLlm.svelte`.
- Тесты: `client/web/tests/settings.test.js`, `client/web/tests/wizard.test.js`.

**Интерфейсы (state):**
- `settings.js`:
  - `isModelFile(creds) -> bool` — пустой адрес и путь `*.gguf`, как `names_model_file` на мосту;
  - `fileCreds(path) -> {base_url: '', api_key: '', model: path}`;
  - `servesClaude(url) -> bool` — хост `api.anthropic.com`;
  - `canShareChat(chat) -> bool` — `!servesClaude(chat.base_url)`;
  - `EMBED_SOURCES = ['Сервер', 'Файл модели']`.
- `wizard.js`:
  - пресет `{ label: 'Anthropic', base_url: 'https://api.anthropic.com' }`;
  - `fileTrouble(creds) -> ''` или `'Выберите файл модели'`.

- [ ] **Шаг 1. Тесты state — красным.**
  `settings.test.js`:
  ```js
  describe('файл модели', () => {
    it('пустой адрес и путь к gguf — это файл модели', () => {
      expect(isModelFile({ base_url: '', model: 'd:\\M\\bge.GGUF' })).toBe(true);
    });
    it('адрес сервера — не файл, даже с gguf в имени', () => {
      expect(isModelFile({ base_url: 'http://localhost:1234', model: 'bge.gguf' })).toBe(false);
    });
    it('пустой черновик — не файл', () => {
      expect(isModelFile(blankCreds())).toBe(false);
    });
    it('выбранный файл ложится в поле модели без адреса и ключа', () => {
      expect(fileCreds('d:\\m.gguf')).toEqual({ base_url: '', api_key: '', model: 'd:\\m.gguf' });
    });
  });

  describe('Anthropic и общие учётные данные', () => {
    it('эмбеддинги не делят адрес с чатом на Anthropic', () => {
      expect(canShareChat({ base_url: 'https://api.anthropic.com', api_key: 'k', model: 'm' })).toBe(false);
    });
    it('с OpenAI-совместимым чатом делить можно', () => {
      expect(canShareChat({ base_url: 'https://api.openai.com/v1', api_key: 'k', model: 'm' })).toBe(true);
    });
    it('недописанный адрес не роняет проверку', () => {
      expect(canShareChat({ base_url: 'http://local', api_key: '', model: '' })).toBe(true);
    });
  });
  ```
  `wizard.test.js`:
  ```js
  it('адрес Anthropic узнаётся пресетом', () => {
    expect(presetFor('https://api.anthropic.com')).toBe('Anthropic');
  });
  it('без выбранного файла дальше не пускают', () => {
    expect(fileTrouble(blankCreds())).toBe('Выберите файл модели');
    expect(fileTrouble(fileCreds('d:\\m.gguf'))).toBe('');
  });
  ```
  Прогон: `cd client/web && npx vitest run tests/settings.test.js tests/wizard.test.js` — красное.

- [ ] **Шаг 2. State.** Функции из «Интерфейсов» с докстроками в манере файла.
  - `servesClaude` разбирает адрес через `new URL(url).hostname` в `try` (негодный адрес — `false`).
  - `fileTrouble` импортирует `isModelFile` из `./settings.js`.
  - В `PRESETS` Anthropic встаёт после OpenAI.
  - Тесты зелёные.

- [ ] **Шаг 3. `LlmSection.svelte`.** Новые свойства эмбеддингов: `fromFile`, `shareable`,
  `onsource(fromFile)`, `onpickfile()`.
  - Сверху секции эмбеддингов — `Dropdown` с `EMBED_SOURCES`; выбранное —
    `fromFile ? 'Файл модели' : 'Сервер'`.
  - В режиме файла:
    - строка пути (`creds.model` или «Файл не выбран»), стиль поля `input mono`, только чтение;
    - кнопка «Выбрать файл» (`onpickfile`);
    - кнопка «Проверить».
  - В режиме сервера — как сейчас. Галочка «как у чата» показывается только при `shareable`.
  - Новых файлов стилей не заводить, взять существующие классы. Вид дорабатывается по вашим
    замечаниям.

- [ ] **Шаг 4. `SettingsScreen.svelte`.**
  - Состояние `fromFile`, при первом чтении — `isModelFile(now.embed)`. `same` в режиме файла —
    `false`.
  - `const sharing = $derived(same && canShareChat(chat))`. В `saveChat` зеркалить эмбеддинги
    только при `sharing`.
  - `switchSource(on)`: `fromFile = on`, плашка проверки гаснет. При включении `same = false`.
    Записи нет, пока не выбран файл или не набран сервер.
  - `pickFile()`:
    ```js
    async function pickFile() {
      const got = await ask('settings.pick_model_file');
      if (!got || got.cancelled || !alive.now) return;
      embed = fileCreds(got.path);
      forgetProbe('embed');
      return save({ embed });
    }
    ```
  - В `probe(kind)` заслон для файла: `if (fromFile && kind === 'embed' && !isModelFile(embed))
    return say('Выберите файл модели', true);`. Нынешний заслон остаётся для сервера.
  - Пропсы `LlmSection` эмбеддингов: `fromFile`, `shareable={canShareChat(chat)}`,
    `onsource={switchSource}`, `onpickfile={pickFile}`.

- [ ] **Шаг 5. `WizardLlm.svelte`, шаг эмбеддингов.**
  - Состояние `fromFile`. В `refresh`:
    - если `isModelFile(now.embed)` — `fromFile = true`, `creds = now.embed`;
    - иначе `sameAsChat` — как сейчас, но `false`, если `!canShareChat(now.chat)`.
  - Над галочкой — `Dropdown` `EMBED_SOURCES`. В режиме файла вместо полей — путь, кнопка
    «Выбрать файл» (`call('settings.pick_model_file')`, выбранное → `creds = fileCreds(path)`,
    `status = null`). Галочки нет.
  - `check()`: в режиме файла без файла — `status = { tone: 'err', text: 'Выберите файл модели.' }`,
    иначе сразу `probe()`.
  - `save()`: заслон `fromFile ? fileTrouble(creds) : llmTrouble(creds)`. В режиме файла `creds`
    уходит как есть.
  - Шаг чата: подзаголовок «Подойдёт любой сервис с OpenAI-совместимым API или Anthropic (Claude).»

- [ ] **Шаг 6. Сборка и сторожа.** `npm test` в `client/web`. `pipenv run pytest
  tests/client/test_page_contract.py tests/client/test_front_vocabulary.py -q`: новый зов
  `settings.pick_model_file` найден и существует на `Api`. `npm run build`.

- [ ] **Шаг 7. Показ вам.** Приложение из исходников. Экран настроек (чат на Anthropic, эмбеддинги
  в обоих режимах) и шаги мастера. Снимки. Правки вида — по вашим словам, круг повторяется, пока
  не скажете «принято».

- [ ] **Шаги 8–10.** Карта фронта
  (`pipenv run python "C:/Users/deade/.claude/skills/free-hands/skills/keeping-code-clean/tools/front_map.py"`)
  и карты питона, ревью, коммит.

---

### Задача 6. README

- [ ] Переписать разделы README под новое, по коду:
  - стек: Anthropic SDK и `llama-cpp-python`;
  - «Что делает бот», пункт про эмбеддинги: они нужны для отсева повторов, а не для сравнения
    с резюме;
  - мастер: Anthropic и «Файл модели»; разбор резюме моделью уже включён;
  - зависимости;
- [ ] Коммит.

---

### Итоговое ревью

После всех задач:
- полный набор `pipenv run pytest -q` и `npm test`;
- агенты по манифесту, дубликатам и ошибкам на весь диф ветки;
- полнота относительно спеки: каждый её пункт указан задачей.

Сама сборка exe в план не входит: её запускают по команде человека, когда всё закончено.

Мутаций нет: они отменены в проекте.
