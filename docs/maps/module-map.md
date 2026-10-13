# Карта модулей

Собирается из кода, а не ведётся руками.
Править руками нельзя — правки затрёт следующая сборка.
Число в скобках — сколько строк занимает объявление.

## . — 2 модулей

### `config.py` — 122 строк

Bootstrap config.

Зависит от: `adapters.browser`, `adapters.telegram`, `backend.bot.media`

- `def _user_data_dir() -> Path` (12)
- `def get_data_dir() -> Path` (5)
- `def get_database_url() -> str` (4)
- `def get_lock_path() -> Path` (8)
- `def data_files() -> list[Path]` (19)
- `def _log_files() -> list[Path]` (4)
- `def data_dirs() -> list[Path]` (18)
- `def get_log_path() -> Path` (7)

### `main.py` — 193 строк

Job Bot — single CLI entry point.

Зависит от: `backend`, `backend.crypto`, `backend.log_file`, `backend.single_instance`, `client.raise_window`, `client.trouble_box`, `client.window`, `config`

- `def _use_utf8_stdout() -> None` (18)
- `def _log_handlers() -> list[logging.Handler]` (27)
- `def _log_uncaught(exc_type, exc, tb) -> None` (13)
- `def _log_uncaught_in_thread(args) -> None` (10)
- `def _started_or_told_why() -> int` (36)
- `def main() -> int` (30)

## adapters — 20 модулей

### `adapters/agent_mcp.py` — 97 строк

MCP-сервер инструментов одной сессии агента: HTTP на 127.0.0.1, токен в адресе.

Зависит от: —

- `class ToolServer` (22)
  - `async def close(self) -> None` (17)
- `def tool_host(tools: list[Callable], **settings) -> FastMCP` (7)
- `async def serve_tools(tools: list[Callable]) -> ToolServer` (28)
- `async def _started(server: uvicorn.Server, task: asyncio.Task) -> None` (10)

### `adapters/app_tied_process.py` — 188 строк

Дочерние процессы, которые Windows снимает вместе с приложением.

Зависит от: —

- `class _IoCounters(ctypes.Structure)` (5)
- `class _BasicLimit(ctypes.Structure)` (12)
- `class _ExtendedLimit(ctypes.Structure)` (9)
- `class _ProcessEntry(ctypes.Structure)` (13)
- `def _kernel32()` (15)
- `def _kill_on_close_job()` (15)
- `def _assign(job, pid: int) -> None` (11)
- `def tie_to_app(pid: int) -> None` (15)
- `def tie_children_named(name: str) -> int` (13)
- `def _children() -> list[tuple[int, str]]` (13)
- `def _snapshot() -> list[tuple[int, int, str]]` (16)

### `adapters/browser.py` — 280 строк

Браузер человека на движке Chromium под управлением Playwright.

Зависит от: `adapters.app_tied_process`, `backend.domain.hosts`, `config`

- `class InstalledBrowser` (4)
- `def find_browser() -> InstalledBrowser | None` (17)
- `def _candidates(relative: str) -> list[Path]` (2)
- `def _first(relative: str) -> Path | None` (2)
- `def _channel(name: str, channel: str, relative: str) -> InstalledBrowser | None` (2)
- `def _by_path(name: str, relative: str) -> InstalledBrowser | None` (3)
- `def _opera() -> InstalledBrowser | None` (10)
- `def remove_profile(profile_id: int) -> None` (8)
- `class BrowserHost` (136)
  - `async def open_profile(self, profile_id: int, sending: bool=True, as_person: bool=False) -> None` (20)
  - `async def page(self)` (8)
  - `async def show(self) -> None` (2)
  - `async def hide_back(self) -> None` (3)
  - `async def clear_cache(self) -> None` (4)
  - `async def wait_closed(self, limit_sec: float) -> bool` (11)
  - `async def close(self) -> None` (7)
  - `async def _launch(self) -> None` (40)
  - `async def _place(self, on_screen: bool) -> None` (10)
  - `def _forget_context(self, closed) -> None` (4)
  - `async def _close_context(self) -> None` (4)
- `async def hold_sending(route) -> None` (13)
- `def _is_captcha(url: str) -> bool` (8)
- `def _accept_dialogs(page) -> None` (4)

### `adapters/claude.py` — 145 строк

Claude через официальный SDK Anthropic: соединение, запрос и перечень моделей.

Зависит от: `backend.provider_config`

- `class MissingKey(Exception)` (2)
- `class ClaudeClient(anthropic.AsyncAnthropic)` (5)
  - `async def aclose(self) -> None` (2)
- `def make_client(config: LlmProviderConfig, *, timeout: float) -> ClaudeClient` (7)
- `def _require_key(client: ClaudeClient) -> None` (9)
- `def split_system(messages: list[dict[str, str]]) -> tuple[str, list[dict[str, str]]]` (8)
- `def _params(model: str, messages: list[dict[str, str]], max_tokens: int) -> dict` (13)
- `async def ask(client: ClaudeClient, model: str, request)` (19)
- `async def list_models(client: ClaudeClient) -> list[str]` (4)
- `async def ping(client: ClaudeClient, model: str, text: str) -> None` (11)

### `adapters/claude_code.py` — 112 строк

Claude через установленный Claude Code по подписке: запросы и перечень моделей.

Зависит от: `adapters`, `adapters.claude`

- `class CliTrouble(Exception)` (10)
- `class ClaudeCodeClient` (8)
  - `async def aclose(self) -> None` (2)
- `def make_client(*, timeout: float) -> ClaudeCodeClient` (3)
- `def _find_cli() -> str | None` (12)
- `def cli() -> str` (6)
- `def reply_of(data: dict) -> tuple[str | None, str | None]` (7)
- `async def _converse(client: ClaudeCodeClient, model: str, messages: list[dict], timeout: float | None) -> tuple[str | None, str | None]` (12)
- `async def ask(client: ClaudeCodeClient, model: str, request)` (8)
- `async def list_models(_client: ClaudeCodeClient) -> list[str]` (4)
- `async def ping(client: ClaudeCodeClient, model: str, text: str) -> None` (3)

### `adapters/claude_code_agent.py` — 89 строк

Сессия агента в своём процессе Claude Code: инструменты приложения, без чужих настроек.

Зависит от: `adapters`, `adapters.agent_mcp`

- `class AgentEnd` (6)
- `class AgentRun` (8)
- `async def run_agent(run: AgentRun) -> AgentEnd` (19)
- `def _end(data: dict) -> AgentEnd` (9)
- `def _argv(cli: str, run: AgentRun) -> list[str]` (13)
- `def _env() -> dict` (3)

### `adapters/claude_code_process.py` — 270 строк

Живой процесс Claude Code: один на приложение, запросы по одному, сброс после каждого.

Зависит от: `adapters`, `adapters.claude`

- `class ProcessGone(Exception)` (2)
- `class _Session` (3)
- `def framed(instructions: str, data: str) -> str` (5)
- `def stream_argv(cli: str, model: str, system_prompt: str, tools: str) -> list[str]` (23)
- `def subscription_env() -> dict` (3)
- `async def spawn_cli(argv: list[str], env: dict)` (19)
- `def _lock() -> asyncio.Lock` (11)
- `async def send_line(process, text: str) -> None` (5)
- `async def read_result(process) -> dict` (20)
- `async def one_turn(process, text: str) -> dict` (4)
- `async def _cleared(process) -> bool` (12)
- `async def _drop() -> None` (6)
- `async def put_down(process) -> None` (9)
- `async def _ready(cli: str, model: str)` (16)
- `async def exchange(cli: str, model: str, message: str, timeout: float) -> dict` (19)
- `async def shutdown() -> None` (10)

### `adapters/cv_text.py` — 137 строк

Текст резюме, вынутый из файла на диске.

Зависит от: —

- `def _pdf_text(path: Path) -> str` (13)
- `def _docx_lines(parent, document: Document) -> list[str]` (13)
- `def _docx_text(path: Path) -> str` (3)
- `def _plain_text(path: Path) -> str` (19)
- `def read_cv_text(path: Path) -> tuple[str | None, str | None]` (27)

### `adapters/db.py` — 105 строк

Соединение с базой: как его завести и как спросить, живо ли оно.

Зависит от: —

- `def _dump_json(value: object) -> str` (9)
- `def make_engine(database_url: str) -> AsyncEngine` (28)
  - `def _prepare_connection(dbapi_conn, _record)` (10)
- `def _lower(value: object) -> object` (14)
- `def _trim(value: object) -> object` (14)
- `async def ping(session) -> bool` (16)

### `adapters/gguf_embed.py` — 111 строк

Эмбеддинги из GGUF-файла модели, посчитанные в своём процессе без сервера.

Зависит от: —

- `class ModelUnavailable(Exception)` (2)
- `def _open_model(path: str)` (18)
- `class ModelFile` (64)
  - `async def embed(self, text: str) -> list[float]` (3)
  - `def _embed_now(self, text: str) -> list[float]` (10)
  - `def _load(self)` (7)
  - `def listed(self) -> list[str]` (3)
  - `async def check(self, text: str) -> tuple[bool, str]` (13)
  - `async def aclose(self) -> None` (3)
  - `def _release(self) -> None` (5)

### `adapters/github_release.py` — 69 строк

Последний релиз приложения на GitHub.

Зависит от: `adapters.web_page`

- `class Release` (5)
- `def make_client() -> httpx.AsyncClient` (2)
- `async def latest_release() -> Release | None` (25)
- `async def download(url: str, write: Callable[[bytes], None]) -> None` (11)

### `adapters/lm_chat.py` — 239 строк

Обращение к чат-модели провайдера и разбор её ответа.

Зависит от: `adapters`

- `class ChatRequest` (16)
- `class ChatAnswer` (10)
- `async def _post_chat(client: httpx.AsyncClient, model: str, request: ChatRequest, log: logging.Logger)` (29)
- `def _status_refusal(purpose: str, status: int, log: logging.Logger) -> ChatAnswer` (8)
- `def _delivery_refusal(purpose: str, trouble: Exception, log: logging.Logger) -> ChatAnswer` (6)
- `def _warn_if_truncated(finish_reason, purpose: str, log: logging.Logger) -> None` (17)
- `def _answer_or_empty(content, finish_reason, purpose: str, log: logging.Logger) -> ChatAnswer` (21)
- `async def chat(client: httpx.AsyncClient | claude.ClaudeClient | claude_code.ClaudeCodeClient, model: str, request: ChatRequest, log: logging.Logger) -> ChatAnswer` (34)
- `async def _chat_with_claude(client: claude.ClaudeClient, model: str, request: ChatRequest, log: logging.Logger) -> ChatAnswer` (21)
- `async def _chat_with_claude_code(client: claude_code.ClaudeCodeClient, model: str, request: ChatRequest, log: logging.Logger) -> ChatAnswer` (14)
- `def _settled(content: str | None, finish_reason: str | None, purpose: str, log: logging.Logger) -> ChatAnswer` (14)

### `adapters/lm_embed.py` — 35 строк

Числовой отпечаток текста у модели встраиваний.

Зависит от: `adapters`

- `async def embed(client: httpx.AsyncClient | gguf_embed.ModelFile, model: str, text: str) -> list[float]` (20)

### `adapters/lm_models.py` — 206 строк

Перечень моделей у провайдера и проверка, что нужная отвечает.

Зависит от: `adapters`, `adapters.lm_chat`, `adapters.lm_embed`, `adapters.lm_studio`

- `def _ping_request(model: str, kind: str) -> tuple[str, dict]` (14)
- `def _ping_failed(model: str, detail: str) -> tuple[bool, str]` (3)
- `async def _ping_claude(client: claude.ClaudeClient | claude_code.ClaudeCodeClient, model: str) -> tuple[bool, str]` (13)
- `async def model_listed(client: LmClient, model: str) -> tuple[bool, list[str]]` (16)
- `async def check_model(client: LmClient, model: str, kind: str) -> tuple[bool, str]` (37)
- `def _looks_like_embed(name: str) -> bool` (9)
- `async def _loaded_models(client: httpx.AsyncClient, kind: str) -> list[str] | None` (37)
- `async def list_models(client: LmClient, *, kind: str | None=None) -> list[str]` (30)

### `adapters/lm_studio.py` — 58 строк

Соединение с OpenAI-совместимым провайдером моделей.

Зависит от: `adapters`, `backend.provider_config`

- `def make_client(config: LlmProviderConfig) -> 'LmClient'` (20)

### `adapters/site_home.py` — 115 строк

Главная страница сайта: как сайт на ней называет сам себя и чем себя обозначает.

Зависит от: `adapters.web_page`

- `class SiteHints` (5)
- `class SiteHome` (5)
- `def make_client() -> httpx.AsyncClient` (3)
- `async def fetch_home(client: httpx.AsyncClient, host: str) -> SiteHome` (6)
- `async def fetch_icon(client: httpx.AsyncClient, urls: tuple[str, ...]) -> bytes | None` (17)
- `def _icons(soup: BeautifulSoup, base: str) -> tuple[str, ...]` (10)
- `def _vector(tag) -> bool` (2)
- `def _hints(soup: BeautifulSoup) -> SiteHints` (10)

### `adapters/smtp_mail.py` — 75 строк

Отправка письма по SMTP с вложением, под паролем приложения.

Зависит от: `backend.domain.mail_servers`

- `class MailAccountConfig` (5)
- `class OutgoingMail` (5)
- `def send_mail(account: MailAccountConfig, mail: OutgoingMail) -> None` (19)
- `def _part(smtp) -> None` (9)
- `def _message(sender: str, mail: OutgoingMail) -> EmailMessage` (10)

### `adapters/telegram.py` — 222 строк

Сборка клиента Telegram и отправка письма его руками.

Зависит от: `backend.domain.telegram_identity`, `backend.tg_credentials`, `config`

- `def make_client(tg: TgAccountConfig) -> Client` (30)
- `async def send_dm(client: Client, user: str | int, text: str, attachment: str | Path | None=None) -> int | None` (24)
- `def _message_date(messages, bookmark: tuple[int, int]) -> int` (19)
- `async def _dialog_page(client, offset_date: int, offset_id: int, offset_peer)` (16)
- `def _next_bookmark(dialogs, messages) -> tuple[int, int, int] | None` (17)
- `def _peers_of(dialogs, users) -> list` (8)
- `async def list_dialog_peers(client) -> list | None` (44)

### `adapters/telegraph.py` — 118 строк

Статья Telegraph: сходить по адресу и достать из страницы её текст.

Зависит от: `adapters.web_page`

- `def make_client() -> httpx.AsyncClient` (3)
- `def _article_text(html: str) -> str | None` (28)
- `async def fetch_article(client: httpx.AsyncClient, url: str) -> str | None` (24)

### `adapters/web_page.py` — 17 строк

Клиент, которым ходят за чужой веб-страницей.

Зависит от: —

- `def page_client(timeout_sec: float, user_agent: str) -> httpx.AsyncClient` (7)

## alembic — 5 модулей

### `alembic/env.py` — 77 строк

Обвязка alembic: откуда берётся база и чьим движком идут миграции.

Зависит от: `adapters.db`, `alembic`, `backend.models`, `config`

- `def run_migrations_offline() -> None` (10)
- `def do_run_migrations(connection: Connection) -> None` (4)
- `async def run_async_migrations() -> None` (14)
- `def run_migrations_online() -> None` (2)

### `alembic/versions/6cc10045aeb6_projects.py` — 43 строк

projects

Зависит от: `alembic`

- `def upgrade() -> None` (19)
- `def downgrade() -> None` (3)

### `alembic/versions/a9c3e1f07b42_aggregators.py` — 144 строк

aggregators

Зависит от: `alembic`

- `def _source_columns(table: str) -> None` (8)
- `def upgrade() -> None` (83)
- `def downgrade() -> None` (24)

### `alembic/versions/c4d7e2a915b3_one_apply_trail.py` — 30 строк

one apply trail

Зависит от: `alembic`

- `def upgrade() -> None` (4)
- `def downgrade() -> None` (2)

### `alembic/versions/e560edf8b958_init.py` — 272 строк

init

Зависит от: `alembic`

- `def upgrade() -> None` (221)
- `def downgrade() -> None` (28)

## backend — 195 модулей

### `backend/agent/__init__.py` — 1 строк

Агент: всё, что работает за человека на сайтах.

Зависит от: —


### `backend/agent/availability.py` — 25 строк

Чем агенту работать: водитель — Claude Code, браузер — установленный Chromium.

Зависит от: `adapters.browser`, `backend.provider_config`

- `def agent_refusal(chat: LlmProviderConfig | None, browser: InstalledBrowser | None) -> str | None` (7)
- `def current_refusal(chat: LlmProviderConfig | None) -> str | None` (4)

### `backend/agent/human_gate.py` — 156 строк

Ожидание человека: капча, слетевший вход или подтверждение отправки. Срок — час

Зависит от: —

- `class _NoBrowser` (8)
  - `async def show(self) -> None` (2)
  - `async def hide_back(self) -> None` (2)
- `class HumanGate` (128)
  - `async def wait(self, kind: str, host: str, browser=None, payload=None) -> str | dict` (27)
  - `async def _arm(self, kind: str, host: str, browser, payload) -> bool` (16)
  - `def resolve(self, answer=None) -> None` (7)
  - `def reveal(self) -> None` (10)
  - `async def _show(self, browser) -> None` (7)
  - `def abort(self) -> None` (10)
  - `def reset(self) -> None` (6)
  - `async def _take(self, browser) -> str | dict` (13)

### `backend/agent/jobs.py` — 94 строк

Задачи сессий агента и их итоги.

Зависит от: `backend.domain.apply_order`, `backend.models`

- `class Source` (12)
  - `def of(cls, row: Aggregator) -> 'Source'` (3)
- `class Finished` (5)
- `class Failed` (4)
- `class Applied` (4)
- `class LoginJob` (3)
- `class SeekJob` (10)
- `class ApplyJob` (14)

### `backend/agent/kit.py` — 50 строк

Набор, с которым работает сессия агента.

Зависит от: `adapters.browser`, `adapters.claude_code_agent`, `backend.agent.human_gate`, `backend.flows.pipeline`

- `class SessionPlan` (7)
- `class AgentKit` (19)
  - `async def written(self, write: Callable[[AsyncSession], Awaitable[T]]) -> T` (9)

### `backend/agent/prompts/__init__.py` — 1 строк

Тексты промптов агента и сборка его стартовых заданий.

Зависит от: —


### `backend/agent/prompts/applier.py` — 70 строк

Откликатель: отклик на одну вакансию одним способом.

Зависит от: `backend.agent.prompts.screening`, `backend.domain.apply_order`, `backend.llm.rules`, `backend.runtime_settings`

- `def applier_task(job, vacancy_text: str, profile_text: str, today: date) -> str` (18)

### `backend/agent/prompts/frame.py` — 42 строк

Общая рамка агента: правила, по которым работает любая его роль.

Зависит от: `backend.agent.jobs`, `backend.llm.rules`

- `def system_prompt(role_prompt: str, tools: list[Callable]) -> str` (11)

### `backend/agent/prompts/login.py` — 15 строк

Проверка входа: вошёл ли человек на сайт агрегатора.

Зависит от: —

- `def login_task(host: str) -> str` (3)

### `backend/agent/prompts/screening.py` — 33 строк

Скрининг: ответы работодателю от имени человека.

Зависит от: `backend.llm.rules`


### `backend/agent/prompts/seeker.py` — 68 строк

Искатели вакансий: на сайте агрегатора и по всей сети.

Зависит от: —

- `def seeker_task(host: str, last_run: datetime | None, limit: int, today: date) -> str` (3)
- `def web_seeker_task(aggregator_hosts: list[str], last_run: datetime | None, limit: int, today: date) -> str` (8)
- `def blacklisted_sites(hosts: list[str]) -> str` (3)
- `def _bounds(last_run: datetime | None, limit: int, today: date) -> list[str]` (7)
- `def _since(last_run: datetime | None) -> str` (4)

### `backend/agent/sessions.py` — 54 строк

Сессия агента под надзором: сервер, водитель, срок человека и общий срок.

Зависит от: `adapters.agent_mcp`, `adapters.claude_code_agent`, `backend.agent.kit`, `backend.agent.stops`, `backend.task_stop`

- `async def run_guarded(kit: AgentKit, plan: SessionPlan) -> AgentEnd` (23)
- `def live_session(model: str) -> RunSession` (12)
  - `async def run(plan: SessionPlan) -> AgentEnd` (7)

### `backend/agent/stops.py` — 17 строк

Беды, которые снимают всю работу с агентом, а не один её шаг.

Зависит от: —

- `class HumanTimeout(Exception)` (2)
- `class LimitExhausted(Exception)` (2)

### `backend/agent/tools_applier.py` — 96 строк

Инструменты откликателя: своя вакансия и запись отклика на сайте.

Зависит от: `backend.agent.jobs`, `backend.agent.kit`, `backend.domain.apply_order`, `backend.models`, `backend.repository.applications`, `backend.repository.vacancy_brief`

- `class ScreeningPair(TypedDict)` (5)
- `def applier_tools(kit: AgentKit, job: ApplyJob) -> list[Callable]` (22)
  - `async def vacancy() -> str` (4)
  - `async def record_application(via: str, target: str, letter: str='', screening: list[ScreeningPair] | None=None, already_applied: bool=False) -> str` (12)
- `class _Report` (7)
- `def _entry(job: ApplyJob, report: _Report) -> ApplicationEntry` (7)
- `def _lines(screening: list[ScreeningPair]) -> list[tuple[bool, str]]` (3)
- `async def _record(kit: AgentKit, job: ApplyJob, entry: ApplicationEntry) -> str` (3)
- `async def record_and_announce(kit: AgentKit, entry: ApplicationEntry) -> int` (5)
- `async def _append(kit: AgentKit, application_id: int, lines: list[tuple[bool, str]]) -> str` (5)

### `backend/agent/tools_browser.py` — 96 строк

Инструменты браузера для агента: открыть, снять, нажать, ввести, выбрать, приложить резюме.

Зависит от: `backend.agent.kit`

- `def browser_tools(kit: AgentKit, resume: Path | None) -> list[Callable]` (35)
  - `async def browser_open(url: str) -> str` (3)
  - `async def browser_snapshot() -> str` (3)
  - `async def browser_click(selector: str) -> str` (3)
  - `async def browser_type(selector: str, text: str) -> str` (3)
  - `async def browser_select(selector: str, value: str) -> str` (3)
  - `async def browser_attach_resume(selector: str) -> str` (5)
  - `async def browser_back() -> str` (3)
- `async def _act(kit: AgentKit, action: Callable[..., Awaitable]) -> str` (12)
- `async def _snapshot(kit: AgentKit) -> str` (12)
- `async def _attach(page, selector: str, resume: Path) -> None` (12)
- `def _first_line(error: Exception) -> str` (2)

### `backend/agent/tools_common.py` — 91 строк

Общие инструменты агента: анкета, итог сессии, зов человека, отметка входа, неудача способа.

Зависит от: `backend.agent.jobs`, `backend.agent.kit`, `backend.domain.apply_order`, `backend.domain.hosts`, `backend.repository.agent_profile`, `backend.repository.aggregators`

- `def common_tools(kit: AgentKit, job) -> list[Callable]` (31)
  - `async def profile() -> str` (4)
  - `async def finish(result: str, reason: str='') -> str` (8)
- `def _login_target(job) -> int | None` (4)
- `def _need_human(kit: AgentKit, job) -> Callable` (8)
  - `async def need_human(kind: str) -> str` (5)
- `def _host_of(job) -> str | None` (5)
- `def _report_login(kit: AgentKit, aggregator_id: int) -> Callable` (7)
  - `async def report_login(logged_in: bool) -> str` (4)
- `def _report_failure(job: ApplyJob) -> Callable` (9)
  - `async def report_failure(reason: str) -> str` (6)

### `backend/agent/tools_letter.py` — 59 строк

Инструмент письма для отклика: пишет приложение или сверяется письмо агента.

Зависит от: `backend.agent.jobs`, `backend.agent.kit`, `backend.llm.agent_letter`, `backend.models`, `backend.repository.agent_profile`

- `def letter_tools(kit: AgentKit, job: ApplyJob) -> list[Callable]` (17)
  - `async def letter(language: str, limit: int=0, subject: str='', body: str='') -> str` (12)
- `async def letter_ask(kit: AgentKit, vacancy_id: int, language: str, limit: int | None) -> LetterAsk | None` (9)
- `async def _written(kit: AgentKit, job: ApplyJob, ask: LetterAsk) -> str` (7)
- `async def _checked(kit: AgentKit, job: ApplyJob, ask: LetterAsk, own: Letter) -> str` (6)

### `backend/agent/tools_seeker.py` — 141 строк

Инструменты искателя: известна ли вакансия и передача найденного в конвейер.

Зависит от: `backend.agent.jobs`, `backend.agent.kit`, `backend.domain.hosts`, `backend.flows`, `backend.incoming`, `backend.models`, `backend.repository.aggregators`, `backend.repository.vacancies_life`, `backend.repository.vacancy_contacts`

- `def seeker_tools(kit: AgentKit, job: SeekJob, queue) -> list[Callable]` (15)
  - `async def is_known(url: str) -> str` (6)
  - `async def submit_vacancy(text: str, url: str, published: str, contacts: list[str]) -> str` (3)
- `class _Page` (5)
- `async def _submit(kit: AgentKit, job: SeekJob, queue, page: _Page) -> str` (31)
- `def _left(answer: str, job: SeekJob) -> str` (2)
- `async def _numbered(kit: AgentKit, job: SeekJob, url: str) -> tuple[str | None, str]` (11)
- `async def _barred(kit: AgentKit, url: str) -> bool` (4)
- `async def _known(kit: AgentKit, aggregator_id: int, key: str) -> bool` (4)
- `async def _store(kit: AgentKit, job: SeekJob, page: _Page, key: str, embedding: list[float]) -> int` (25)
  - `async def contacts(session) -> None` (3)
- `def _posted(published: str) -> datetime | None` (6)

### `backend/app_version.py` — 25 строк

Версия приложения: единственное место, где оно знает свой номер.

Зависит от: —

- `def _parse(text: str) -> tuple[int, int, int] | None` (6)
- `def newer_version(tag: str) -> str | None` (9)

### `backend/applying/__init__.py` — 5 строк

Откликатель: на каждую вакансию — первый доступный способ, пока один не удастся.

Зависит от: —


### `backend/applying/browser.py` — 79 строк

Браузерный способ: сессия агента на кнопку агрегатора или форму работодателя.

Зависит от: `backend.agent.jobs`, `backend.agent.kit`, `backend.agent.prompts.applier`, `backend.agent.prompts.frame`, `backend.agent.sessions`, `backend.agent.stops`, `backend.agent.tools_applier`, `backend.agent.tools_browser`, `backend.agent.tools_common`, `backend.agent.tools_letter`, `backend.applying.result`, `backend.domain.apply_order`, `backend.repository.agent_profile`, `backend.repository.aggregators`, `backend.repository.vacancy_brief`, `backend.repository.vacancy_status`

- `async def via_browser(kit: AgentKit, vacancy_id: int, way: Way) -> Outcome` (18)
- `async def _mark_unfit(kit: AgentKit, vacancy_id: int, reason: str) -> None` (5)
- `async def _apply_plan(kit: AgentKit, job: ApplyJob) -> SessionPlan | None` (14)
- `def _settle(job: ApplyJob, way: Way) -> Outcome` (14)

### `backend/applying/email.py` — 57 строк

Отклик письмом без агента: модель приложения пишет, сервер почты принимает,

Зависит от: `adapters`, `adapters.smtp_mail`, `backend.agent.kit`, `backend.agent.tools_applier`, `backend.agent.tools_letter`, `backend.applying.result`, `backend.domain.apply_order`, `backend.llm.agent_letter`, `backend.models`, `backend.repository.applications`, `backend.repository.mail_account`

- `async def via_email(kit: AgentKit, vacancy_id: int, way: Way) -> Outcome` (11)
- `async def _send_and_record(kit: AgentKit, vacancy_id: int, way: Way, letter: Letter) -> Outcome` (22)

### `backend/applying/result.py` — 60 строк

Исходы исполнителя способа и то новое о мире, что он узнал по дороге.

Зависит от: —

- `class TelegramClosed` (4)
- `class SiteClosed` (2)
- `class Missed` (5)
- `class Unfit` (7)
- `async def delivered(record: Awaitable, vacancy_id: int) -> Outcome` (11)

### `backend/applying/run.py` — 78 строк

Цикл откликателя: по каждой вакансии первый доступный способ, пока один не удастся.

Зависит от: `backend.agent.kit`, `backend.agent.stops`, `backend.applying.browser`, `backend.applying.email`, `backend.applying.result`, `backend.applying.telegram`, `backend.applying.world`, `backend.domain.apply_order`, `backend.models`

- `async def apply_vacancies(kit: AgentKit, vacancy_ids: list[int]) -> None` (8)
- `async def _apply_one(kit: AgentKit, world: World, vacancy_id: int) -> None` (13)
- `async def apply_chosen(kit: AgentKit, vacancy_id: int, way: Way) -> Outcome` (18)
- `async def _title(kit: AgentKit, vacancy_id: int) -> str` (4)

### `backend/applying/telegram.py` — 134 строк

Отклик в Telegram: письмо HR, доставка и след в базе.

Зависит от: `adapters`, `backend.agent.kit`, `backend.applying.result`, `backend.applying.telegram_ban`, `backend.applying.telegram_letter`, `backend.domain.apply_order`, `backend.domain.telegram_identity`, `backend.models`, `backend.payloads`, `backend.repository.applications`, `backend.repository.hr_identify`, `backend.repository.messages`, `backend.telegram_time`

- `class _Errand` (14)
- `async def via_telegram(kit: AgentKit, vacancy_id: int, way: Way) -> Outcome` (15)
- `async def _errand(kit: AgentKit, vacancy_id: int) -> _Errand | None` (19)
- `async def _letter(kit: AgentKit, errand: _Errand) -> Letter | Missed` (6)
- `async def _deliver(kit: AgentKit, peer: int | str, letter: Letter) -> int | None | Missed` (15)
- `async def _record(kit: AgentKit, errand: _Errand, way: Way, letter: Letter, tg_message_id: int | None) -> None` (21)

### `backend/applying/telegram_ban.py` — 32 строк

Срок, до которого Telegram просил не писать: запись и снятие.

Зависит от: —

- `async def note_flood_wait(rs, error) -> float` (14)
- `async def clear_flood_wait(rs) -> None` (8)

### `backend/applying/telegram_letter.py` — 106 строк

Письмо HR в Telegram: полное с резюме или короткое вдогон.

Зависит от: `backend.llm.cover_letter`, `backend.models`, `backend.payloads`

- `class Letter` (9)
- `def format_channel_ref(channel_username: str | None) -> str | None` (8)
- `def short_note(title: str, channel_ref: str | None, prior_count: int) -> str` (19)
- `async def full_letter(pipeline, parsed: ParsedVacancy, channel_ref: str | None, vacancy_id: int)` (27)
- `def parsed_from_row(v: Vacancy) -> ParsedVacancy` (17)

### `backend/applying/world.py` — 87 строк

Факты для выбора способа: что известно о вакансии и что сейчас доступно.

Зависит от: `backend.agent.availability`, `backend.applying.result`, `backend.domain.apply_order`, `backend.models`, `backend.repository.aggregators`, `backend.repository.mail_account`, `backend.repository.vacancy_contacts`

- `async def read_world(rs, session_factory) -> World` (12)
- `async def awaits_application(session_factory, vacancy_id: int) -> bool` (7)
- `async def vacancy_facts(session: AsyncSession, vacancy_id: int) -> VacancyFacts | None` (14)
- `def _handle(hr: HR | None) -> str | None` (7)
- `async def ways_in(session_factory, world: World, vacancy_id: int) -> list[Way]` (5)
- `async def available_ways(rs, session_factory, vacancy_id: int) -> list[Way]` (3)
- `def learn(world: World, lesson: Lesson) -> None` (6)

### `backend/bootstrap.py` — 41 строк

First-run bootstrap: ensure DB schema exists.

Зависит от: `alembic`

- `def alembic_config() -> Config` (10)
- `def ensure_schema() -> None` (9)

### `backend/bot/aggregators.py` — 116 строк

Работа агента у бота с источниками: обход агрегаторов, вход на сайт и удаление источника.

Зависит от: `adapters.browser`, `backend.agent.availability`, `backend.agent.jobs`, `backend.agent.kit`, `backend.bot`, `backend.flows.aggregator_login`, `backend.flows.aggregator_round`, `backend.models`, `backend.repository`

- `def aggregators_available(bot) -> str | None` (3)
- `def human_done(bot, answer=None) -> None` (4)
- `def reveal_browser(bot) -> None` (3)
- `async def seek_all(bot, kit: AgentKit) -> None` (17)
- `async def run_aggregator_now(bot, aggregator_id: int) -> AgentOutcome` (13)
  - `async def one_source(kit: AgentKit) -> str` (3)
- `async def login_aggregator(bot, aggregator_id: int) -> AgentOutcome` (12)
  - `async def login(kit: AgentKit) -> str` (2)
- `async def delete_aggregator(bot, aggregator_id: int) -> str` (10)
- `async def _row(bot, aggregator_id: int) -> Aggregator | None` (3)
- `async def _refused(bot, row: Aggregator) -> AgentOutcome | None` (10)

### `backend/bot/apply.py` — 53 строк

Отклик по нажатию человека: тот же откликатель, в месте прогона с набором агента.

Зависит от: `backend.agent.kit`, `backend.applying`, `backend.applying.result`, `backend.bot`, `backend.domain.apply_order`, `backend.flows.handover`, `backend.models`

- `async def apply_chosen_way(bot, vacancy_id: int, way: Way) -> ApplyOutcome` (16)
  - `async def apply(kit: AgentKit) -> str` (8)
- `async def apply_all_new(bot) -> work.WorkOutcome` (13)
  - `async def apply(kit: AgentKit) -> str` (4)

### `backend/bot/can_send.py` — 55 строк

Ответ на вопрос «можно ли писать этому HR» для переписки из окна.

Зависит от: `adapters`, `backend.domain.telegram_identity`, `backend.repository.hr_card`

- `class SendPermission` (8)
- `async def can_send_to_hr(bot, hr) -> SendPermission` (24)

### `backend/bot/channels.py` — 115 строк

Каналы по просьбе окна: заведение нового и чтение по требованию.

Зависит от: `backend.bot`, `backend.flows`, `backend.repository.channels`, `backend.telegram_lookup`

- `async def poll_channel_now(bot, channel_id: int) -> ChannelPollOutcome` (24)
- `async def _ask_telegram_about(bot, username: str)` (19)
- `async def add_channel(bot, username: str) -> tuple[int | None, ChannelAddOutcome]` (38)

### `backend/bot/chat.py` — 216 строк

Переписка с HR из окна: отправка текста, файла и отметка о прочтении.

Зависит от: `backend.bot`, `backend.models`, `backend.payloads`, `backend.repository.messages`, `backend.telegram_time`

- `async def mark_hr_chat_read(bot, hr_id: int) -> int` (22)
- `async def _tell_telegram_it_is_read(bot, hr: HR, hr_id: int) -> None` (20)
- `async def _target_or_refuse(bot, hr_id: int) -> int | str` (18)
- `async def _persist_outgoing(bot, outgoing: OutgoingMessage) -> Message` (10)
- `async def send_to_hr_chat(bot, hr_id: int, text: str) -> Message` (32)
- `def _checked_kind(src: Path, file_path: str) -> bool` (28)
- `async def send_to_hr_media(bot, hr_id: int, file_path: str) -> Message` (38)

### `backend/bot/client.py` — 408 строк ⚠ подошёл к 300

Сборка бота: его состояние, соединения и поверхность, которой пользуется окно.

Зависит от: `adapters`, `backend.agent.human_gate`, `backend.applying`, `backend.bot`, `backend.domain.apply_order`, `backend.domain.telegram_identity`, `backend.flows.pipeline`, `backend.models`, `backend.notify`, `backend.runtime_settings`

- `def _shares_provider(a, b) -> bool` (12)
- `def _open_connections(bot, runtime_settings: RuntimeSettings) -> None` (18)
- `def _subscribe_to_updates(bot) -> None` (33)
- `def _declare_loop_controls(bot) -> None` (23)
- `def _declare_ui_hooks(bot) -> None` (41)
- `def _forward_pipeline_hooks(bot) -> None` (17)
- `class Bot` (206)
  - `def is_ready(self) -> bool` (7)
  - `def is_connected(self) -> bool` (13)
  - `def is_running_round(self) -> bool` (8)
  - `def kick(self) -> None` (8)
  - `def request_stop(self) -> None` (8)
  - `async def poll_channel_now(self, channel_id) -> channels.ChannelPollOutcome` (4)
  - `async def add_channel(self, username) -> tuple[int | None, channels.ChannelAddOutcome]` (4)
  - `def cancel_current_poll(self) -> None` (2)
  - `async def force_poll_once(self) -> work.WorkOutcome` (11)
  - `async def mark_hr_chat_read(self, hr_id) -> int` (2)
  - `async def send_to_hr_chat(self, hr_id, text) -> Message` (2)
  - `async def send_to_hr_media(self, hr_id, file_path) -> Message` (2)
  - `async def apply_vacancies(self, vacancy_ids: list[int]) -> None` (3)
  - `async def _on_raw_update(self, _client, update, _users, _chats) -> None` (2)
  - `async def _on_dm_edit(self, _client, msg) -> None` (2)
  - `async def _on_dm_delete(self, _client, messages) -> None` (2)
  - `async def _on_dm_outgoing(self, _client, msg) -> None` (2)
  - `async def _on_dm(self, _client, msg) -> None` (2)
  - `async def log_out_session(self) -> None` (2)
  - `async def current_mode(self) -> BotMode` (2)
  - `async def run(self, *, once=False) -> None` (2)
  - `async def ui_rerun_vacancy_pipeline(self, vacancy_id) -> rerun.RerunOutcome` (4)
  - `async def ui_ingest_pasted_text(self, text, posted_at) -> pasted.PastedOutcome` (4)
  - `async def ui_forget_vacancy(self, vacancy_id) -> bool` (2)
  - `async def run_aggregator_now(self, aggregator_id) -> aggregators.AgentOutcome` (2)
  - `async def login_aggregator(self, aggregator_id) -> aggregators.AgentOutcome` (2)
  - `async def apply_chosen_way(self, vacancy_id: int, way: Way) -> apply.ApplyOutcome` (2)
  - `async def apply_all_new(self) -> work.WorkOutcome` (2)
  - `async def download_update(self) -> update.DownloadOutcome` (2)
  - `def human_done(self, answer=None) -> None` (2)
  - `def reveal_browser(self) -> None` (2)
  - `async def delete_aggregator(self, aggregator_id) -> str` (2)

### `backend/bot/loop.py` — 283 строк

Жизненный цикл соединения: режим работы, главный цикл, выход из сеанса.

Зависит от: `adapters`, `backend.bot`, `backend.flows.dm_backfill`, `backend.models`, `backend.repository.bot_mode`, `backend.tg_credentials`

- `async def log_out_session(bot) -> None` (17)
- `async def current_mode(bot) -> BotMode` (7)
- `async def _read_dialogs(bot) -> None` (13)
- `async def _connect(bot) -> None` (30)
- `async def _on_mode_switch(bot, prev_mode: BotMode, mode: BotMode) -> None` (16)
- `def _spawn_catch_up(bot) -> None` (20)
  - `async def work() -> None` (7)
- `async def _tick(bot, mode: BotMode) -> None` (20)
- `async def _sleep_until_wake(bot) -> None` (17)
- `async def _disconnect(bot) -> None` (33)
- `async def _turn_done(bot) -> None` (4)
- `async def run(bot, *, once: bool=False) -> None` (39)
- `async def persist_session_if_changed(bot) -> None` (25)

### `backend/bot/media.py` — 163 строк

Вложения: распознание, кэш и скачивание.

Зависит от: `backend.domain.image_types`, `config`

- `def _has_photo_content(path: Path) -> bool` (13)
- `def looks_like_photo(path: Path) -> bool` (11)
- `def classify_media(msg) -> tuple[str | None, str | None]` (11)
- `def media_cache_path(hr_id: int, tg_message_id: int, ext: str) -> Path` (5)
- `def _cache_ext(as_photo: bool, name: str | None) -> str` (12)
- `def cache_sent_file(src: Path, hr_id: int, tg_message_id: int, *, as_photo: bool) -> str | None` (24)
- `def media_path_for_db(path) -> str` (11)
- `async def download_media(client, msg, hr_id: int) -> str | None` (25)

### `backend/bot/pasted.py` — 38 строк

Заведение вакансии по вставленному тексту — из окна.

Зависит от: `backend.bot`, `backend.flows`

- `async def ui_ingest_pasted_text(bot, text: str, posted_at: datetime | None) -> PastedOutcome` (19)

### `backend/bot/rerun.py` — 38 строк

Ручной перезапуск разбора вакансии из окна.

Зависит от: `backend.bot`, `backend.flows`

- `async def ui_rerun_vacancy_pipeline(bot, vacancy_id: int) -> RerunOutcome` (20)

### `backend/bot/slot.py` — 189 строк

Единственное место прогона: пока оно занято, второй цикл получает отказ.

Зависит от: `backend.notify`

- `def on_runner_loop(bot, action: Callable[[], Any]) -> None` (14)
- `def cancel_current_poll(bot) -> None` (7)
- `async def _run_task(bot, work: Callable[[], Any], label: str)` (31)
- `async def run_in_slot(bot, work: Callable[[], Any], label: str, progress: tuple[str, str, int, int] | None=None) -> tuple[CycleOutcome, Any]` (29)
- `async def answer_in_slot(bot, work: Callable[[], Any], label: str, progress: tuple[str, str, int, int] | None=None) -> Any` (14)
- `def launch_in_slot(bot, work: Callable[[], Any], label: str) -> bool` (18)
- `async def settle_slot(bot, timeout: float) -> None` (19)
- `def slot_taken(bot) -> bool` (3)
- `def _occupy(bot, label: str) -> bool` (7)
- `def _release(bot) -> None` (4)

### `backend/bot/turn.py` — 52 строк

Полный оборот автоматики одной задачей: недоразобранное, каналы, агрегаторы.

Зависит от: `backend.agent.kit`, `backend.agent.stops`, `backend.bot`

- `def launch_turn(bot, label: str) -> asyncio.Task | None` (17)
  - `async def turn(kit: AgentKit) -> str` (5)
- `async def _recover(bot) -> None` (17)

### `backend/bot/update.py` — 48 строк

Скачивание обновления в месте прогона: пока оно идёт, прогон не начать.

Зависит от: `backend`, `backend.bot`, `backend.notify`

- `async def download_update(bot) -> DownloadOutcome` (26)
  - `def report(got: int, total: int) -> None` (2)

### `backend/bot/updates.py` — 113 строк

Обработчики оповещений Telegram: входящее, эхо, правка, удаление, отметка о прочтении.

Зависит от: `backend.flows`, `backend.flows.dm`, `backend.message_text`, `backend.models`, `backend.notify`

- `async def _muted(bot) -> bool` (8)
- `async def on_raw_update(bot, _client, update, _users, _chats) -> None` (18)
- `async def on_dm_edit(bot, _client, msg) -> None` (18)
- `async def on_dm_delete(bot, _client, messages) -> None` (9)
- `async def on_dm_outgoing(bot, _client, msg) -> None` (13)
- `async def on_dm(bot, _client, msg) -> None` (12)

### `backend/bot/work.py` — 69 строк

Работа в месте прогона с набором агента: набор живёт, пока идёт работа.

Зависит от: `adapters.browser`, `backend.agent.kit`, `backend.agent.sessions`, `backend.agent.stops`, `backend.bot`, `backend.notify`

- `async def agent_work(bot, work: Callable[[AgentKit], Awaitable[str]]) -> str` (21)
- `async def in_slot(bot, job: Callable[[AgentKit], Awaitable[str]], label: str, progress: tuple[str, str, int, int] | None=None) -> str` (4)
- `def _kit(bot) -> AgentKit` (8)

### `backend/crypto.py` — 118 строк

Шифрование секретов мастер-ключом из связки ключей ОС.

Зависит от: —

- `def _check_keyring_backend() -> None` (22)
- `def _get_or_create_master_key() -> bytes` (11)
- `def forget_master_key() -> None` (17)
- `def _cipher() -> Fernet` (2)
- `def encrypt_str(plaintext: str) -> str` (3)
- `def decrypt_or_none(ciphertext: str | bytes | None, what: str) -> str | None` (17)
- `def encrypt_bytes(plaintext: bytes) -> bytes` (2)

### `backend/domain/alphabet.py` — 14 строк

Буквы двух алфавитов, на которых пишут резюме и вакансии.

Зависит от: —


### `backend/domain/apply_order.py` — 104 строк

Какими способами откликнуться и в каком порядке.

Зависит от: `backend.domain.contact_keys`, `backend.domain.hosts`, `backend.models`

- `class Way` (4)
- `class KnownSite` (7)
- `class VacancyFacts` (8)
- `class World` (8)
- `def apply_ways(vacancy: VacancyFacts, world: World) -> list[Way]` (8)
- `def _telegram(vacancy: VacancyFacts, world: World) -> Way | None` (4)
- `def _button(vacancy: VacancyFacts, world: World) -> Way | None` (7)
- `def _form(vacancy: VacancyFacts, world: World) -> Way | None` (11)
- `def _links(vacancy: VacancyFacts) -> list[str]` (3)
- `def _contact_links(vacancy: VacancyFacts) -> list[str]` (2)
- `def _owner(link: str, sites: list[KnownSite]) -> KnownSite | None` (3)

### `backend/domain/blacklist.py` — 56 строк

Поиск запрещённого слова в тексте по границам слова.

Зависит от: —

- `def _is_word_char(ch: str) -> bool` (3)
- `def _compile_word_pattern(variant: str) -> re.Pattern[str]` (13)
- `def _word_match(text_lower: str, variant: str) -> bool` (4)
- `def check_blacklist(raw_text: str, patterns: list[str]) -> str | None` (18)

### `backend/domain/company_hosts.py` — 104 строк

Хосты, которые не бывают домашним сайтом компании.

Зависит от: `backend.domain.hosts`

- `def _is_brand_domain(host: str) -> bool` (15)
- `def is_aggregator_host(host: str) -> bool` (11)

### `backend/domain/company_names.py` — 39 строк

Заглавная буква в названии компании.

Зависит от: —

- `def capitalized_company_name(name: str | None) -> str | None` (32)

### `backend/domain/contact_keys.py` — 70 строк

Контакт вакансии: его вид — почта, телефон, ссылка — и нормальная форма, по которой два написания признаются одним.

Зависит от: `backend.domain.hosts`

- `def contact_key(value: str) -> str` (14)
- `def is_address(value: str) -> bool` (3)
- `def is_link(value: str) -> bool` (7)
- `def _linkish(text: str) -> bool` (2)
- `def _plain(value: str) -> str` (6)
- `def _link_key(text: str) -> str` (11)

### `backend/domain/currency.py` — 24 строк

Карта валют: чем их называют в объявлении и каким знаком печатают.

Зависит от: —


### `backend/domain/dedup.py` — 126 строк

Отсев повторов: векторы заведённых вакансий и поиск ближайшего к новому.

Зависит от: —

- `def cosine_top_match(query: np.ndarray, ids: np.ndarray, matrix: np.ndarray, threshold: float) -> int | None` (43)
- `class EmbeddingCache` (71)
  - `def fill(self, pairs: Iterable[tuple[int, list[float]]], width: int) -> int` (19)
  - `def append(self, vacancy_id: int, vector: list[float]) -> None` (18)
  - `def drop(self, vacancy_id: int) -> None` (7)
  - `def match(self, vector: list[float], threshold: float) -> int | None` (5)

### `backend/domain/fit_fields.py` — 58 строк

Пригодность по полям-перечислениям: что решается о вакансии без модели.

Зависит от: `backend.domain.taxonomy`

- `def _blocked(value: str | None, accepted: list[str] | None, known: tuple[str, ...]) -> str | None` (21)
- `def grade_refusal(grade: str | None, accepted: list[str] | None) -> str | None` (8)
- `def work_format_refusal(remote: str | None, accepted: list[str] | None) -> str | None` (10)

### `backend/domain/funnel.py` — 72 строк

Ступени воронки отбора, выраженные наборами статусов вакансии.

Зависит от: `backend.models`

- `def percent_or_none(numerator: int, denominator: int) -> int | None` (14)

### `backend/domain/hosts.py` — 148 строк

Разбор адреса: нормальный хост, имя сайта, остаток, принадлежность сайту, номер страницы.

Зависит от: `backend.domain.company_names`

- `class AddressParts(NamedTuple)` (5)
- `def normalize_host(url: str | None) -> str` (21)
- `def address_parts(url: str) -> AddressParts` (17)
- `def site_label(host: str) -> str` (6)
- `def host_owns(host: str, link_host: str) -> bool` (6)
- `def owning_hosts(host: str) -> list[str]` (9)
- `def owning_host(url: str, hosts: set[str]) -> str | None` (10)
- `def source_key(url: str, aggregator_host: str | None) -> str | None` (15)
- `def is_arrival_mark(name: str) -> bool` (7)
- `def _numbering(query: str) -> str` (15)
- `def _without_scheme(url: str) -> str` (3)

### `backend/domain/image_types.py` — 26 строк

Тип картинки по её первым байтам — одно правило на вложения Telegram и на окно.

Зависит от: —

- `def image_type(head: bytes) -> str | None` (14)

### `backend/domain/mail_servers.py` — 23 строк

Справочник почтовых серверов: человеку незачем искать сервер своей почты в справке.

Зависит от: —

- `def known_server(address: str | None) -> tuple[str, int] | None` (3)

### `backend/domain/resume_marks.py` — 62 строк

Приметы поста соискателя: метки, по которым он опознаётся без модели.

Зависит от: —

- `def resume_mark(text: str) -> str | None` (13)

### `backend/domain/salary.py` — 323 строк ⚠ подошёл к 300

Разбор свободной строки зарплаты: число, как записано, и валюта.

Зависит от: `backend.domain.currency`

- `def parse_salary(salary: str | None) -> tuple[int | None, int | None, str | None]` (19)
- `def salary_text(low: int | None, high: int | None, currency: str | None) -> str | None` (19)
- `def _named_outright(s: str, part: list[re.Match]) -> bool` (32)
- `def _money_bounds(s: str) -> tuple[int | None, int | None]` (20)
- `def _one_bound(s: str, part: list[re.Match], kept: tuple[re.Match, int]) -> tuple[int | None, int | None]` (14)
- `def _money_part(s: str, run: list[re.Match]) -> list[re.Match]` (21)
- `def _spaced(s: str, pair: list[re.Match]) -> bool` (8)
- `def _one_sided(s: str, hit: re.Match, value: int) -> tuple[int | None, int | None]` (18)
- `def _values(run: list[re.Match]) -> list[tuple[re.Match, int]]` (17)
- `def _runs(s: str) -> list[list[re.Match]]` (15)
- `def _amount(num: str, scale: str | None) -> int` (13)
- `def _scale(marker: str | None) -> int` (5)
- `def currency_sign(s: str | None) -> str | None` (20)

### `backend/domain/scoring.py` — 145 строк

Оценка вакансии по навыкам анкеты.

Зависит от: `backend.domain.skill_names`, `backend.models`

- `def _build_skill_level_lookup(skills: list[ProfileSkill]) -> dict[str, tuple[str, int]]` (33)
- `def build_skill_lookup(skills: list[ProfileSkill]) -> set[str]` (10)
- `def _paid_level(level_lookup: dict[str, tuple[str, int]], item: object, paid: set[str]) -> int | None` (17)
- `def _required_points(level_lookup: dict[str, tuple[str, int]], item: object, paid: set[str]) -> int` (15)
- `def _preferred_points(level_lookup: dict[str, tuple[str, int]], item: object, paid: set[str]) -> int` (10)
- `def score_stack(stack_required: list[str], stack_preferred: list[str], skills: list[ProfileSkill]) -> int` (40)

### `backend/domain/sentence.py` — 18 строк

Законченная фраза: свой знак конца или точка.

Зависит от: —

- `def closed_sentence(text: str) -> str` (3)

### `backend/domain/skill_names.py` — 57 строк

Сведение написаний названия навыка по общему ключу.

Зависит от: —

- `def skill_key(name: str) -> str` (14)
- `def index_by_key(lookup: dict[str, T], names: Iterable[object], value: T) -> list[tuple[str, str, T]]` (31)

### `backend/domain/spellings.py` — 50 строк

Отсев повторов среди написаний: первое встреченное выигрывает.

Зависит от: —

- `def dedupe_first_wins(items: Iterable[T], key: Callable[[T], str], seen: set[str] | None=None) -> list[T]` (38)

### `backend/domain/stack.py` — 46 строк

Стек вакансии: что делают с его половинами, прежде чем показать человеку.

Зависит от: `backend.domain.skill_names`, `backend.domain.spellings`

- `def joined_stack(required: list[str], preferred: list[str]) -> list[str]` (8)
- `def deduped_halves(required: list[str], preferred: list[str]) -> tuple[list[str], list[str]]` (22)

### `backend/domain/taxonomy.py` — 116 строк

Замкнутые перечни значений, которыми описывают вакансию и анкету.

Зависит от: —


### `backend/domain/telegram_identity.py` — 166 строк

Правила опознания собеседника в Telegram по написанному о нём.

Зависит от: —

- `def _strip_link_prefixes(s: str) -> str` (29)
- `def normalize_username(hr_contact: str | None, *, typed_by_a_person: bool=False) -> str | None` (22)
- `def typed_username(value) -> str | None` (24)
- `def telegram_peer(hr) -> int | str | None` (9)
- `class DialogPeer` (10)
- `def hrs_to_catch_up(hrs, dialogs) -> list` (36)

### `backend/domain/tenure.py` — 39 строк

Сроки мест работы: период и стаж, общий и по навыку.

Зависит от: —

- `def place_period(place) -> str` (7)
- `def full_years(start: date, end: date) -> int` (5)
- `def years_in_it(experiences, today: date) -> int` (8)
- `def skill_years(experiences, today: date) -> int` (8)

### `backend/domain/transitions.py` — 136 строк

Граф разрешённых авто-переходов статуса вакансии, вместе с условиями

Зависит от: `backend.models`

- `def is_terminal_for_auto(status: VacancyStatus) -> bool` (9)
- `def should_apply_status(current: VacancyStatus, new: VacancyStatus) -> bool` (7)

### `backend/domain/verdict.py` — 100 строк

Приговор разобранному объявлению до того, как оно войдёт в граф статусов.

Зависит от: `backend.models`, `backend.payloads`

- `def is_empty_vacancy(parsed: ParsedVacancy | None) -> bool` (24)
- `def blacklist_refusal(blacklist_match: str | None) -> str | None` (9)
- `def decide_vacancy_status(score: int, *, threshold: int) -> tuple[VacancyStatus, str | None]` (14)

### `backend/domain/wording.py` — 23 строк

Как узнать написание в тексте: словом, а не куском чужого слова.

Зависит от: —

- `def spelled_alone(text: str, word: str) -> bool` (11)

### `backend/flows/aggregator_login.py` — 36 строк

Вход на сайт агрегатора: человек входит в видимом браузере, агент проверяет вход.

Зависит от: `backend.agent.human_gate`, `backend.agent.jobs`, `backend.agent.kit`, `backend.agent.prompts.frame`, `backend.agent.prompts.login`, `backend.agent.sessions`, `backend.agent.stops`, `backend.agent.tools_browser`, `backend.agent.tools_common`, `backend.models`

- `async def log_in(kit: AgentKit, source: Source) -> str` (22)

### `backend/flows/aggregator_name.py` — 89 строк

Имя и значок агрегатора: как сервис зовут люди и чем он себя обозначает.

Зависит от: `adapters`, `backend.domain.hosts`, `backend.llm.site_name`, `backend.models`, `backend.provider_config`, `backend.repository`

- `async def _named(host: str, hints: site_home.SiteHints, chat: LlmProviderConfig | None) -> str` (11)
- `async def create_named_aggregator(session_factory, address: str, chat: LlmProviderConfig | None) -> tuple[Aggregator | None, str]` (17)
- `async def _site(host: str) -> tuple[site_home.SiteHints, bytes | None]` (9)
- `async def _model_name(host: str, hints: list[str], chat: LlmProviderConfig | None) -> str | None` (12)
- `def _site_like_part(host: str, parts: tuple[str, ...]) -> str | None` (10)

### `backend/flows/aggregator_round.py` — 93 строк

Обход источника-агрегатора: поиск, разбор найденного и передача отобранного.

Зависит от: `adapters.claude_code_agent`, `backend.agent.jobs`, `backend.agent.kit`, `backend.agent.prompts.frame`, `backend.agent.prompts.seeker`, `backend.agent.sessions`, `backend.agent.stops`, `backend.agent.tools_browser`, `backend.agent.tools_common`, `backend.agent.tools_seeker`, `backend.flows.handover`, `backend.flows.parse_queue`, `backend.repository.aggregators`, `backend.telegram_time`

- `async def seek_source(kit: AgentKit, source: Source) -> None` (28)
- `async def _hand_over(kit: AgentKit, queue: ParseQueue) -> None` (3)
- `async def _search(kit: AgentKit, job: SeekJob, queue: ParseQueue) -> AgentEnd` (7)
- `async def _seek_plan(kit: AgentKit, job: SeekJob, queue: ParseQueue) -> SessionPlan` (12)
- `async def _settle(kit: AgentKit, job: SeekJob, end: AgentEnd, started: datetime) -> None` (9)

### `backend/flows/auto_gate.py` — 48 строк

Заслон автоматики: двигает ли она эту вакансию вообще.

Зависит от: `backend.domain.transitions`, `backend.models`

- `async def status_open_for_auto(session_factory, vacancy_id: int) -> tuple[bool, VacancyStatus | None]` (34)

### `backend/flows/batches.py` — 30 строк

Разбор исходов работы, пущенной по людям разом.

Зависит от: —

- `def report_failures(hr_ids: list[int], results: list, what: str, log: logging.Logger) -> None` (25)

### `backend/flows/channels.py` — 379 строк ⚠ подошёл к 300

Обход телеграм-каналов за свежими постами.

Зависит от: `backend.agent.stops`, `backend.flows`, `backend.models`, `backend.notify`, `backend.repository.channels`, `backend.telegram_lookup`

- `async def poll_active_channels(pipeline) -> None` (41)
- `async def _walk_channel(pipeline, ch) -> None` (19)
- `async def _switch_off(pipeline, ch) -> None` (10)
- `async def poll_one_channel(pipeline, channel_id: int) -> PollOutcome` (41)
- `async def refresh_channel_metadata_for_ids(pipeline, channel_ids: list[int]) -> None` (12)
- `async def _store_metadata(pipeline, title_updates: dict[int, str], avatar_updates: dict[int, bytes]) -> None` (19)
- `async def _collect_metadata(pipeline, channels) -> tuple[dict, dict]` (34)
- `async def refresh_channel_metadata(pipeline, channels) -> None` (27)
- `async def _unseen_posts(pipeline, channel_username: str, last_id: int | None)` (23)
- `async def _take_post(pipeline, channel_id: int, channel_username: str, msg) -> bool` (19)
- `def _silence_broke_the_walk(channel_username: str, msg_id: int, silence: int) -> bool` (19)
- `async def poll_channel(pipeline, channel_id: int, channel_username: str, last_id: int | None) -> bool` (42)
- `async def advance_cursor(pipeline, channel_id: int, msg_id: int) -> None` (10)

### `backend/flows/cleanup.py` — 88 строк

Удаление вакансии конвейером — вместе с её вектором в кэше.

Зависит от: `backend.models`, `backend.repository.vacancies_life`

- `async def _delete_and_forget(pipeline, vacancy_id: int, *, trash_reason=_NO_TRASH_EVENT) -> tuple[bool, int | None]` (36)
- `async def forget_vacancy(pipeline, vacancy_id: int) -> bool` (15)
- `async def delete_vacancy_as_trash(pipeline, vacancy_id: int, reason: str | None) -> None` (11)

### `backend/flows/dm.py` — 367 строк ⚠ подошёл к 300

Личная переписка с HR: запись сообщения в обе стороны, привязка, разбор.

Зависит от: `backend.bot.media`, `backend.flows.auto_gate`, `backend.flows.dm_classify`, `backend.message_text`, `backend.payloads`, `backend.repository.hr_card`, `backend.repository.hr_identify`, `backend.repository.messages`, `backend.telegram_lookup`, `backend.telegram_time`

- `class DmHelpers` (19)
- `class _Attachment` (14)
- `async def _attachment_of(client, msg, hr_id: int) -> _Attachment` (14)
- `async def _store_outgoing_row(session_factory, msg, hr_id: int, media: _Attachment) -> OutgoingDmOutcome` (38)
- `async def persist_outgoing_dm(session_factory, client, msg, hr_id: int) -> OutgoingDmOutcome` (19)
- `async def _sender_to_listen_to(session_factory, msg)` (30)
- `async def _attributed_vacancy(session, hr_id: int, msg) -> int | None` (18)
- `def _incoming_row(msg, hr_id: int, vacancy_id: int | None, attachment: _Attachment) -> IncomingMessage` (18)
- `async def _save_incoming(session_factory, msg, attachment: _Attachment)` (36)
- `async def _status_open_for_reply(session_factory, vacancy_id: int)` (14)
- `async def _catch_up_avatar(session_factory, client, msg) -> None` (32)
- `async def _receive(dm, msg, hr_lookup) -> tuple[int | None, int | None]` (9)
- `async def _hand_to_classification(dm, msg, hr_id: int, subject) -> None` (12)
- `async def process_dm(msg, dm: DmHelpers) -> int | None` (37)

### `backend/flows/dm_backfill.py` — 304 строк ⚠ подошёл к 300

Догон пропущенной переписки с HR.

Зависит от: `backend.domain.telegram_identity`, `backend.flows.batches`, `backend.flows.dm`, `backend.models`, `backend.notify`, `backend.repository.hr_list`, `backend.repository.messages`, `backend.telegram_lookup`

- `class DmHooks` (9)
- `async def _fetch_history(client, hr, limit: int) -> list | None` (24)
- `async def _read_or_find(client, hr, target, limit: int) -> list | None` (27)
  - `async def read(peer) -> list` (2)
- `async def _store_outgoing(hr_id: int, dm: DmHelpers, msg) -> bool` (23)
- `async def _store_incoming(hr_id: int, dm: DmHelpers, hooks: DmHooks, msg) -> bool` (27)
- `async def _walk_messages(messages: list, hr_id: int, dm: DmHelpers, hooks: DmHooks) -> bool` (18)
- `async def _reconcile_deletes(session_factory, hr_id: int, messages: list, newest_before: int) -> bool` (37)
- `async def backfill_hr_dm_history(hr, dm: DmHelpers, hooks: DmHooks, *, backfill_limit: int, newest_before: int=0) -> None` (28)
- `async def catch_up_missed_dms(dm: DmHelpers, hooks: DmHooks, *, backfill_limit: int, dialogs) -> None` (38)
- `def spawn_hr_backfill(pipeline, hr) -> None` (23)
  - `async def work() -> None` (7)

### `backend/flows/dm_classify.py` — 324 строк ⚠ подошёл к 300

Разбор переписки с HR языковой моделью.

Зависит от: `backend.flows.auto_gate`, `backend.flows.batches`, `backend.llm.hr_reply`, `backend.models`, `backend.notify`, `backend.payloads`, `backend.repository.hr_card`, `backend.repository.vacancy_status`

- `def schedule_dm_classification(pipeline, hr_id: int, reply: PendingReply) -> None` (27)
- `async def classify_and_apply(session_factory, lm_client, lm_chat_model, text: str, target: tuple[int, int, VacancyStatus]) -> tuple[bool, str | None]` (52)
- `async def _run_debounced_classify(pipeline, hr_id: int) -> None` (22)
- `async def _blacklisted_now(pipeline, hr_id: int) -> str | None` (13)
- `async def _ask_and_apply(pipeline, hr_id: int, burst: list, target) -> None` (42)
- `def _burst_text(buf: list[dict]) -> str` (8)
- `async def classify_and_apply_for_hr(pipeline, hr_id: int) -> None` (37)
- `async def _wait_out(pipeline, tasks: list, *, drain: bool) -> None` (20)
- `async def _cancel_and_wait(pipeline, *, drain: bool) -> None` (12)
- `async def _drain_buffers(pipeline) -> None` (18)
- `async def cancel_pending_dm_classifications(pipeline, *, drain: bool=False) -> None` (37)

### `backend/flows/dm_debounce.py` — 167 строк

Копилка отложенного разбора: пачки писем, таймеры над ними и начавшие.

Зависит от: —

- `class DmDebounce` (162)
  - `def remember(self, hr_id: int, letter: dict) -> int` (15)
  - `def retext(self, hr_id: int, tg_msg_id: int, text: str) -> None` (11)
  - `def forget(self, hr_id: int, tg_msg_id: int) -> None` (14)
  - `def take(self, hr_id: int) -> list[dict]` (3)
  - `def restore(self, hr_id: int, burst: list[dict]) -> int` (27)
  - `def drop(self, hr_id: int) -> None` (3)
  - `def waiting(self) -> list[int]` (3)
  - `def arm(self, hr_id: int, timer: asyncio.Task) -> None` (15)
  - `def claim(self, hr_id: int, timer: asyncio.Task) -> bool` (11)
  - `def begin(self, reading: asyncio.Task) -> None` (3)
  - `def end(self, reading: asyncio.Task) -> None` (3)
  - `def busy(self) -> list[asyncio.Task]` (3)
  - `def cancel_timers(self) -> list[asyncio.Task]` (10)
  - `def forget_timers(self) -> None` (3)
  - `def forget_bursts(self) -> None` (3)

### `backend/flows/dm_sync.py` — 197 строк

Сверка переписки с тем, что случилось с ней на стороне Telegram.

Зависит от: `backend.flows.dm`, `backend.message_text`, `backend.models`, `backend.repository.hr_identify`, `backend.repository.messages`, `backend.telegram_time`

- `async def mark_read(session_factory, user_id: int, max_id: int) -> int | None` (15)
- `async def sync_edit(session_factory, msg) -> tuple[int, bool] | None` (23)
- `def _split_by_chat(messages) -> tuple[dict[int, list[int]], list[int]]` (17)
- `def _chat_username(messages, chat_id: int) -> str | None` (11)
- `async def _tombstone_in_chat(session_factory, chat_id: int, msg_ids: list[int], messages)` (15)
- `async def _tombstone_chatless(session_factory, chatless_ids: list[int]) -> set[int]` (19)
- `def _forget_all(forget_pending, hr_id: int, msg_ids) -> None` (4)
- `async def tombstone_deleted(session_factory, messages, forget_pending) -> set[int]` (28)
- `async def store_outgoing(session_factory, client, msg) -> int | None` (17)

### `backend/flows/embeddings.py` — 122 строк

Отпечаток текста: как его считают у поставщика и как поднимают кэш.

Зависит от: `adapters`, `adapters.gguf_embed`, `backend.models`

- `class ProviderIsSilent(Exception)` (7)
- `def _is_about_the_provider(trouble: Exception) -> bool` (18)
- `async def embed_text(pipeline, text: str, what: str) -> list[float] | None` (25)
- `async def similar_vacancy_id(pipeline, embedding: list[float]) -> int | None` (11)
- `async def ensure_embedding_cache(pipeline, width: int) -> None` (28)

### `backend/flows/events.py` — 33 строк

Запись события вакансии своей транзакцией.

Зависит от: `backend.repository.vacancies_life`

- `async def record_vacancy_event(session_factory, vacancy_id: int, kind: str, payload: dict) -> None` (24)

### `backend/flows/fit_refusal.py` — 171 строк

Отказ в пригодности: пост не вакансия, мимо анкеты по полям или по суждению модели.

Зависит от: `adapters.lm_chat`, `backend.domain.fit_fields`, `backend.domain.verdict`, `backend.llm.answers`, `backend.llm.fit_languages`, `backend.llm.fit_preferences`, `backend.llm.fit_role`, `backend.llm.genre`

- `def unanswered(what: str, trouble: str | None, vacancy_id: int) -> tuple[str | None, bool] | None` (28)
- `def _fit_verdict_refusal(validation) -> str | None` (17)
- `async def _fit_refusal(pipeline, parsed, text: str, vacancy_id: int) -> tuple[str | None, bool]` (37)
- `async def _genre_refusal(pipeline, text: str, vacancy_id: int) -> tuple[str | None, bool]` (20)
- `def _fields_refusal(parsed, profile) -> str | None` (12)
- `async def unfit_refusal(pipeline, parsed, text: str, vacancy_id: int) -> tuple[str | None, bool]` (21)

### `backend/flows/ghosting.py` — 37 строк

Гашение вакансий, по которым HR замолчал дольше срока.

Зависит от: `backend.domain.transitions`, `backend.notify`, `backend.repository.vacancies_ghosting`

- `async def check_ghosting_timeouts(pipeline) -> int` (26)

### `backend/flows/handover.py` — 59 строк

Передача отобранного откликателю: решение «откликаться» и догон новых HR после отклика.

Зависит от: `backend.applying.world`, `backend.flows`, `backend.flows.dm_backfill`, `backend.flows.parse`, `backend.models`, `backend.repository.hr_card`, `backend.repository.vacancies_common`

- `async def to_apply(session_factory, vacancy_ids: list[int]) -> list[int]` (9)
- `async def new_to_apply(session_factory) -> list[int]` (8)
- `async def hand_over(pipeline, judged: list[tuple[int, Judged]]) -> None` (16)
- `async def judge_and_hand_over(pipeline, vacancy_id: int, text: str, channel_username: str | None, *, allow_delete: bool=True) -> bool` (7)

### `backend/flows/ingest.py` — 154 строк

Приём объявления из канала с отсевом перепостов.

Зависит от: `backend.flows`, `backend.message_text`, `backend.models`, `backend.payloads`, `backend.telegram_time`

- `async def _post_match(pipeline, post: ChannelPost) -> sameness.Match | None` (22)
- `def _waits_to_be_read_out(vacancy_id: int, post: ChannelPost) -> None` (6)
- `async def _resume_or_skip(pipeline, match: sameness.Match, post: ChannelPost, whole: bool) -> None` (29)
- `async def ingest_post(pipeline, channel_id: int, channel_username: str, msg) -> None` (30)
- `def _vacancy_row(post: ChannelPost, embedding: list[float]) -> Vacancy` (14)
- `async def save_new_vacancy(pipeline, post: ChannelPost, embedding: list[float]) -> int | None` (26)

### `backend/flows/intake.py` — 43 строк

Запись новой строки вакансии: строка, событие ленты и вектор в кэше.

Зависит от: `backend.models`, `backend.repository.vacancies_life`

- `async def save_new_vacancy(pipeline, vacancy: Vacancy, kind: str, payload: dict | None=None) -> int` (23)

### `backend/flows/linked_article.py` — 95 строк

Статья, на которую ссылается объявление, дописанная к его тексту.

Зависит от: `adapters`, `backend.domain.spellings`

- `def _article_urls(text: str) -> list[str]` (11)
- `def _blame_the_site(url: str, trouble: httpx.HTTPError) -> None` (16)
- `async def with_linked_articles(text: str) -> tuple[str, bool]` (37)

### `backend/flows/parse.py` — 301 строк ⚠ подошёл к 300

Приговор объявлению: разбор моделью, вердикт по разобранному и что дальше.

Зависит от: `backend.domain.blacklist`, `backend.domain.contact_keys`, `backend.domain.resume_marks`, `backend.domain.scoring`, `backend.domain.verdict`, `backend.flows`, `backend.flows.fit_refusal`, `backend.flows.parse_write`, `backend.llm.rules`, `backend.llm.vacancy`, `backend.models`, `backend.payloads`, `backend.repository.aggregators`, `backend.repository.vacancy_contacts`

- `class Judged` (5)
- `def _judged(written) -> 'Judged'` (6)
- `async def _dropped_as_trash(pipeline, vacancy_id: int, reason: str, *, allow_delete: bool) -> bool` (23)
- `async def _thrown_out_as_a_resume(pipeline, vacancy_id: int, mark: str, allow_delete: bool) -> Judged` (16)
- `async def _parsed_or_dropped(pipeline, vacancy_id: int, text: str, channel_username: str, allow_delete: bool)` (44)
- `async def _barred_site(pipeline, vacancy_id: int, found: list[str]) -> str | None` (10)
- `async def _verdict_for(pipeline, parsed, text: str, vacancy_id: int) -> tuple | None` (38)
- `async def _finish_parse(pipeline, vacancy_id: int, parsed, outcome: Outcome) -> Judged` (4)
- `async def _thrown_out_by_the_verdict(pipeline, vacancy_id: int, skip_reason: str | None, allow_delete: bool) -> bool` (18)
- `async def parse_and_update_vacancy(pipeline, vacancy_id: int, text: str, channel_username: str | None, *, allow_delete: bool=True) -> Judged` (43)
- `async def is_unparsed_vacancy(pipeline, vacancy_id: int) -> bool` (11)
- `async def save_empty_vacancy(pipeline, vacancy_id: int, parsed: ParsedVacancy | None, *, reason: str=EMPTY_SKIP_REASON) -> Judged` (27)

### `backend/flows/parse_queue.py` — 46 строк

Очередь разбора вакансий, найденных агентом: разбор идёт рядом с поиском.

Зависит от: `backend.flows`, `backend.task_stop`

- `class ParseQueue` (35)
  - `def put(self, vacancy_id: int, text: str) -> None` (2)
  - `async def drain(self) -> None` (4)
  - `async def stop(self) -> None` (3)
  - `async def _work(self) -> None` (10)

### `backend/flows/parse_write.py` — 250 строк

Запись исхода разбора: строка вакансии, её контакт, компания и собеседник.

Зависит от: `backend.domain.salary`, `backend.models`, `backend.payloads`, `backend.repository.companies_matching`, `backend.repository.hr_identify`, `backend.repository.vacancies_life`, `backend.repository.vacancy_contacts`, `backend.repository.vacancy_status`, `backend.telegram_lookup`

- `class Outcome` (13)
- `async def _resolve_hr(pipeline, parsed: ParsedVacancy | None)` (12)
- `def _clear_parsed_fields(v: Vacancy, score: int) -> None` (13)
- `def _apply_parsed_fields(v: Vacancy, parsed: ParsedVacancy | None, outcome: Outcome) -> None` (25)
- `def _fields_filled(v: Vacancy) -> list[str]` (11)
- `async def _write_parsed_row(session, vacancy_id: int, parsed: ParsedVacancy | None, outcome: Outcome) -> Vacancy | None` (29)
- `async def _resolve_company(pipeline, parsed) -> tuple[int | None, dict | None]` (32)
- `async def _link_resolved_hr(session, v: Vacancy, resolved) -> tuple[HR | None, bool]` (12)
- `def _parsed_event_payload(v: Vacancy, outcome: Outcome, decision) -> dict` (15)
- `async def persist_parse_outcome(pipeline, vacancy_id: int, parsed: ParsedVacancy | None, outcome: Outcome) -> tuple[HR | None, bool] | None` (41)

### `backend/flows/pasted.py` — 136 строк

Приём объявления, вставленного человеком: тот же конвейер, но без канала.

Зависит от: `backend.flows`, `backend.models`, `backend.repository.vacancies_new`

- `async def ingest_pasted_text(pipeline, text: str, posted_at: datetime | None) -> PastedIntakeOutcome` (30)
- `async def _finish_or_refuse(pipeline, match: sameness.Match, text: str) -> PastedIntakeOutcome` (16)
- `async def _parsed(pipeline, vacancy_id: int, text: str) -> PastedIntakeOutcome` (19)
- `async def _still_there(pipeline, vacancy_id: int) -> bool` (8)
- `async def _save_pasted_vacancy(pipeline, text: str, embedding: list[float], posted_at: datetime | None) -> int` (15)

### `backend/flows/pipeline.py` — 359 строк ⚠ подошёл к 300

Сборка конвейера: его состояние, общие ресурсы и поверхность для зовущих.

Зависит от: `backend.domain.dedup`, `backend.flows`, `backend.flows.dm`, `backend.flows.dm_backfill`, `backend.flows.dm_debounce`, `backend.llm`, `backend.llm.candidate`, `backend.models`, `backend.notify`, `backend.repository.blacklist_marks`, `backend.repository.profile`, `backend.repository.profile_block`, `backend.repository.profile_languages`, `backend.repository.profile_skills`

- `def _declare_caches(pipeline) -> None` (16)
- `def _declare_window_hooks(pipeline) -> None` (32)
- `def _declare_dm_debounce(pipeline) -> None` (19)
- `class LmProviders` (14)
- `class IngestionPipeline` (225)
  - `def mark_shutting_down(self) -> None` (5)
  - `def spawn_backfill(self, work, what: str, *, extra: dict | None=None) -> None` (26)
    - `async def _run() -> None` (7)
  - `def emit_progress(self, stage: str, label: str, current: int, total: int) -> None` (2)
  - `def fire_contacts_changed(self) -> None` (2)
  - `def fire_vacancies_changed(self) -> None` (2)
  - `async def reload_resources(self) -> None` (28)
  - `def cv_path(self)` (10)
  - `def cv_file(self) -> Path | None` (8)
  - `async def check_ghosting_timeouts(self) -> int` (2)
  - `async def rerun_pipeline_for_vacancy(self, vacancy_id) -> rerun.RerunPipelineOutcome` (4)
  - `async def recover_orphan_vacancies(self) -> int` (2)
  - `async def ingest_pasted_text(self, text, posted_at) -> pasted.PastedIntakeOutcome` (4)
  - `async def poll_active_channels(self) -> None` (2)
  - `async def forget_vacancy(self, vacancy_id) -> bool` (2)
  - `async def poll_one_channel(self, channel_id) -> channels.PollOutcome` (4)
  - `async def refresh_channel_metadata_for_ids(self, channel_ids) -> None` (2)
  - `def update_dm_buffer_text(self, hr_id, tg_msg_id, new_text) -> None` (3)
  - `def remove_dm_buffer_msg(self, hr_id, tg_msg_id) -> None` (3)
  - `def schedule_dm_classification(self, hr_id, reply) -> None` (2)
  - `def dm_helpers(self) -> DmHelpers` (15)
  - `def dm_hooks(self) -> DmHooks` (6)
  - `async def cancel_pending_dm_classifications(self, *, drain=False) -> None` (2)

### `backend/flows/rerun.py` — 453 строк ⚠ подошёл к 300

Повторный разбор уже заведённой вакансии.

Зависит от: `adapters`, `backend.agent.stops`, `backend.flows`, `backend.message_text`, `backend.models`, `backend.repository.channels`, `backend.repository.vacancy_status`, `backend.telegram_lookup`, `backend.telegram_time`

- `class _Origin` (14)
- `async def _vacancy_origin(pipeline, vacancy_id: int) -> _Origin | None` (23)
- `async def _post_text(msg, where: str, vacancy_id: int) -> tuple[str, bool] | None` (17)
- `async def _fetch_fresh_text(pipeline, channel_username: str, msg_id: int | None, vacancy_id: int)` (33)
- `async def _store(pipeline, vacancy_id: int, **fields) -> bool` (17)
- `async def _refresh_embedding(pipeline, vacancy_id: int, text: str) -> None` (36)
- `async def _note_rerun(pipeline, vacancy_id: int, origin: '_Origin') -> None` (5)
- `async def _reread_and_store(pipeline, vacancy_id: int, was: str, where: tuple[str, int | None])` (20)
- `async def _text_to_parse(pipeline, origin: '_Origin', vacancy_id: int) -> str` (21)
- `async def rerun_pipeline_for_vacancy(pipeline, vacancy_id: int) -> RerunPipelineOutcome` (38)
- `async def _orphan_rows(pipeline) -> list` (28)
- `def _wait_is_over(created_at) -> bool` (9)
- `async def _text_to_judge_by(pipeline, row) -> tuple[str, bool] | None` (27)
- `async def _recover_one(pipeline, row) -> bool` (20)
- `async def recover_orphan_vacancies(pipeline) -> int` (47)

### `backend/flows/sameness.py` — 32 строк

Узнать в тексте заведённую вакансию: новая, повтор разобранной или брошенная недоразобранной.

Зависит от: `backend.flows`

- `class Match` (7)
- `async def known_or_new(pipeline, text: str, what: str) -> Match | None` (15)

### `backend/health.py` — 90 строк

Живо ли то, на чём держится работа: база, Telegram и модели.

Зависит от: `adapters`

- `async def database_alive(session_factory) -> bool` (14)
- `def telegram_alive(bot) -> bool` (7)
- `async def model_alive(cfg, kind: str) -> bool` (43)

### `backend/incoming.py` — 172 строк

Приведение внешнего ввода к значениям, годным для записи.

Зависит от: —

- `def fold_homoglyphs(text: str) -> str` (12)
- `def text_or_none(value) -> str | None` (16)
- `def int_or_none(value) -> int | None` (3)
- `def amount_or_none(value) -> int | None` (8)
- `def float_or_none(value) -> float | None` (3)
- `def _number_or_none(value, kind)` (19)
- `def moment_or_none(value) -> datetime | None` (16)
- `def str_list(value) -> list[str]` (11)
- `def normalize_enum(value, allowed: tuple[str, ...]) -> str | None` (22)
- `def enum_member_or_none(value, kind: type[enum.Enum])` (8)
- `def normalize_enum_list(values, allowed: tuple[str, ...]) -> list[str]` (15)

### `backend/llm/agent_letter.py` — 102 строк

Письмо и тема для отклика вне Telegram: пишет чат-модель, проверяет сверка фактов.

Зависит от: `adapters.lm_chat`, `backend.llm.answers`, `backend.llm.external`, `backend.llm.factcheck`, `backend.llm.rules`

- `class Letter` (3)
- `class LetterAsk` (6)
- `async def write_letter(ask: LetterAsk, client, model: str) -> tuple[Letter | None, list[str]]` (8)
- `async def check_letter(ask: LetterAsk, letter: Letter, client, model: str) -> tuple[bool, list[str]]` (8)
- `def _request(ask: LetterAsk) -> ChatRequest` (14)
- `def _letter_of(text: str | None) -> Letter | None` (10)
- `def _short_dash(text: str) -> str` (2)
- `def _trouble(letter: Letter, limit: int | None) -> str | None` (7)

### `backend/llm/answers.py` — 255 строк

Разбор того, что ответила модель, порядок двух заходов и жалоба на неудачу.

Зависит от: `adapters.lm_chat`

- `def _last_object_in(text: str) -> tuple[int, int, str] | None` (27)
- `def extract_last_json(answer: str) -> str | None` (37)
- `def json_object(answer: str, log: logging.Logger, purpose: str) -> dict | None` (23)
- `def log_unparseable(answer: str, log: logging.Logger, purpose: str) -> None` (18)
- `def truncation_trouble(finish_reason: str | None) -> str | None` (9)
- `def wants_more_room(parsed, finish_reason: str | None) -> bool` (18)
- `async def read_with_a_second_try(ask, read, tokens: tuple[int, int], told: tuple[logging.Logger, str], *, empty_means: str | None=None)` (41)
- `def _say_unread(answer: str, told: tuple[logging.Logger, str], empty_means: str | None) -> None` (15)
- `def str_or_none(value) -> str | None` (10)

### `backend/llm/candidate.py` — 114 строк

Сведения о кандидате в том виде, в каком они уходят в промпт.

Зависит от: `backend.incoming`, `backend.models`

- `class CandidateLanguage` (5)
- `class CandidateProfile` (20)
- `def format_languages(languages: list[CandidateLanguage] | None) -> str` (16)
- `def format_text(text: str | None) -> str` (8)
- `def format_known_skills(skills) -> str` (17)
- `def candidate_languages(rows: list[ProfileLanguage]) -> list[CandidateLanguage]` (3)
- `def build_candidate_profile(profile: Profile | None, languages: list[ProfileLanguage]) -> CandidateProfile` (20)

### `backend/llm/company.py` — 174 строк

Арбитр: та же это компания, что уже заведена, или новая.

Зависит от: `adapters.lm_chat`, `backend.incoming`, `backend.llm.answers`, `backend.llm.external`, `backend.llm.rules`

- `def _shown_candidates(parsed_name: str, parsed_website: str | None, candidates: list) -> str` (20)
- `def _dedupe_request(parsed_name: str, parsed_website: str | None, candidates: list) -> ChatRequest` (28)
- `def _matched_id(answer: str) -> tuple[int | None, str | None]` (22)
- `async def dedupe_company_with_llm(client: httpx.AsyncClient, model: str, *, parsed_name: str, parsed_website: str | None, candidates: list) -> tuple[int | None, str | None]` (41)

### `backend/llm/cover_letter.py` — 295 строк

Сочинение письма-отклика.

Зависит от: `adapters.lm_chat`, `backend.llm.external`, `backend.llm.factcheck`, `backend.llm.rules`, `backend.payloads`

- `def _letter_request(profile_block: str, parsed: ParsedVacancy, channel_ref: str | None) -> ChatRequest` (39)
- `def _vacancy_ref(parsed: ParsedVacancy, channel_ref) -> str` (9)
- `def _with_vacancy_filled(raw_text: str, parsed: ParsedVacancy, channel_ref) -> str` (27)
- `def _letter_refusal(text: str, finish_reason) -> str | None` (23)
- `async def generate_cover_letter(profile_block: str, parsed: ParsedVacancy, client: httpx.AsyncClient, model: str, *, channel_ref: str | None=None) -> tuple[str | None, str | None]` (50)

### `backend/llm/cv.py` — 498 строк ⚠ подошёл к 300

Разбор резюме моделью: из текста файла — заполненная анкета.

Зависит от: `adapters.lm_chat`, `backend.domain.salary`, `backend.domain.sentence`, `backend.domain.skill_names`, `backend.domain.spellings`, `backend.domain.taxonomy`, `backend.domain.wording`, `backend.incoming`, `backend.llm.answers`, `backend.llm.cv_grounding`, `backend.llm.cv_native`, `backend.llm.external`, `backend.llm.rules`, `backend.models`, `backend.payloads`

- `def _normalize_lang_level(value: object) -> str | None` (25)
- `def _parse_language_item(item) -> tuple[str, str | None] | None` (13)
- `def _parse_languages(raw: object) -> list[ParsedCvLanguage]` (23)
- `def _parse_date(value) -> date | None` (21)
- `def _parse_profile(data: dict) -> ParsedCvProfile | None` (27)
- `def _parse_skill(item) -> ParsedCvSkill | None` (35)
- `def _points(value) -> list[str]` (10)
- `def _parse_experience(item) -> ParsedCvExperience | None` (18)
- `def _parse_project(item) -> ParsedCvProject | None` (13)
- `def _parsed_items(raw: object, parse) -> list` (5)
- `def _parse_cv_json(answer: str) -> ParsedCv | None` (21)
- `async def parse_cv(text: str, client: httpx.AsyncClient, model: str) -> ParsedCv | None` (36)

### `backend/llm/cv_grounding.py` — 379 строк ⚠ подошёл к 300

Что в разобранном резюме не подтверждается его же текстом.

Зависит от: `backend.domain.taxonomy`, `backend.domain.wording`, `backend.incoming`, `backend.llm.hallucination`, `backend.payloads`

- `def _any_named_in(text: str, words: tuple[str, ...]) -> bool` (8)
- `def _grounded_formats(text: str, formats: list[str]) -> list[str]` (18)
- `def _language_named_in(text: str, name: str) -> bool` (18)
- `def _stops_after(text: str, at: int, others: tuple[str, ...]) -> int` (11)
- `def _level_windows(text: str, language: str, others: tuple[str, ...]) -> list[str]` (23)
- `def _level_named_in(near: str, word: str) -> bool` (12)
- `def _level_read_near(windows: list[str]) -> str | None` (16)
- `def _grounded_level(windows: list[str], level: str) -> str` (24)
- `def _company_at(lowered: str, company: str, cursor: int) -> int` (21)
- `def _starts(lowered: str, names: list[str], taken: set[int]) -> list[int]` (22)
- `def _job_blocks(text: str, groups: list[list[str]]) -> list[str | None]` (30)
- `def _grounded_stack(place, block: str | None) -> list[str]` (11)
- `def _grounded_languages(text: str, languages: list) -> list` (13)
- `def _grounded_records(text: str, parsed: ParsedCv) -> tuple[list, list]` (16)
- `def _say_dropped(what: str, was, left) -> None` (3)
- `def grounded_in_cv(parsed: ParsedCv, text: str) -> ParsedCv` (28)

### `backend/llm/cv_native.py` — 73 строк

Родной язык кандидата — тот, на котором написано его резюме.

Зависит от: `backend.domain.alphabet`, `backend.domain.taxonomy`, `backend.payloads`

- `def _resume_language(text: str) -> str` (10)
- `def with_native_language(parsed: ParsedCv, text: str) -> ParsedCv` (40)

### `backend/llm/external.py` — 47 строк

Внешний текст в виде, пригодном для вставки в промпт.

Зависит от: —

- `def external_block(text: str, what: str, then: str='') -> str` (14)
- `def wrap_external(text: str) -> str` (15)

### `backend/llm/factcheck.py` — 171 строк

Сверка письма-отклика с тем, что о кандидате известно.

Зависит от: `adapters.lm_chat`, `backend.incoming`, `backend.llm.answers`, `backend.llm.external`, `backend.llm.rules`

- `def _factcheck_request(profile_block: str, letter: str, about: str) -> ChatRequest` (23)
- `def _verdict_of(obj: dict, elapsed: float) -> tuple[bool, list[str]]` (29)
- `async def factcheck_cover_letter(profile_block: str, letter: str, client: httpx.AsyncClient, model: str, *, about: str='') -> tuple[bool, list[str]]` (39)

### `backend/llm/fit.py` — 197 строк

Общее у зовов о пригодности: чем спросить модель и как прочесть ответ.

Зависит от: `adapters.lm_chat`, `backend.incoming`, `backend.llm.answers`, `backend.llm.external`, `backend.llm.hallucination`, `backend.llm.rules`, `backend.payloads`

- `class FitQuestion` (9)
- `def vacancy_block(parsed: ParsedVacancy, raw_text: str) -> str` (18)
- `def vacancy_text(raw_text: str) -> str` (3)
- `def _parse_fit_validation(answer: str, purpose: str) -> FitValidation | None` (10)
- `def _request(question: FitQuestion, about: str, max_tokens: int) -> ChatRequest` (16)
- `def _without_candidate_data(validation: FitValidation, purpose: str) -> FitValidation` (20)
- `async def ask_fit(question: FitQuestion, about: str, client: httpx.AsyncClient, model: str) -> tuple[FitValidation | None, str | None]` (29)
  - `def read(answer: str) -> FitValidation | None` (4)

### `backend/llm/fit_languages.py` — 124 строк

Один вопрос о вакансии: требует ли она языка, которого у кандидата нет.

Зависит от: `backend.llm.candidate`, `backend.llm.fit`, `backend.llm.hallucination`, `backend.payloads`

- `def _prompt_for(profile: CandidateProfile) -> str` (5)
- `def _without_invented_language(validation: FitValidation, raw_text: str, profile: CandidateProfile) -> FitValidation` (19)
- `async def validate_language_fit(parsed: ParsedVacancy, raw_text: str, client: httpx.AsyncClient, model: str, *, profile: CandidateProfile) -> tuple[FitValidation | None, str | None]` (15)

### `backend/llm/fit_preferences.py` — 95 строк

Один вопрос о вакансии: нарушает ли она то, что кандидат написал словами.

Зависит от: `backend.llm.candidate`, `backend.llm.fit`, `backend.payloads`

- `def _prompt_for(profile: CandidateProfile) -> str` (7)
- `async def validate_preferences_fit(parsed: ParsedVacancy, raw_text: str, client: httpx.AsyncClient, model: str, *, profile: CandidateProfile) -> tuple[FitValidation | None, str | None]` (12)

### `backend/llm/fit_role.py` — 95 строк

Один вопрос о вакансии: та ли это профессия.

Зависит от: `backend.llm.candidate`, `backend.llm.fit`, `backend.payloads`

- `def _prompt_for(profile: CandidateProfile) -> str` (7)
- `async def validate_role_fit(parsed: ParsedVacancy, raw_text: str, client: httpx.AsyncClient, model: str, *, profile: CandidateProfile) -> tuple[FitValidation | None, str | None]` (12)

### `backend/llm/genre.py` — 139 строк

Жанр поста: зовёт ли автор на работу или предлагает себя.

Зависит от: `adapters.lm_chat`, `backend.llm.answers`, `backend.llm.external`, `backend.llm.rules`, `backend.payloads`

- `def _parse_genre(answer: str) -> PostGenre | None` (20)
- `def _genre_request(text: str, max_tokens: int) -> ChatRequest` (17)
- `async def classify_post_genre(text: str, client: httpx.AsyncClient, model: str) -> tuple[PostGenre | None, str | None]` (22)

### `backend/llm/hallucination.py` — 286 строк

Чем негодно обоснование, которое дала модель.

Зависит от: `backend.domain.taxonomy`, `backend.llm.candidate`

- `def language_root(name: str) -> str | None` (18)
- `def _language_marker(root: str, name: str, inference_verbs: str, cefr_text: str) -> tuple[re.Pattern[str], re.Pattern[str]]` (21)
- `def _build_profile_hallucination_markers(profile: CandidateProfile) -> tuple[tuple[re.Pattern[str], re.Pattern[str]], ...]` (30)
- `def looks_hallucinated(reason: str, raw_text: str, profile: CandidateProfile) -> str | None` (23)
- `def breaks_reason_style(reason: str) -> str | None` (15)

### `backend/llm/hr_reply.py` — 270 строк

Разбор ответа HR: на каком этапе теперь отклик.

Зависит от: `adapters.lm_chat`, `backend.domain.transitions`, `backend.llm.answers`, `backend.llm.external`, `backend.models`, `backend.payloads`

- `def _parse_classification(answer: str) -> Classification | None` (19)
- `def _allowed_next(current_status: VacancyStatus) -> set[VacancyStatus]` (21)
- `def _as_line(allowed: set[VacancyStatus]) -> str` (3)
- `def _classify_request(text: str, current_status: VacancyStatus, allowed_str: str) -> ChatRequest` (21)
- `async def classify_hr_reply(text: str, current_status: VacancyStatus, client: httpx.AsyncClient, model: str) -> tuple[Classification | None, str | None]` (55)

### `backend/llm/rules.py` — 278 строк

Приметы предметной области, общие для наставлений модели.

Зависит от: `backend.domain.company_hosts`, `backend.domain.resume_marks`, `backend.domain.taxonomy`

- `def has_placeholder(text: str) -> bool` (9)

### `backend/llm/site_name.py` — 52 строк

Имя сервиса по адресу его сайта — так, как его называют люди.

Зависит от: `adapters.lm_chat`, `backend.llm.external`

- `def _request(host: str, hints: list[str]) -> ChatRequest` (12)
- `async def ask_site_name(host: str, hints: list[str], client: httpx.AsyncClient, model: str) -> str | None` (13)

### `backend/llm/skills.py` — 226 строк

Приведение названий технологий к виду, пригодному для стека вакансии.

Зависит от: `backend.domain.alphabet`, `backend.domain.skill_names`, `backend.domain.spellings`, `backend.llm.rules`

- `def _strip_version(s: str) -> str` (12)
- `def _capitalize_skill(s: str) -> str` (20)
- `def _wrapped_tail(s: str) -> str | None` (4)
- `def _is_name(one: str) -> bool` (8)
- `def _named_tools(s: str) -> list[str]` (19)
- `def _is_wrapped_requirement(s: str) -> bool` (9)
- `def _as_items(raw: object) -> list` (16)
- `def clean_stack_items(raw: object, seen: set[str]) -> list[str]` (36)

### `backend/llm/vacancy.py` — 495 строк ⚠ подошёл к 300

Разбор объявления о вакансии в структурированные поля.

Зависит от: `adapters.lm_chat`, `backend.domain.company_names`, `backend.domain.contact_keys`, `backend.domain.taxonomy`, `backend.domain.telegram_identity`, `backend.incoming`, `backend.llm.answers`, `backend.llm.candidate`, `backend.llm.external`, `backend.llm.rules`, `backend.llm.skills`, `backend.payloads`

- `def _split_stack(data: dict) -> tuple[list, list]` (19)
- `def _company_name_and_site(company_name: str | None, company_website: str | None) -> tuple[str | None, str | None]` (28)
- `def _address_after_label(value: str) -> str` (15)
- `def _contacts(hr_contact: str | None, other_contacts: list[str]) -> tuple[str | None, list[str]]` (17)
- `def _way_to_apply(other_contact: str) -> str | None` (20)
- `def parsed_vacancy_from_json(answer: str) -> ParsedVacancy | None` (16)
- `def _vacancy_of(data: dict, title: str) -> ParsedVacancy` (34)
  - `def _text_field(field: str) -> str | None` (2)
- `def _parse_request(text: str, known_skills, max_tokens: int) -> ChatRequest` (18)
- `def _without_the_channel_itself(parsed: ParsedVacancy, channel_username: str | None) -> ParsedVacancy` (27)
  - `def is_the_channel(contact: str | None) -> bool` (3)
- `def _log_parsed(parsed: ParsedVacancy) -> None` (10)
- `async def parse_vacancy(text: str, client: httpx.AsyncClient, model: str, channel_username: str | None=None, *, known_skills=None) -> tuple[ParsedVacancy | None, str | None]` (39)

### `backend/log_buffer.py` — 214 строк

Журнал в памяти для экрана «Логи»: четыре кольца записей и снимок для окна.

Зависит от: `backend.log_secrets`

- `def _bucket_of(levelname: str) -> str` (9)
- `class LogBufferHandler(logging.Handler)` (121)
  - `def emit(self, record: logging.LogRecord) -> None` (33)
  - `def handleError(self, record: logging.LogRecord) -> None` (6)
  - `def snapshot(self) -> list[dict]` (3)
  - `def _taken(self) -> tuple[list[dict], dict[str, int]]` (20)
  - `def page(self) -> dict` (33)
  - `def clear(self) -> int` (7)
- `def install() -> LogBufferHandler` (23)
- `def get_handler() -> LogBufferHandler` (2)

### `backend/log_file.py` — 62 строк

Файл журнала, переживающий сорванный переход на новый файл.

Зависит от: `backend.log_secrets`

- `class LogFileHandler(RotatingFileHandler)` (53)
  - `def _complain_once(self, what: str, record: logging.LogRecord | None) -> None` (11)
  - `def doRollover(self) -> None` (16)
  - `def handleError(self, record: logging.LogRecord) -> None` (2)

### `backend/log_secrets.py` — 191 строк

Вымарывание секретов из журнала — включая тот случай, когда запись сломалась.

Зависит от: `config`

- `def remember_secret(value: str) -> None` (13)
- `def report_own_failure(what: str, record: logging.LogRecord | None) -> None` (33)
- `def report_own_failure_once(what: str, record: logging.LogRecord) -> None` (13)
- `def _redact(text: str) -> str` (7)
- `class SecretRedactionFilter(logging.Filter)` (36)
  - `def filter(self, record: logging.LogRecord) -> bool` (32)
- `def install_secret_filter() -> None` (11)

### `backend/message_text.py` — 102 строк

Текст сообщения Telegram в том виде, в каком его читают.

Зависит от: —

- `def extract_text(msg) -> str` (2)
- `def _with_link_addresses(text: str, entities) -> str` (21)
- `def extract_post_text(msg) -> str` (15)
- `def _media_placeholder(msg) -> str` (18)
- `def extract_dm_text(msg) -> str` (23)

### `backend/models/__init__.py` — 88 строк

Объявления таблиц базы, собранные из всех предметов.

Зависит от: `backend.models.application`, `backend.models.base`, `backend.models.contacts`, `backend.models.enums`, `backend.models.message`, `backend.models.profile`, `backend.models.settings`, `backend.models.vacancy`

Отдаёт наружу: `HR`, `Aggregator`, `AppSetting`, `Application`, `ApplicationVia`, `Base`, `BLACKLIST_KINDS`, `Blacklist`, `BotMode`, `BotState`, `Company`, `ContactAddedBy`, `Gender`, `LlmConfig`, `LlmConfigKind`, `MailAccount`, `Message`, `Profile`, `ProfileExperience`, `ProfileLanguage`, `ProfileProject`, `ProfileSkill`, `STACK_LINKS`, `SalaryPeriod`, `Screening`, `StatusHistorySource`, `status_code`, `TelegramChannel`, `TgAccount`, `TrashEvent`, `Vacancy`, `VacancyContact`, `VacancyEvent`, `VacancyStatus`, `VacancyStatusHistory`, `profile_experience_skills`, `profile_project_skills`


### `backend/models/application.py` — 46 строк

Отклик и скрининг по нему.

Зависит от: `backend.models.base`, `backend.models.enums`

- `class Application(IdMixin, Base)` (21)
- `class Screening(IdMixin, CreatedAtMixin, Base)` (12)

### `backend/models/base.py` — 65 строк

Основание, от которого объявляются таблицы.

Зависит от: —

- `class Base(DeclarativeBase)` (2)
- `def enum_column(values: type[enum.Enum], name: str) -> SQLEnum` (12)
- `class IdMixin` (4)
- `class CreatedAtMixin` (8)
- `class UpdatedAtMixin` (14)

### `backend/models/contacts.py` — 74 строк

Таблицы сторон, с которыми связана вакансия.

Зависит от: `backend.models.base`

- `class TelegramChannel(IdMixin, Base)` (11)
- `class Aggregator(IdMixin, Base)` (19)
- `class HR(IdMixin, Base)` (17)
- `class Company(IdMixin, Base)` (10)

### `backend/models/enums.py` — 82 строк

Перечисления, которыми колонки ограничивают набор значений.

Зависит от: —

- `class BotMode(enum.Enum)` (4)
- `class VacancyStatus(enum.Enum)` (12)
- `def status_code(status: VacancyStatus) -> str` (15)
- `class StatusHistorySource(enum.Enum)` (11)
- `class LlmConfigKind(enum.Enum)` (3)
- `class ContactAddedBy(enum.Enum)` (4)
- `class ApplicationVia(enum.Enum)` (5)
- `class SalaryPeriod(enum.Enum)` (4)
- `class Gender(enum.Enum)` (3)

### `backend/models/message.py` — 64 строк

Таблица переписки с HR.

Зависит от: `backend.models.base`

- `class Message(IdMixin, Base)` (46)

### `backend/models/profile.py` — 138 строк

Таблицы анкеты кандидата.

Зависит от: `backend.models.base`, `backend.models.enums`

- `class Profile(IdMixin, UpdatedAtMixin, Base)` (29)
- `class ProfileLanguage(IdMixin, Base)` (19)
- `class ProfileSkill(IdMixin, Base)` (10)
- `class ProfileExperience(IdMixin, Base)` (18)
- `class ProfileProject(IdMixin, Base)` (15)

### `backend/models/settings.py` — 125 строк

Таблицы, которыми настраивают работу бота.

Зависит от: `backend.models.base`, `backend.models.enums`

- `class BotState(IdMixin, Base)` (16)
- `class Blacklist(IdMixin, CreatedAtMixin, Base)` (7)
- `class TgAccount(IdMixin, UpdatedAtMixin, Base)` (18)
- `class MailAccount(IdMixin, UpdatedAtMixin, Base)` (15)
- `class LlmConfig(IdMixin, UpdatedAtMixin, Base)` (14)
- `class AppSetting(UpdatedAtMixin, Base)` (7)

### `backend/models/vacancy.py` — 215 строк

Таблицы, в которых конвейер записывает судьбу разобранного поста.

Зависит от: `backend.models.base`, `backend.models.contacts`, `backend.models.enums`

- `class Vacancy(IdMixin, CreatedAtMixin, Base)` (70)
- `class VacancyEvent(IdMixin, CreatedAtMixin, Base)` (16)
- `class TrashEvent(IdMixin, CreatedAtMixin, Base)` (42)
- `class VacancyContact(IdMixin, Base)` (18)
- `class VacancyStatusHistory(IdMixin, Base)` (38)

### `backend/notify.py` — 20 строк

Оповещение окна: позвать подписчика, не дав его поломке уронить работу.

Зависит от: —

- `def fire(hook, name: str, *args) -> None` (13)

### `backend/payloads.py` — 456 строк ⚠ подошёл к 300

Свёртки значений, ходящих между слоями.

Зависит от: `backend.domain.stack`, `backend.models`

- `class ChannelPost` (12)
- `class OutgoingMessage` (21)
- `class IncomingMessage` (19)
- `class PendingReply` (15)
- `class ParsedCvProfile` (19)
- `class ParsedCvLanguage` (3)
- `class ParsedCvSkill` (5)
- `class ParsedCvExperience` (9)
- `class ParsedCvProject` (5)
- `class ParsedCv` (6)
- `class Classification` (3)
- `class ParsedVacancy` (38)
  - `def stack(self) -> list[str]` (11)
- `class PostGenre` (14)
- `class FitValidation` (3)
- `class VacancyDetail` (6)
- `class HrWithCount` (6)
- `class HrDetail` (18)
- `class CompanyDetail` (13)
- `class CompanyWithCount` (4)
- `class ChannelWithCount` (4)
- `class SourceStats` (20)
- `class ChannelDetail` (4)
- `class VacancyFilter` (53)

### `backend/provider_config.py` — 74 строк

Поставщик модели в настройках: из каких полей он состоит и когда настроен.

Зависит от: —

- `def names_model_file(base_url: str | None, model: str | None) -> bool` (6)
- `def serves_claude(base_url: str | None) -> bool` (3)
- `def serves_claude_code(base_url: str | None) -> bool` (3)
- `def chat_only(base_url: str | None) -> bool` (3)
- `def serves_kind(kind: str, base_url: str | None) -> bool` (3)
- `def provider_complete(kind: str, base_url: str | None, model: str | None) -> bool` (15)
- `class LlmProviderConfig` (9)
  - `def names_model_file(self) -> bool` (2)

### `backend/repository/agent_profile.py` — 114 строк

Анкета человека целиком, как её видит агент: со стажем общим и по навыкам.

Зависит от: `backend.domain.salary`, `backend.domain.tenure`, `backend.llm.candidate`, `backend.models`, `backend.repository.profile`, `backend.repository.profile_experience`, `backend.repository.profile_languages`, `backend.repository.profile_projects`, `backend.repository.profile_skills`

- `async def build_agent_profile(session: AsyncSession, today: date) -> str` (17)
- `def _person_lines(p, languages) -> list[str]` (20)
- `def _salary(p) -> str` (7)
- `def _skill_lines(skills, places, projects, today: date) -> list[str]` (5)
- `def _skill_term(skill, places, projects, today: date) -> str` (10)
- `def _record_lines(head: str, labelled: list[tuple[str, list[str]]]) -> list[str]` (3)
- `def _place_lines(places) -> list[str]` (7)
- `def _project_lines(projects) -> list[str]` (7)
- `def _years(years: int) -> str` (2)

### `backend/repository/aggregators.py` — 227 строк

Ведение записей об агрегаторах.

Зависит от: `backend.domain.hosts`, `backend.models`, `backend.models.settings`, `backend.payloads`, `backend.repository.blacklist_marks`, `backend.repository.search`, `backend.repository.source_stats`, `backend.repository.vacancies_common`, `backend.repository.vacancies_life`

- `async def find_aggregator(session: AsyncSession, host: str) -> Aggregator | None` (3)
- `async def create_aggregator(session: AsyncSession, address: str, name: str, avatar: bytes | None) -> tuple[Aggregator | None, str]` (14)
- `async def list_aggregators(session: AsyncSession) -> list[Aggregator]` (5)
- `async def web_search_id(session: AsyncSession) -> int` (3)
- `def aggregator_blacklist_candidates(row: Aggregator) -> list[str]` (10)
- `async def deactivate_blacklisted_aggregators(session: AsyncSession) -> int` (6)
- `async def barred_hosts(session: AsyncSession) -> set[str]` (7)
- `async def barred_host_of(session: AsyncSession, urls: list[str]) -> str | None` (11)
- `async def list_aggregators_with_counts(session: AsyncSession, search: str | None=None) -> list[tuple[Aggregator, int, bool]]` (14)
- `async def get_aggregator_detail(session: AsyncSession, aggregator_id: int) -> tuple[Aggregator, SourceStats, str | None] | None` (9)
- `async def set_aggregator_active(session: AsyncSession, aggregator_id: int, active: bool) -> str` (15)
- `async def set_logged_in(session: AsyncSession, aggregator_id: int, logged_in: bool) -> None` (5)
- `async def mark_run(session: AsyncSession, aggregator_id: int, started_at: datetime) -> None` (4)
- `async def applications_of(session: AsyncSession, aggregator_id: int) -> int` (12)
- `async def delete_aggregator(session: AsyncSession, aggregator_id: int) -> str` (25)
- `async def deletion_block(session: AsyncSession, aggregator_id: int) -> str | None` (6)
- `async def round_sources(session: AsyncSession) -> list[Aggregator]` (13)

### `backend/repository/app_settings.py` — 33 строк

Строка общего словаря настроек: записать значение по ключу.

Зависит от: `backend.models`

- `async def put_app_setting(session: AsyncSession, key: str, value: str) -> None` (7)

### `backend/repository/applications.py` — 114 строк

Отклики и скрининг по ним.

Зависит от: `backend.models`, `backend.repository.vacancies_life`, `backend.repository.vacancy_status`, `backend.telegram_time`

- `class ApplicationEntry` (12)
- `async def record_application(session: AsyncSession, entry: ApplicationEntry) -> int` (22)
- `async def append_screening(session: AsyncSession, application_id: int, lines) -> None` (8)
- `class ScreenedApplication` (5)
- `async def vacancy_screening(session: AsyncSession, vacancy_id: int) -> list[ScreenedApplication]` (16)
- `async def _screening_lines(session: AsyncSession, application_ids: list[int]) -> dict[int, list[tuple[bool, str]]]` (13)
- `async def has_screening(session: AsyncSession, vacancy_id: int) -> bool` (4)

### `backend/repository/blacklist.py` — 344 строк ⚠ подошёл к 300

Ведение чёрного списка.

Зависит от: `backend.domain.hosts`, `backend.incoming`, `backend.models`, `backend.models.settings`, `backend.repository`, `backend.repository.blacklist_marks`

- `async def _hold_the_source_rule(session: AsyncSession, kind: str) -> None` (12)
- `async def set_blacklist_active(session: AsyncSession, blacklist_id: int, active: bool) -> bool` (23)
- `async def deactivate_blacklist_values(session: AsyncSession, kind: str, candidates: list[str]) -> int` (23)
- `async def rename_blacklist_marks(session: AsyncSession, kind: str, *, old_value: str, new_value: str) -> None` (41)
- `class BlacklistUpdateError(ValueError)` (2)
- `def _value_of_kind(kind: str, value: str) -> str` (12)
- `def _required_value(value) -> str` (11)
- `async def _free_value(session: AsyncSession, row: Blacklist, value: str) -> str` (10)
- `async def update_blacklist(session: AsyncSession, blacklist_id: int, *, value=_BLACKLIST_FIELD_UNSET, reason=_BLACKLIST_FIELD_UNSET) -> bool` (32)
- `async def _same_entry(session: AsyncSession, kind: str, value: str) -> Blacklist | None` (11)
- `def _reuse_existing(existing: Blacklist, reason: str | None) -> BlacklistOutcome` (20)
- `async def _insert_blacklist(session: AsyncSession, kind: str, value: str, reason: str | None) -> Blacklist` (15)
- `async def create_blacklist(session: AsyncSession, *, kind: str, value: str, reason: str | None=None) -> tuple[Blacklist, BlacklistOutcome]` (32)
- `async def delete_blacklist(session: AsyncSession, blacklist_id: int) -> bool` (18)
- `async def list_blacklist(session: AsyncSession) -> list[Blacklist]` (15)

### `backend/repository/blacklist_candidates.py` — 125 строк

Подсказки «кого предложить в чёрный список» для окна заведения.

Зависит от: `backend.models`, `backend.models.settings`, `backend.repository.aggregators`, `backend.repository.blacklist_marks`, `backend.repository.channels`, `backend.repository.companies_card`, `backend.repository.hr_card`, `backend.repository.hr_identify`

- `def _by_label(rows: list[dict]) -> list[dict]` (9)
- `def _named_candidates(named: list[tuple[str | None, str | None]]) -> list[dict]` (14)
- `async def _company_candidates(session: AsyncSession) -> list[dict]` (13)
- `async def _aggregator_candidates(session: AsyncSession) -> list[dict]` (15)
- `async def list_blacklist_candidates(session: AsyncSession, kind: str) -> list[dict]` (47)

### `backend/repository/blacklist_marks.py` — 220 строк

Активные строки чёрного списка, по которым предметы получают отметку.

Зависит от: `backend.models`, `backend.models.settings`

- `def account_mark(telegram_user_id: int) -> str` (9)
- `def nickname_mark(telegram_username: str) -> str` (3)
- `def _account_id_of(value: str) -> int | None` (9)
- `def active_mark_of(kind: str, candidates: list[str])` (14)
- `async def active_blacklist_value(session: AsyncSession, kind: str, candidates: list[str]) -> str | None` (21)
- `async def active_blacklist_values(session: AsyncSession, kind: str) -> set[str]` (14)
- `async def _nicknames_of_marked_people(session: AsyncSession) -> list[str]` (30)
- `async def load_active_blacklist_patterns(session: AsyncSession) -> list[str]` (25)
- `def marked_by(candidates: list[str], values: set[str]) -> bool` (9)
- `def preferred_blacklist_value(candidates: list[str]) -> str | None` (10)
- `class BlacklistMark` (40)
  - `async def value(self, session: AsyncSession, row) -> str | None` (3)
  - `async def marked(self, session: AsyncSession) -> set[str]` (3)
  - `def among(self, row, values: set[str]) -> bool` (3)
  - `async def switch_off(self, session: AsyncSession, model) -> int` (15)

### `backend/repository/bot_mode.py` — 50 строк

Режим бота, записанный в единственной строке состояния.

Зависит от: `backend.models`

- `async def _state_row(session: AsyncSession) -> BotState | None` (3)
- `async def read_mode(session: AsyncSession) -> BotMode` (8)
- `async def write_mode(session: AsyncSession, mode: BotMode) -> None` (17)

### `backend/repository/channels.py` — 276 строк

Ведение записей о телеграм-каналах.

Зависит от: `backend.models`, `backend.models.settings`, `backend.payloads`, `backend.repository.blacklist_marks`, `backend.repository.search`, `backend.repository.source_stats`, `backend.repository.vacancies_common`, `backend.repository.vacancies_life`

- `async def list_named_channels(session: AsyncSession, *, ids: list[int] | None=None) -> list[TelegramChannel]` (23)
- `def channel_blacklist_candidates(ch: TelegramChannel) -> list[str]` (14)
- `def _channels_with_counts_query()` (16)
- `async def list_telegram_channels(session: AsyncSession, search: str | None=None) -> list[ChannelWithCount]` (32)
- `async def get_channel_detail(session: AsyncSession, channel_id: int) -> ChannelDetail | None` (13)
- `async def find_channel_by_username(session: AsyncSession, username: str) -> TelegramChannel | None` (17)
- `async def create_channel(session: AsyncSession, username: str, title: str | None, avatar: bytes | None) -> int` (20)
- `async def set_channel_active(session: AsyncSession, channel_id: int, is_active: bool) -> str` (25)
- `async def deactivate_blacklisted_channels(session: AsyncSession) -> int` (10)
- `async def is_channel_blacklisted(session: AsyncSession, channel_id: int) -> bool` (13)
- `async def reset_channel_cursor(session: AsyncSession, channel_id: int) -> bool` (9)
- `async def delete_channel(session: AsyncSession, channel_id: int) -> int | None` (39)

### `backend/repository/companies_card.py` — 277 строк

Ведение записей о компаниях.

Зависит от: `backend.domain.company_names`, `backend.domain.spellings`, `backend.incoming`, `backend.models`, `backend.models.settings`, `backend.payloads`, `backend.repository.blacklist`, `backend.repository.blacklist_marks`, `backend.repository.merging`, `backend.repository.vacancies_life`

- `async def create_company(session: AsyncSession, *, name: str, website: str | None=None, aliases: list[str] | None=None, notes: str | None=None) -> Company` (37)
- `def company_blacklist_candidates(co: Company) -> list[str]` (11)
- `async def get_company_detail(session: AsyncSession, company_id: int) -> 'CompanyDetail | None'` (17)
- `def add_company_spellings(co: Company, incoming: list) -> None` (25)
- `def typed_spellings(aliases) -> list[str]` (14)
- `async def update_company_fields(session: AsyncSession, company_id: int, **fields) -> bool` (44)
- `async def delete_company(session: AsyncSession, company_id: int) -> bool` (22)
- `class _AbsorbedCompany` (7)
- `def _carry_company_to_survivor(survivor: Company, taken: _AbsorbedCompany) -> None` (19)
- `async def merge_company(session: AsyncSession, *, absorbed_id: int, survivor_id: int) -> None` (37)

### `backend/repository/companies_keys.py` — 126 строк

Приведение компании к ключам, по которым её сравнивают.

Зависит от: `backend.domain.company_hosts`, `backend.domain.hosts`, `backend.incoming`

- `def _translit_cyr_to_latin(s: str) -> str` (2)
- `def _without_edge_legal_forms(words: list[str]) -> list[str]` (17)
- `def normalize_company_name(s: str | None) -> str` (17)
- `def signal_host(host: str) -> str` (11)
- `def real_corporate_website(url: str | None) -> str | None` (15)
- `def hosts_compatible(a: str, b: str) -> bool` (6)

### `backend/repository/companies_list.py` — 50 строк

Перечень компаний со счётчиками.

Зависит от: `backend.incoming`, `backend.models`, `backend.payloads`, `backend.repository.companies_card`, `backend.repository.paging`, `backend.repository.search`, `backend.repository.vacancies_common`

- `async def list_companies_with_counts(session: AsyncSession, search: str | None=None, *, limit: int | None=None, offset: int=0) -> tuple[list[CompanyWithCount], bool]` (36)

### `backend/repository/companies_matching.py` — 484 строк ⚠ подошёл к 300

Сведение разобранной из вакансии компании с уже заведённой.

Зависит от: `backend.domain.company_names`, `backend.domain.hosts`, `backend.incoming`, `backend.llm.company`, `backend.models`, `backend.repository.companies_card`, `backend.repository.companies_keys`

- `def _known_spellings(company: Company) -> tuple[str, list[str]]` (13)
- `def _enrich_company_with_parsed(company: Company, parsed_name: str, parsed_website: str | None) -> None` (23)
- `def _accept_company_match(company: Company, parsed_name: str, parsed_website: str | None, decision: dict, stage: str) -> tuple[Company, dict]` (24)
- `def _keep_pre_create_stage(decision: dict) -> None` (10)
- `async def _insert_company(session: AsyncSession, name: str, website: str | None, decision: dict) -> Company | None` (25)
- `async def _company_by_exact_name(session: AsyncSession, name: str) -> Company | None` (12)
- `async def _create_company_row(session: AsyncSession, name: str, website: str | None, decision: dict, seen_ids: set[int]) -> tuple[Company | None, dict]` (44)
- `class _Parsed` (26)
  - `def of(cls, raw_name: str, website: str | None) -> '_Parsed'` (8)
- `def _new_decision() -> dict` (36)
- `async def _companies_in_order(session: AsyncSession) -> list[Company]` (12)
- `def _company_norms(rows) -> list[tuple[Company, str, list[str], str]]` (12)
- `def _same_name(norms, parsed: _Parsed) -> Company | None` (16)
- `def _same_alias(norms, parsed: _Parsed) -> Company | None` (8)
- `def _same_host(norms, parsed: _Parsed) -> Company | None` (15)
- `def _rule_match(norms, parsed: _Parsed)` (23)
- `def _llm_shortlist(norms, parsed: _Parsed) -> list[Company]` (28)
- `def _log_no_match(parsed: _Parsed, shortlist, reasoning: str | None) -> None` (15)
- `async def _llm_arbitrate(lm_client: Any, lm_model: str, parsed: _Parsed, shortlist) -> tuple[Company | None, dict]` (39)
- `async def find_or_create_company(session: AsyncSession, name: str, *, website: str | None=None, lm_client: Any=None, lm_model: str | None=None) -> tuple[Company | None, dict]` (40)

### `backend/repository/hr_card.py` — 404 строк ⚠ подошёл к 300

Одна запись HR: чтение, правка, слияние, удаление.

Зависит от: `backend.domain.telegram_identity`, `backend.incoming`, `backend.models`, `backend.models.settings`, `backend.payloads`, `backend.repository.blacklist`, `backend.repository.blacklist_marks`, `backend.repository.merging`, `backend.repository.messages`, `backend.repository.vacancies_life`

- `async def update_hr_fields(session: AsyncSession, hr_id: int, **fields) -> bool` (38)
- `async def _last_company_of(session: AsyncSession, hr_id: int) -> tuple[int | None, str | None]` (21)
- `async def _unread_count_of(session: AsyncSession, hr_id: int) -> int` (11)
- `async def get_hr_detail(session: AsyncSession, hr_id: int) -> HrDetail | None` (25)
- `def _marks_of(user_id: int | None, username: str | None) -> list[str]` (13)
- `def hr_blacklist_candidates(hr: HR) -> list[str]` (15)
- `async def delete_hr(session: AsyncSession, hr_id: int) -> bool` (27)
- `class _AbsorbedHr` (14)
- `async def _drop_letters_the_survivor_already_has(session: AsyncSession, absorbed_id: int, survivor_id: int) -> int` (31)
- `async def _move_or_drop_chat(session: AsyncSession, absorbed_id: int, survivor_id: int, survivor_has_tg: bool) -> tuple[int, int]` (28)
- `def _carry_to_survivor(survivor: HR, taken: _AbsorbedHr, survivor_has_tg: bool) -> None` (19)
- `async def carry_hr_marks(session: AsyncSession, written_before: list[str], hr: HR) -> None` (34)
- `async def merge_hr(session: AsyncSession, *, absorbed_id: int, survivor_id: int) -> None` (45)

### `backend/repository/hr_identify.py` — 292 строк

Соответствие записи HR данным Telegram.

Зависит от: `backend.models`, `backend.repository.hr_card`

- `async def find_known_hr(session: AsyncSession, telegram_user_id: int, telegram_username: str | None=None) -> HR | None` (40)
- `async def find_last_outgoing_vacancy_id_for_hr(session: AsyncSession, hr_id: int, *, as_of: datetime) -> int | None` (40)
- `async def count_recent_outgoing_with_vacancy_for_hr(session: AsyncSession, hr_id: int, *, window_days: int, other_than: int) -> int` (29)
- `async def resolve_reply_target_vacancy(session: AsyncSession, hr_id: int, reply_to_tg_msg_id: int) -> int | None` (24)
- `def telegram_full_name(user) -> str | None` (3)
- `async def refresh_hr_from_telegram(session: AsyncSession, hr: HR, user, *, avatar: bytes | None) -> None` (39)
- `async def create_hr(session: AsyncSession, *, name: str | None, telegram_username: str | None, telegram_user_id: int | None=None, notes: str | None=None) -> HR` (42)
- `async def find_or_create_hr(session: AsyncSession, user, *, avatar: bytes | None=None) -> tuple[HR, bool]` (23)

### `backend/repository/hr_list.py` — 218 строк

Перечни HR со счётчиками.

Зависит от: `backend.models`, `backend.payloads`, `backend.repository.hr_card`, `backend.repository.hr_identify`, `backend.repository.messages`, `backend.repository.paging`, `backend.repository.search`, `backend.repository.vacancies_common`

- `async def list_hrs_for_backfill(session: AsyncSession) -> list[HR]` (12)
- `def _hr_counts_query(sort_by: str)` (39)
- `async def _last_company_by_hr(session: AsyncSession) -> dict[int, str]` (26)
- `async def _unread_by_hr(session: AsyncSession) -> dict[int, int]` (17)
- `async def list_hr_with_counts(session: AsyncSession, search: str | None=None, *, limit: int | None=None, offset: int=0, sort_by: str='vacancy_count') -> tuple[list[HrWithCount], bool]` (45)
- `async def list_hrs_for_company(session: AsyncSession, company_id: int) -> list[tuple[HR, int]]` (16)
- `async def list_hrs_with_unread(session: AsyncSession) -> list[dict]` (31)

### `backend/repository/mail_account.py` — 66 строк

Почта для откликов письмом: одна строка, пароль шифром.

Зависит от: `adapters.smtp_mail`, `backend.crypto`, `backend.domain.mail_servers`, `backend.log_secrets`, `backend.models`

- `class MailSettings` (5)
- `async def get_mail_account(session: AsyncSession) -> MailAccountConfig | None` (6)
- `async def read_mail_account(session: AsyncSession) -> MailSettings | None` (14)
- `async def save_mail_account(session: AsyncSession, settings: MailSettings) -> None` (9)
- `def _server(address: str | None, host: str | None, port: int | None) -> tuple[str | None, int | None]` (10)

### `backend/repository/merging.py` — 54 строк

Общее у слияния двух записей об одном предмете.

Зависит от: —

- `async def load_merge_pair(session: AsyncSession, model, *, absorbed_id: int, survivor_id: int, subject: str)` (24)
- `def concat_notes(survivor: str | None, absorbed: str | None) -> str | None` (12)

### `backend/repository/messages.py` — 346 строк ⚠ подошёл к 300

Хранение переписки с HR.

Зависит от: `backend.models`, `backend.payloads`, `backend.repository.paging`

- `async def save_incoming_message(session: AsyncSession, incoming: IncomingMessage) -> Message` (24)
- `async def mark_incoming_read(session: AsyncSession, hr_id: int, now: datetime) -> int` (23)
- `async def mark_outgoing_read(session: AsyncSession, hr_id: int, up_to_tg_id: int, now: datetime) -> int` (27)
- `async def overwrite_message_text(session: AsyncSession, hr_id: int, tg_message_id: int, *, is_incoming: bool, text: str) -> int` (38)
- `async def hr_ids_of_live_messages(session: AsyncSession, *where) -> set[int]` (20)
- `async def newest_tg_message_id(session: AsyncSession, hr_id: int) -> int` (18)
- `async def tombstone_messages(session: AsyncSession, *where) -> int` (31)
- `async def find_outgoing_message(session: AsyncSession, hr_id: int, tg_message_id: int) -> Message | None` (17)
- `async def save_outgoing_message(session: AsyncSession, out: OutgoingMessage) -> tuple[Message, bool]` (36)
- `def _older_than(q, before_id: int | None, before_sent_at: datetime | None)` (25)
- `async def list_messages_for_hr(session: AsyncSession, hr_id: int, *, limit: int=50, before_id: int | None=None, before_sent_at: datetime | None=None) -> tuple[list[Message], bool]` (32)
- `async def count_unread_incoming(session: AsyncSession) -> int` (11)

### `backend/repository/paging.py` — 61 строк

Страница ответа репозитория и признак продолжения, который знает режущий.

Зависит от: —

- `def trim_page(rows: list[T], limit: int | None) -> tuple[list[T], bool]` (12)
- `def searched_page(rows: list[T], matches, limit: int | None, offset: int) -> tuple[list[T], bool]` (11)
- `def slice_page(rows: list[T], limit: int | None, offset: int) -> tuple[list[T], bool]` (13)

### `backend/repository/profile.py` — 33 строк

Поля анкеты кандидата.

Зависит от: `backend.models`

- `async def get_profile(session: AsyncSession) -> Profile | None` (3)
- `async def upsert_profile(session: AsyncSession, **fields) -> Profile` (16)

### `backend/repository/profile_block.py` — 106 строк

Сборка текстового блока анкеты для наставления модели.

Зависит от: `backend.domain.tenure`, `backend.repository.profile`, `backend.repository.profile_experience`, `backend.repository.profile_projects`, `backend.repository.profile_skills`

- `def _skills_lines(skills: list) -> list[str]` (12)
- `def _header_lines(profile, experiences: list) -> list[str]` (19)
- `def _record_line(head: str, points: list[str]) -> str` (7)
- `def _experience_lines(experiences: list) -> list[str]` (5)
- `def _project_lines(projects: list) -> list[str]` (3)
- `async def build_profile_block(session: AsyncSession) -> str` (32)

### `backend/repository/profile_cv.py` — 177 строк

Запись анкеты, разобранной моделью из резюме.

Зависит от: `backend.models`, `backend.payloads`, `backend.repository.app_settings`, `backend.repository.profile`, `backend.repository.profile_experience`, `backend.repository.profile_languages`, `backend.repository.profile_projects`, `backend.repository.profile_records`, `backend.repository.profile_skills`

- `async def _wipe_profile(session: AsyncSession) -> None` (12)
- `async def _add_parsed_skills(session: AsyncSession, profile_id: int, skills) -> dict[str, ProfileSkill]` (21)
- `def _parsed_records(model, records, profile_id: int, skill_lookup: dict[str, ProfileSkill]) -> list` (20)
- `async def _answers_to_keep(session: AsyncSession) -> dict` (5)
- `def _answers(p, kept: dict) -> dict` (11)
- `def _new_profile(p, kept: dict) -> Profile` (21)
- `async def save_parsed_cv(session: AsyncSession, parsed: ParsedCv, *, cv_path: str | None=None) -> None` (39)

### `backend/repository/profile_experience.py` — 71 строк

Места работы, названные в анкете кандидата.

Зависит от: `backend.incoming`, `backend.models`, `backend.repository.profile_records`

- `async def wipe_experience(session: AsyncSession) -> None` (3)
- `async def list_experience(session: AsyncSession) -> list[ProfileExperience]` (11)
- `def _date_of(row: dict, key: str, label: str) -> date | None` (9)
- `def _experience_fields(row: dict) -> dict` (21)
- `async def save_experience(session: AsyncSession, rows: list[dict], profile_id: int) -> None` (3)

### `backend/repository/profile_languages.py` — 47 строк

Языки, названные в анкете кандидата.

Зависит от: `backend.models`

- `async def list_profile_languages(session: AsyncSession) -> list[ProfileLanguage]` (8)
- `async def replace_profile_languages(session: AsyncSession, profile_id: int, items: list[tuple[str, str]]) -> None` (25)

### `backend/repository/profile_projects.py` — 51 строк

Проекты из анкеты кандидата.

Зависит от: `backend.incoming`, `backend.models`, `backend.repository.profile_records`

- `async def wipe_projects(session: AsyncSession) -> None` (3)
- `async def list_projects(session: AsyncSession) -> list[ProfileProject]` (15)
- `def _project_fields(row: dict) -> dict` (10)
- `async def save_projects(session: AsyncSession, rows: list[dict], profile_id: int) -> None` (3)

### `backend/repository/profile_records.py` — 117 строк

Запись перечня записей анкеты со стеком — мест работы и проектов.

Зависит от: `backend.domain.skill_names`, `backend.models`, `backend.repository.profile_skills`

- `class RowError(ValueError)` (12)
- `class RecordKind(NamedTuple)` (7)
- `async def wipe_records(session: AsyncSession, kind: RecordKind) -> None` (10)
- `def _stack_by_key(rows: list[ProfileSkill]) -> dict[str, ProfileSkill]` (11)
- `def link_stack(record, names, by_key: dict[str, ProfileSkill]) -> list[str]` (17)
- `def _parsed_rows(rows: list[dict], fields_of: Callable[[dict], dict]) -> list[tuple[dict, dict]]` (14)
- `async def replace_records(session: AsyncSession, rows: list[dict], profile_id: int, kind: RecordKind) -> None` (18)

### `backend/repository/profile_skills.py` — 129 строк

Навыки, названные в анкете кандидата.

Зависит от: `backend.domain.skill_names`, `backend.incoming`, `backend.models`

- `def index_skill_keys(lookup: dict[str, ProfileSkill], names: tuple[str, ...], row: ProfileSkill, where: str) -> None` (19)
- `async def list_skills(session: AsyncSession) -> list[ProfileSkill]` (10)
- `def _skill_columns(row: dict) -> dict | None` (19)
- `def _upsert_skills(session: AsyncSession, rows: list[dict], existing: dict, profile_id: int) -> set[int]` (26)
- `async def _drop_skills(session: AsyncSession, existing: dict, drop_ids: set[int]) -> None` (9)
- `async def save_skills(session: AsyncSession, rows: list[dict], profile_id: int) -> None` (22)

### `backend/repository/search.py` — 31 строк

Отсев списка по строке поиска — тот, что идёт на стороне питона.

Зависит от: —

- `def matches_search(search: str | None, *values: object) -> bool` (17)

### `backend/repository/source_stats.py` — 67 строк

Числа карточки источника вакансий — канала или агрегатора.

Зависит от: `backend.domain.funnel`, `backend.models`, `backend.payloads`, `backend.repository.vacancies_common`

- `async def _vacancies_per_day(session: AsyncSession, from_source) -> float` (16)
- `async def source_stats(session: AsyncSession, from_source) -> SourceStats` (34)

### `backend/repository/stats_common.py` — 83 строк

Кирпичи, из которых обе половины экрана статистики собирают свои числа.

Зависит от: `backend.models`, `backend.repository.vacancies_common`

- `def status_cond(statuses)` (9)
- `def first_transition_subq(statuses)` (13)
- `def parsed_in_window(since) -> list` (11)
- `def stats_period_since(period: str) -> datetime | None` (25)

### `backend/repository/stats_kpi.py` — 118 строк

Верхняя строка экрана статистики: пять счётчиков и дельта у каждого.

Зависит от: `backend.domain.funnel`, `backend.models`, `backend.repository.stats_common`, `backend.repository.vacancies_common`

- `async def _ever_in(session: AsyncSession, statuses) -> int` (12)
- `async def _first_in_period(session: AsyncSession, statuses, since: datetime) -> int` (10)
- `async def _kpi_totals(session: AsyncSession) -> dict` (16)
- `async def _kpi_deltas(session: AsyncSession, since: datetime | None) -> dict` (31)
- `async def get_stats_kpi(session: AsyncSession, *, period: str) -> dict` (23)

### `backend/repository/stats_pipeline.py` — 202 строк

Воронка по источникам — каналам и агрегаторам — для экрана статистики.

Зависит от: `backend.domain.funnel`, `backend.domain.verdict`, `backend.models`, `backend.models.settings`, `backend.repository.stats_common`, `backend.repository.stats_rows`, `backend.repository.vacancies_common`

- `def _trash_predicates()` (26)
- `async def _ingest_by_source(session: AsyncSession, since) -> list` (24)
- `async def _trash_events_by_source(session: AsyncSession, since) -> dict[SourceKey, int]` (16)
- `async def _first_in_period_by_source(session: AsyncSession, statuses, since) -> dict[SourceKey, set[int]]` (21)
- `async def _funnel_by_source(session: AsyncSession, since) -> dict[str, dict[SourceKey, set[int]]]` (19)
- `async def _sources_without_ingest(session: AsyncSession, missing: set[SourceKey]) -> dict[SourceKey, dict]` (27)
- `async def get_stats_channels_pipeline(session: AsyncSession, *, period: str) -> dict` (30)

### `backend/repository/stats_responses.py` — 139 строк

Скорость ответа HR: сколько ждали, кто не ответил и в какие дни отвечают.

Зависит от: `backend.domain.funnel`, `backend.models`, `backend.repository.stats_common`, `backend.repository.vacancies_common`

- `async def _applied_in_period(session: AsyncSession, since: datetime | None) -> dict[int, datetime]` (23)
- `async def _first_response_at(session: AsyncSession, applied_map: dict[int, datetime]) -> dict[int, datetime]` (32)
- `def _local_weekday(stamp: datetime) -> int` (8)
- `def _weekdays_and_waits(applied_map: dict[int, datetime], first_resp_by_vid: dict[int, datetime]) -> tuple[list[int], list[float]]` (17)
- `async def get_stats_hr_responses(session: AsyncSession, *, period: str) -> dict` (33)

### `backend/repository/stats_rows.py` — 84 строк

Строка таблицы источников на экране статистики: кто прислал, сколько, куда дошло.

Зависит от: `backend.models.settings`

- `def source_item(key: SourceKey, title: str | None, username: str | None, counts: tuple[int, int, int]=(0, 0, 0)) -> dict` (32)
- `def pipeline_row(key: SourceKey, item: dict, trash_events: int, funnel) -> dict` (42)
  - `def share(stage: str) -> float | None` (4)

### `backend/repository/stats_skills.py` — 94 строк

Частота технологий в объявлениях за выбранный срок.

Зависит от: `backend.domain.scoring`, `backend.domain.skill_names`, `backend.models`, `backend.repository.profile_skills`, `backend.repository.stats_common`

- `def _count_stack_tags(stacks) -> tuple[dict[str, int], dict[str, str]]` (30)
- `def _skill_items(counts: dict[str, int], canon_by_key: dict[str, str], profile_set, min_count: int) -> list[dict]` (18)
- `async def get_stats_skills(session: AsyncSession, *, period: str, limit: int=27, min_count: int=2) -> dict` (30)

### `backend/repository/stats_statuses.py` — 31 строк

Разбивка вакансий по нынешним статусам за выбранный срок.

Зависит от: `backend.repository.stats_common`, `backend.repository.vacancies_activity`, `backend.repository.vacancies_common`

- `async def get_stats_status_breakdown(session: AsyncSession, *, period: str) -> dict` (22)

### `backend/repository/vacancies_activity.py` — 165 строк

Отметка последней жизни вакансии — из чего складывается и как её спросить.

Зависит от: `backend.models`

- `def _greatest_pair(a, b)` (4)
- `def _greatest(*cols)` (5)
- `def last_incoming_subq(ids: list[int] | None=None)` (22)
- `def entered_current_status_at()` (36)
- `def last_human_touch_at()` (25)
- `def activity_aggs(ids: list[int] | None=None) -> tuple` (24)
- `def activity_ts(aggs: tuple)` (7)
- `def join_activity(stmt, aggs: tuple)` (9)

### `backend/repository/vacancies_card.py` — 229 строк

Поля одной вакансии.

Зависит от: `backend.models`, `backend.payloads`, `backend.repository.applications`, `backend.repository.vacancies_life`, `backend.repository.vacancy_contacts`

- `async def _newest_first(session: AsyncSession, model, stamp, vacancy_id: int) -> list` (20)
- `async def get_vacancy_detail(session: AsyncSession, vacancy_id: int) -> VacancyDetail | None` (31)
- `async def update_vacancy_notes(session: AsyncSession, vacancy_id: int, notes: str | None) -> Vacancy | None` (30)
- `class _Link` (16)
- `async def _link_name(session: AsyncSession, link: _Link, row_id: int | None) -> str | None` (13)
- `async def _relink(session: AsyncSession, vacancy_id: int, new_id: int | None, link: _Link) -> bool` (40)
- `async def set_vacancy_hr(session: AsyncSession, vacancy_id: int, hr_id: int | None) -> bool` (5)
- `async def set_vacancy_company(session: AsyncSession, vacancy_id: int, company_id: int | None) -> bool` (5)

### `backend/repository/vacancies_common.py` — 109 строк

Чтение вакансий, общее для всех экранов.

Зависит от: `backend.models`, `backend.models.settings`

- `def by_vacancy_count(label)` (13)
- `def with_vacancy_counts(subject, link, label)` (12)
- `def counted_vacancies(subject, link)` (12)
- `async def count_by_status(session: AsyncSession, *conditions) -> dict[VacancyStatus, int]` (21)

### `backend/repository/vacancies_ghosting.py` — 99 строк

Вакансии, о которых замолчали: срок тишины и гашение по нему.

Зависит от: `backend.domain.transitions`, `backend.models`, `backend.repository.vacancies_activity`, `backend.repository.vacancy_status`, `backend.telegram_time`

- `async def _silence_candidates(session: AsyncSession)` (29)
- `def _last_activity(vacancy: Vacancy, last_msg_at, entered_at, touched_at)` (10)
- `async def mark_ghosted_vacancies(session: AsyncSession, *, timeout_days: int) -> list[int]` (27)

### `backend/repository/vacancies_life.py` — 177 строк

Что случается с вакансией после того, как её завели, кроме смены статуса.

Зависит от: `backend.models`

- `async def repoint_vacancies(session: AsyncSession, column, *, absorbed_id: int, survivor_id: int | None) -> int` (23)
- `async def record_trash_event(session: AsyncSession, vacancy: Vacancy | None, reason: str | None) -> None` (20)
- `async def source_trashed(session: AsyncSession, aggregator_id: int, key: str) -> bool` (7)
- `async def source_seen(session: AsyncSession, aggregator_id: int, key: str) -> bool` (6)
- `async def _trash_noted(session: AsyncSession, mark: TrashEvent) -> bool` (11)
- `async def _marked(session: AsyncSession, *same) -> bool` (2)
- `async def delete_vacancy(session: AsyncSession, vacancy_id: int) -> bool` (41)
- `async def add_vacancy_event(session: AsyncSession, vacancy_id: int, kind: str, payload: dict | None=None) -> VacancyEvent` (19)

### `backend/repository/vacancies_list.py` — 459 строк ⚠ подошёл к 300

Отбор вакансий для списка на экране.

Зависит от: `backend.domain.spellings`, `backend.models`, `backend.payloads`, `backend.repository.paging`, `backend.repository.vacancies_activity`, `backend.repository.vacancies_card`, `backend.repository.vacancies_common`

- `def _order_for(sort: str, freshness)` (34)
- `def _like_anywhere(text: str) -> str` (18)
- `def _search_clauses(search: str | None) -> tuple[list, set[str]]` (31)
- `def _choice_clauses(f: VacancyFilter) -> tuple[list, set[str]]` (41)
- `def _salary_clauses(f: VacancyFilter) -> list` (34)
- `def _range_clauses(f: VacancyFilter, freshness) -> list` (13)
- `def _column_clauses(f: VacancyFilter) -> list` (20)
- `def _where_and_joins(f: VacancyFilter, freshness) -> tuple[list, set[str]]` (15)
- `async def list_vacancies(session: AsyncSession, filters: VacancyFilter) -> tuple[list[Vacancy], bool]` (21)
- `def _listing_stmt(f: VacancyFilter)` (26)
- `async def _channel_options(session: AsyncSession) -> list[str]` (12)
- `async def _company_options(session: AsyncSession) -> list[str]` (34)
- `async def list_vacancy_filter_options(session: AsyncSession) -> dict[str, list[str]]` (16)
- `async def list_vacancy_last_activity(session: AsyncSession, vacancy_ids: list[int]) -> dict[int, datetime]` (25)

### `backend/repository/vacancies_mini.py` — 143 строк

Короткие списки вакансий для карточек других предметов.

Зависит от: `backend.models`, `backend.repository.hr_card`, `backend.repository.paging`, `backend.repository.vacancies_common`

- `async def _list_linked(session: AsyncSession, linked_to) -> list[Vacancy]` (21)
- `async def list_vacancies_for_hr(session: AsyncSession, hr_id: int) -> list[Vacancy]` (8)
- `async def list_vacancies_for_company(session: AsyncSession, company_id: int) -> list[Vacancy]` (5)
- `def _from_source(kind: str, source_id: int)` (2)
- `async def count_vacancies_from(session: AsyncSession, kind: str, source_id: int) -> int` (12)
- `async def list_vacancies_from(session: AsyncSession, kind: str, source_id: int, *, limit: int=50, offset: int=0) -> tuple[list[Vacancy], bool]` (40)

### `backend/repository/vacancies_new.py` — 71 строк

Заведение вакансии руками — набранной в окне, а не найденной в канале.

Зависит от: `backend.domain.salary`, `backend.domain.scoring`, `backend.domain.stack`, `backend.models`, `backend.repository.profile_skills`, `backend.repository.vacancies_life`

- `async def create_vacancy(session: AsyncSession, fields: dict) -> int` (39)

### `backend/repository/vacancy_brief.py` — 39 строк

Вакансия текстом для агента.

Зависит от: `backend.llm.external`, `backend.models`, `backend.repository.vacancy_contacts`

- `async def describe_vacancy(session: AsyncSession, vacancy_id: int) -> str | None` (20)
- `async def _source(session: AsyncSession, vacancy: Vacancy) -> str` (8)

### `backend/repository/vacancy_contacts.py` — 95 строк

Контакты вакансии — всё, чем она указывает вовне, кроме Telegram-HR.

Зависит от: `backend.domain.contact_keys`, `backend.models`

- `async def replace_parsed_contacts(session: AsyncSession, vacancy_id: int, values: list[str]) -> None` (18)
- `async def add_contact(session: AsyncSession, vacancy_id: int, value: str, added_by: ContactAddedBy) -> None` (21)
- `async def _contact_row(session: AsyncSession, vacancy_id: int, key: str) -> VacancyContact | None` (9)
- `async def list_contacts(session: AsyncSession, vacancy_id: int) -> list[VacancyContact]` (7)
- `async def contact_values(session: AsyncSession, vacancy_id: int) -> list[str]` (3)
- `async def vacancy_addresses(session: AsyncSession, vacancy_id: int) -> list[str]` (4)
- `async def delete_contact(session: AsyncSession, contact_id: int) -> int | None` (8)

### `backend/repository/vacancy_status.py` — 387 строк ⚠ подошёл к 300

Смена статуса вакансии: решение, запись, история.

Зависит от: `backend.domain.sentence`, `backend.domain.transitions`, `backend.models`, `backend.payloads`

- `def _ensure_trailing_period(s: str | None) -> str | None` (3)
- `class _Signature` (13)
- `def _move_status(vacancy: Vacancy, new_status: VacancyStatus, sign: _Signature) -> VacancyStatusHistory` (34)
- `async def mark_vacancy_applied(session: AsyncSession, vacancy_id: int, explanation: str | None) -> bool` (12)
- `async def mark_vacancy_unfit(session: AsyncSession, vacancy_id: int, reason: str) -> None` (11)
- `class _Move` (5)
- `async def _move_by_application(session: AsyncSession, vacancy_id: int, move: _Move, explanation: str | None) -> bool` (9)
- `async def last_status_history_id(session: AsyncSession, vacancy_id: int) -> int | None` (13)
- `async def record_rerun(session: AsyncSession, vacancy_id: int, previous: VacancyStatus, last_history: int | None) -> None` (38)
- `def _log_status_change(vacancy_id: int, previous, new_status, detail: str) -> None` (14)
- `def _log_manual_change(history: VacancyStatusHistory, vacancy_id: int, previous, new_status) -> None` (19)
- `async def change_vacancy_status(session: AsyncSession, vacancy_id: int, new_status: VacancyStatus, explanation: str | None) -> VacancyStatusHistory | None` (36)
- `async def update_status_history_explanation(session: AsyncSession, history_id: int, explanation: str | None) -> VacancyStatusHistory | None` (18)
- `def _log_blocked_verdict(vacancy_id: int, previous, classification: Classification, message_id: int) -> None` (19)
- `async def apply_classification(session: AsyncSession, vacancy_id: int, message_id: int, classification: Classification) -> None` (24)
- `def apply_silence(session: AsyncSession, vacancy: Vacancy, timeout_days: int) -> None` (23)
- `def apply_parse_outcome(vacancy: Vacancy, new_status: VacancyStatus) -> None` (18)

### `backend/runtime_settings.py` — 440 строк ⚠ подошёл к 300

Runtime settings layer.

Зависит от: `adapters`, `backend.crypto`, `backend.incoming`, `backend.models`, `backend.provider_config`, `backend.repository.app_settings`, `backend.tg_credentials`

- `async def _llm_row(session: AsyncSession, kind: LlmConfigKind) -> LlmConfig | None` (5)
- `class RuntimeSettings` (329)
  - `async def load(cls, session_factory: async_sessionmaker[AsyncSession]) -> 'RuntimeSettings'` (6)
  - `async def reload(self) -> None` (22)
  - `def tg(self) -> TgAccountConfig | None` (2)
  - `def has_tg_session(self) -> bool` (10)
  - `def chat(self) -> LlmProviderConfig | None` (2)
  - `def embed(self) -> LlmProviderConfig | None` (2)
  - `def scoring_threshold(self) -> int` (2)
  - `def poll_interval_sec(self) -> int` (2)
  - `def backfill_limit(self) -> int` (3)
  - `def aggregator_backfill_limit(self) -> int` (4)
  - `def channels_enabled(self) -> bool` (3)
  - `def aggregators_enabled(self) -> bool` (3)
  - `def show_browser(self) -> bool` (3)
  - `def letter_writer(self) -> str` (9)
  - `def dedup_cosine_threshold(self) -> float` (8)
  - `def dm_backfill_limit(self) -> int` (6)
  - `def cv_path(self) -> str` (2)
  - `def wizard_completed(self) -> bool` (2)
  - `def send_locked(self) -> bool` (7)
  - `def auto_apply(self) -> bool` (3)
  - `def flood_wait_until_ts(self) -> float` (2)
  - `def _app_bool(self, key: str) -> bool` (9)
  - `def _app_float(self, key: str) -> float` (17)
    - `def read(raw: str) -> float | None` (6)
  - `def _app_int(self, key: str, *, minimum: int | None=None) -> int` (15)
    - `def read(raw: str) -> int | None` (6)
  - `def _app_number(self, key: str, read: Callable, kind: type)` (17)
  - `def _app_value(self, key: str) -> str` (8)
  - `async def set_tg(self, creds: TgAccountConfig) -> None` (20)
  - `async def clear_tg(self) -> None` (12)
  - `async def set_chat(self, *, base_url: str, api_key: str, model: str) -> None` (4)
  - `async def set_embed(self, *, base_url: str, api_key: str, model: str) -> None` (4)
  - `async def _set_llm(self, kind: LlmConfigKind, base_url: str, api_key: str, model: str) -> None` (32)
  - `async def set_app(self, key: str, value: str | bool | int) -> None` (21)
  - `async def mark_wizard_completed(self) -> None` (3)
- `def _from_llm_row(row: LlmConfig) -> LlmProviderConfig | None` (13)

### `backend/single_instance.py` — 127 строк

Замок, которым запущенная копия приложения не пускает вторую.

Зависит от: —

- `def release_the_lock() -> None` (15)
- `def _take_the_lock(fd: int) -> bool | None` (36)
- `def hold_the_only_copy(lock_path: Path | str)` (48)

### `backend/task_stop.py` — 15 строк

Погасить задачу и дождаться её конца.

Зависит от: —

- `async def put_out(task: asyncio.Task) -> None` (10)

### `backend/telegram_login.py` — 332 строк ⚠ подошёл к 300

Вход в Telegram по коду: четыре шага и состояние между ними.

Зависит от: `backend.tg_credentials`

- `class LoginStep` (5)
- `async def _safe_disconnect(client) -> None` (14)
- `async def username_of(client) -> str | None` (14)
- `def _flood_wait_refusal(e, before: str) -> str` (13)
- `def _humanize_duration(seconds: int) -> str` (9)
- `class TelegramLogin` (234)
  - `def awaiting_code(self) -> bool` (7)
  - `def awaiting_password(self) -> bool` (8)
  - `def active(self) -> bool` (3)
  - `async def forget(self) -> None` (10)
  - `def _new_client(self, api_id: int, api_hash: str, phone: str) -> PyrogramClient` (14)
  - `async def send_code(self, api_id: int, api_hash: str, phone: str) -> LoginStep` (36)
  - `async def confirm_code(self, code: str) -> LoginStep` (24)
  - `async def confirm_password(self, password: str) -> LoginStep` (25)
  - `def _drop(self) -> None` (10)
  - `async def _failed(self, client, message: str) -> LoginStep` (5)
  - `async def _save(self) -> LoginStep` (48)

### `backend/telegram_lookup.py` — 115 строк

Что берётся у Telegram по дороге, а не ради самого похода.

Зависит от: `backend.domain.telegram_identity`

- `async def read_channel_metadata(client, chat, *, current_avatar: bytes | None=None) -> tuple[str | None, bytes | None]` (20)
- `async def _quietly(what: str, asking)` (24)
- `def say_flood_wait(log: logging.Logger, what: str, error) -> None` (8)
- `async def fetch_telegram_avatar(client, entity) -> bytes | None` (21)
- `async def resolve_hr_telegram(client, hr_contact: str)` (12)

### `backend/telegram_time.py` — 43 строк

Время в той шкале, в какой приложение пишет всё остальное.

Зависит от: —

- `def tg_moment(dt: datetime | None) -> datetime | None` (15)
- `def utc_now() -> datetime` (10)

### `backend/tg_credentials.py` — 101 строк

Учётная запись Telegram: от строки в базе до следа в журнале.

Зависит от: `backend.crypto`, `backend.models`

- `def mask_phone(phone: str | None) -> str` (10)
- `class TgAccountConfig` (7)
- `def log_tg_updated(api_id: int, phone: str, password: str, session_string: str | None) -> None` (16)
- `async def tg_row(session: AsyncSession) -> TgAccount | None` (3)
- `def from_tg_row(row: TgAccount) -> TgAccountConfig | None` (24)
- `def fill_tg_row(row: TgAccount, creds: TgAccountConfig) -> None` (15)

### `backend/update_download.py` — 97 строк

Скачивание обновления: файл остаётся на диске, только если сошёлся с релизом.

Зависит от: `adapters`, `adapters.github_release`, `backend.app_version`

- `def new_exe_path() -> Path` (5)
- `async def newer_release() -> Release | None` (6)
- `async def download_update(target: Path, report: Callable[[int, int], None]) -> UpdateOutcome` (21)
- `async def _fetch(release: Release, target: Path, report: Callable[[int, int], None]) -> str` (23)
- `def remove_leftover(path: Path) -> None` (8)

### `backend/updater.py` — 124 строк

Подмена exe скачанным обновлением — копией приложения в режиме `--update`.

Зависит от: `backend.update_download`

- `def updater_copy() -> Path` (4)
- `def launch_updater(new: Path) -> None` (10)
- `def run(args: list[str]) -> int` (20)
- `def clear_leftovers() -> None` (5)
- `def _start(args: list[str]) -> None` (6)
- `def _log_to_own_file() -> None` (6)
- `def _wait_for_exit(pid: int) -> None` (9)
- `def _replace(new: Path, exe: Path) -> bool` (14)

### `backend/wipe.py` — 103 строк

Снос всего, что приложение записало на диск.

Зависит от: `backend.single_instance`, `config`

- `def _close_log_files() -> list[str]` (20)
- `def _remove_the_data() -> list[str]` (27)
- `async def wipe_all(engine) -> list[str]` (28)

## client — 51 модулей

### `client/bridge/__init__.py` — 23 строк

Поверхность моста, доступная окну: дерево доменов и мотор под ним.

Зависит от: `client.bridge.api`, `client.bridge.runner`

Отдаёт наружу: `Api`, `AsyncRunner`


### `client/bridge/aggregators.py` — 189 строк

Экран «Агрегаторы»: перечень, заведение, удаление, включение, вход и обход.

Зависит от: `backend.agent.availability`, `backend.flows.aggregator_name`, `backend.repository`, `client.bridge.answer`, `client.bridge.hub`, `client.bridge.mark`, `client.bridge.page`, `client.bridge.refusals`, `client.bridge.source_page`, `client.bridge.source_switch`, `client.bridge.wire`

- `class Aggregators` (146)
  - `def list(self, payload: dict | None=None) -> dict` (17)
    - `async def run() -> dict` (7)
  - `def detail(self, aggregator_id: int) -> dict` (15)
    - `async def run() -> dict` (10)
  - `def vacancies(self, payload: dict) -> dict` (3)
  - `def set_all_active(self, payload: dict) -> dict` (3)
  - `def block(self, aggregator_id: int) -> dict` (7)
  - `def unblock(self, aggregator_id: int) -> dict` (3)
  - `def create(self, payload: dict | None=None) -> dict` (18)
    - `async def run() -> dict` (7)
  - `def delete(self, payload: dict | None=None) -> dict` (22)
    - `async def run() -> dict` (11)
  - `def set_active(self, payload: dict | None=None) -> dict` (22)
    - `async def run() -> dict` (11)
  - `def login(self, aggregator_id: int) -> dict` (3)
  - `def run_now(self, aggregator_id: int) -> dict` (3)
  - `def _launch(self, aggregator_id: int, action: str, done: str, refusals: dict) -> dict` (13)
    - `def start(bot)` (3)
- `def _refuse_deletion(block: str | None) -> None` (4)

### `client/bridge/answer.py` — 251 строк

Единый конверт ответа окну — от исхода работы до ответа зовущему.

Зависит от: `backend.incoming`, `client.bridge.events`, `client.bridge.payload`, `client.bridge.refusals`, `client.bridge.runner`

- `class Denied(Exception)` (12)
- `def denied(reason: str, **extra: Any) -> dict` (8)
- `def bad_fields(where: str, error: Exception, **extra: Any) -> dict` (20)
- `def asked_id(payload: dict, key: str, slot: str) -> tuple` (15)
- `def read_toggle(payload: dict, id_key: str, flag_key: str, slot: str) -> tuple` (27)
- `def reply(runner: AsyncRunner, coro: Coroutine[Any, Any, Any]) -> dict` (33)
- `def launched(hub, work: Callable[[], Coroutine[Any, Any, str]], refusals: dict[str, str], done: str, **started: Any) -> dict` (39)
  - `async def report() -> None` (10)
- `def launched_on_bot(hub, start: Callable[[Any], Coroutine[Any, Any, str]], refusals: dict[str, str], done: str, **started: Any) -> dict` (14)
- `def finished(events: Events, status: str, refusals: dict[str, str], done: str) -> None` (19)

### `client/bridge/api.py` — 41 строк

Поверхность окна: домены, собранные в одно дерево.

Зависит от: `client.bridge.aggregators`, `client.bridge.blacklist`, `client.bridge.channels`, `client.bridge.companies`, `client.bridge.hr`, `client.bridge.hub`, `client.bridge.profile`, `client.bridge.settings`, `client.bridge.stats`, `client.bridge.system`, `client.bridge.vacancies`, `client.bridge.wizard`

- `class Api` (15)

### `client/bridge/app_update.py` — 72 строк

Обновление приложения из релизов GitHub: какая версия запущена и есть ли новее.

Зависит от: `backend.app_version`, `backend.update_download`, `client.bridge.answer`, `client.bridge.refusals`

- `class AppUpdate` (49)
  - `def version(self) -> dict` (7)
  - `def check_update(self) -> dict` (19)
    - `async def run() -> dict` (9)
  - `def update(self) -> dict` (10)
  - `async def _download_then_hand_over(self, bot) -> str` (7)

### `client/bridge/blacklist.py` — 162 строк

Экран «Контакты / Чёрный список»: чем окно правит отсев.

Зависит от: `backend.models`, `backend.repository`, `client.bridge.answer`, `client.bridge.hub`, `client.bridge.refusals`, `client.bridge.wire`

- `class Blacklist` (150)
  - `def list(self) -> dict` (12)
    - `async def run() -> dict` (4)
  - `def candidates(self, kind: str) -> dict` (15)
    - `async def run() -> dict` (6)
  - `def create(self, payload: dict | None=None) -> dict` (36)
    - `async def run() -> dict` (14)
  - `def update(self, payload: dict) -> dict` (36)
    - `async def run() -> dict` (16)
  - `def delete(self, blacklist_id: int) -> dict` (15)
    - `async def run() -> dict` (10)
  - `def set_active(self, payload: dict) -> dict` (25)
    - `async def run() -> dict` (12)

### `client/bridge/bot_stop.py` — 90 строк

Остановка бота: попросить и дождаться.

Зависит от: —

- `def detach_bot(hub) -> tuple[object | None, Future | None]` (10)
- `async def stop_bot(bot, bot_task: Future | None, asking: Callable[[], Awaitable[None]] | None=None, timeout: float=STOP_TIMEOUT_S) -> bool` (41)

### `client/bridge/cards.py` — 273 строк

Карточка контакта: то, что человек и компания делают одним и тем же телом.

Зависит от: `backend.incoming`, `client.bridge.answer`, `client.bridge.page`, `client.bridge.pickers`, `client.bridge.refusals`, `client.bridge.wire`

- `class CardSubject` (24)
- `def listed(hub, subject: CardSubject, payload: dict | None) -> dict` (29)
  - `async def run() -> dict` (14)
- `def vacancies_of(hub, subject: CardSubject, payload: dict) -> dict` (17)
  - `async def run() -> dict` (7)
- `def merge_candidates(hub, subject: CardSubject, payload: dict) -> dict` (13)
  - `async def run() -> dict` (3)
- `def merge_into(hub, subject: CardSubject, payload: dict) -> dict` (45)
  - `async def run() -> dict` (29)
- `def delete_card(hub, subject: CardSubject, entity_id: int) -> dict` (6)
- `def create_card(hub, subject: CardSubject, payload: dict) -> dict` (21)
  - `async def run() -> dict` (6)
- `async def created_or_taken(session, create: Callable, taken: str, **echo) -> int` (12)
- `async def _deleting(hub, subject: CardSubject, entity_id: int) -> dict` (12)
- `def asked_update(payload: dict, subject: CardSubject) -> tuple` (17)
- `def _tell(hub, subject: CardSubject) -> None` (9)

### `client/bridge/channel_actions.py` — 196 строк

Что окно делает с каналом: опрос, курсор, чёрный список, состав.

Зависит от: `backend.domain.telegram_identity`, `backend.repository`, `client.bridge.answer`, `client.bridge.mark`, `client.bridge.refusals`, `client.bridge.source_switch`

- `class ChannelActions` (179)
  - `def block(self, channel_id: int) -> dict` (10)
  - `def unblock(self, channel_id: int) -> dict` (8)
  - `def poll_now(self, channel_id: int) -> dict` (15)
  - `def reset_cursor(self, channel_id: int) -> dict` (22)
    - `async def run() -> dict` (9)
  - `def delete(self, channel_id: int) -> dict` (25)
    - `async def run() -> dict` (9)
  - `def create(self, payload: dict | None=None) -> dict` (46)
    - `async def run() -> dict` (23)
  - `def set_active(self, payload: dict) -> dict` (15)
  - `async def _switched(self, channel_id: int, is_active: bool) -> dict` (15)
  - `def set_all_active(self, payload: dict) -> dict` (3)

### `client/bridge/channels.py` — 77 строк

Экран «Контакты / Каналы»: список каналов и их карточка.

Зависит от: `backend.incoming`, `backend.repository`, `client.bridge.answer`, `client.bridge.channel_actions`, `client.bridge.hub`, `client.bridge.refusals`, `client.bridge.source_page`, `client.bridge.wire`

- `class Channels(ChannelActions)` (63)
  - `def list(self, payload: dict | None=None) -> dict` (29)
    - `async def run() -> dict` (16)
  - `def detail(self, channel_id: int) -> dict` (16)
    - `async def run() -> dict` (6)
  - `def vacancies(self, payload: dict) -> dict` (3)

### `client/bridge/choices.py` — 42 строк

Просеивание значений, пришедших из окна, по известному набору.

Зависит от: `backend.domain.taxonomy`

- `def _filter_languages(items) -> list[tuple[str, str]]` (35)

### `client/bridge/companies.py` — 259 строк

Компания как запись в контактах: найти, показать, поправить, убрать.

Зависит от: `backend.repository`, `client.bridge.answer`, `client.bridge.cards`, `client.bridge.form_payloads`, `client.bridge.hub`, `client.bridge.mark`, `client.bridge.pickers`, `client.bridge.refusals`, `client.bridge.wire`

- `async def create_company_row(session, fields: dict, **echo) -> int` (25)
- `class Companies` (173)
  - `def list(self, payload: dict | None=None) -> dict` (6)
  - `def detail(self, company_id: int) -> dict` (22)
    - `async def run() -> dict` (13)
  - `def vacancies(self, payload: dict) -> dict` (6)
  - `def people(self, company_id: int) -> dict` (16)
    - `async def run() -> dict` (7)
  - `def merge_picker(self, payload: dict) -> dict` (7)
  - `def merge(self, payload: dict) -> dict` (8)
  - `def create(self, payload: dict) -> dict` (7)
  - `def update(self, payload: dict) -> dict` (19)
  - `async def _updated(self, company_id: int, kwargs: dict) -> dict` (36)
  - `def delete(self, company_id: int) -> dict` (3)
  - `def block(self, company_id: int) -> dict` (12)
  - `def unblock(self, company_id: int) -> dict` (9)

### `client/bridge/cv.py` — 147 строк

Файл резюме, на который смотрит окно: запомнить путь, открыть, разобрать.

Зависит от: `adapters`, `adapters.cv_text`, `backend.llm`, `backend.provider_config`, `backend.repository.app_settings`, `backend.repository.profile_cv`, `client.bridge.answer`, `client.bridge.cv_file`, `client.bridge.desktop`, `client.bridge.refusals`

- `class Cv` (95)
  - `def pick(self) -> dict` (16)
  - `def _replace(self, payload: dict) -> dict` (22)
    - `async def run() -> dict` (3)
  - `def parse_cv(self) -> dict` (24)
  - `def open(self) -> dict` (15)
- `async def _parse_into_profile(hub, path: Path, chat: LlmProviderConfig) -> str` (25)

### `client/bridge/cv_file.py` — 16 строк

Что можно узнать о файле резюме с диска.

Зависит от: —

- `def _stat_cv(cv_path: str) -> dict | None` (9)

### `client/bridge/desktop.py` — 210 строк

Просьбы окна к рабочему столу: открыть названное системой, выбрать файл диалогом.

Зависит от: `client.bridge.answer`, `client.bridge.media`, `client.bridge.refusals`

- `def _show_in_folder(target) -> bool` (20)
- `def _scheme_of(url: str) -> str` (7)
- `def open_in_system(target: str) -> bool` (20)
- `class Desktop` (67)
  - `def open_url(self, url: str) -> dict` (28)
  - `def open_attachment(self, url: str) -> dict` (25)
- `def closed_dialog() -> dict` (3)
- `def file_filter(label: str, suffixes) -> str` (3)
- `def chosen_path(window, *file_types: str) -> str | None` (10)

### `client/bridge/events.py` — 155 строк

Живые события окна: копит случившееся с номерами и отдаёт всё новее названного.

Зависит от: —

- `class Events` (83)
  - `def add(self, kind: str, payload: dict | None=None) -> None` (10)
  - `async def take(self, after: int | None, timeout: float=WAIT_SECONDS) -> dict` (38)
  - `def close(self) -> None` (6)
  - `def _since(self, after: int) -> dict` (15)
- `def _wake(waiters: list[tuple[asyncio.AbstractEventLoop, asyncio.Future]]) -> None` (6)
- `def _finish(waiter: asyncio.Future) -> None` (3)

### `client/bridge/form_payloads.py` — 165 строк

Поля записи, прочитанные из нагрузки форм окна.

Зависит от: `backend.domain.salary`, `backend.domain.taxonomy`, `backend.domain.telegram_identity`, `backend.incoming`

- `def _comma_list(raw) -> list[str]` (12)
- `def read_company_spellings(raw) -> list[str]` (12)
- `def read_new_company_fields(payload: dict) -> dict` (16)
- `def hr_is_identified(fields: dict) -> bool` (11)
- `def read_new_hr_fields(payload: dict) -> dict` (31)
- `def _slashed(country: str | None, city: str | None) -> str | None` (10)
- `def read_new_vacancy_fields(payload: dict) -> dict` (39)

### `client/bridge/hr.py` — 229 строк

Экран «Контакты / HR»: список людей, их карточка и правки в ней.

Зависит от: `backend.repository`, `client.bridge.answer`, `client.bridge.cards`, `client.bridge.form_payloads`, `client.bridge.hr_chat`, `client.bridge.hub`, `client.bridge.mark`, `client.bridge.media`, `client.bridge.pickers`, `client.bridge.refusals`

- `async def create_hr_row(session, fields: dict, **echo) -> int` (19)
- `class Hr(HrChat)` (152)
  - `def list(self, payload: dict | None=None) -> dict` (7)
  - `def detail(self, hr_id: int) -> dict` (26)
    - `async def run() -> dict` (17)
  - `def vacancies(self, payload: dict) -> dict` (6)
  - `def merge_picker(self, payload: dict) -> dict` (7)
  - `def merge(self, payload: dict) -> dict` (12)
  - `def delete(self, hr_id: int) -> dict` (3)
  - `def block(self, hr_id: int) -> dict` (15)
  - `def unblock(self, hr_id: int) -> dict` (9)
  - `def update(self, payload: dict) -> dict` (32)
    - `async def run() -> dict` (14)
  - `def create(self, payload: dict) -> dict` (8)

### `client/bridge/hr_chat.py` — 187 строк

Переписка с человеком: страница сообщений, отправка, прочтение.

Зависит от: `backend.bot.chat`, `backend.incoming`, `backend.repository`, `client.bridge.answer`, `client.bridge.desktop`, `client.bridge.page`, `client.bridge.refusals`, `client.bridge.wire`

- `class HrChat` (168)
  - `def messages(self, payload: dict) -> dict` (30)
  - `async def _paged(self, asked: dict, before_sent_at, limit: int) -> dict` (17)
  - `async def _sent(self, sending, hr_id: int, action: str) -> dict` (28)
  - `def mark_read(self, hr_id: int) -> dict` (19)
    - `async def run() -> dict` (10)
  - `def send_message(self, payload: dict) -> dict` (21)
  - `def pick_media(self, hr_id: int) -> dict` (20)
  - `def _send_media(self, payload: dict) -> dict` (17)

### `client/bridge/hub.py` — 60 строк

Живое хозяйство окна: то, из чего собран каждый домен поверхности.

Зависит от: `client.bridge.events`

- `class Hub` (43)

### `client/bridge/journal.py` — 106 строк

Системный журнал в окне: страница записей, подписка, очистка.

Зависит от: `backend.log_buffer`, `client.bridge.answer`, `client.bridge.refusals`

- `def close_journal() -> None` (9)
- `class Journal` (79)
  - `def _open_journal(self) -> None` (4)
  - `def logs(self) -> dict` (21)
    - `async def run() -> dict` (2)
  - `def watch_logs(self, subscribed: bool) -> dict` (12)
  - `def clear_logs(self) -> dict` (11)
    - `async def run() -> dict` (2)
  - `def _push_record(self, entry: dict) -> None` (16)

### `client/bridge/lifespan.py` — 301 строк ⚠ подошёл к 300

Жизнь моста при окне: от подъёма хозяйства до его гашения.

Зависит от: `backend.bot.client`, `backend.telegram_login`, `client.bridge.bot_stop`, `client.bridge.events`, `client.bridge.hub`, `client.bridge.journal`

- `def start(runner, session_factory, rs, engine=None) -> Hub` (20)
- `def stop(hub: Hub) -> None` (35)
- `def start_bot(hub: Hub) -> None` (28)
- `def _ready_for_bot(rs) -> bool` (9)
- `def _forget_login(hub: Hub) -> None` (14)
- `def _start_bot(hub: Hub) -> None` (25)
  - `async def _build_and_run() -> None` (8)
- `def _tell_the_window(bot, hub: Hub) -> None` (41)
  - `def arrived(hr_id: int) -> None` (3)
- `def _restart_bot(hub: Hub) -> None` (36)
  - `async def _swap() -> None` (15)
- `def _remember_login(hub: Hub, username: str | None) -> None` (17)
- `def _log_if_crashed(hub: Hub, future: Future) -> None` (20)

### `client/bridge/llm.py` — 232 строк

Поставщик модели для окна: проверить связь, спросить имена, выбрать файл модели.

Зависит от: `adapters`, `adapters.lm_studio`, `backend.log_secrets`, `backend.models`, `backend.provider_config`, `client.bridge.answer`, `client.bridge.desktop`, `client.bridge.refusals`

- `def _client_or_reason(cfg: LlmProviderConfig) -> tuple[LmClient | None, str]` (16)
- `async def _do_list_models_for_creds(base_url: str, api_key: str, *, kind: str | None=None) -> dict` (27)
- `async def _do_llm_probe(cfg: LlmProviderConfig, check_fn: Callable[[LmClient, str], Any]) -> tuple[bool, str, list[str], int]` (24)
- `def read_llm_creds(payload: dict, kind: str) -> LlmProviderConfig` (23)
- `def read_models_ask(payload) -> tuple[str, str, str]` (4)
- `def _provider_address(payload: dict) -> tuple[str, str]` (14)
- `class Llm` (80)
  - `def probe_model(self, payload: dict) -> dict` (34)
    - `async def run() -> dict` (10)
  - `def pick_model_file(self) -> dict` (11)
  - `def list_models(self, payload: dict) -> dict` (25)
    - `async def run() -> dict` (9)

### `client/bridge/login.py` — 129 строк

Вход в Telegram: три шага, общие основному окну и мастеру.

Зависит от: `backend.telegram_login`, `client.bridge.answer`, `client.bridge.refusals`

- `def read_credentials(payload: dict) -> tuple[int, str, str]` (12)
- `def read_code(payload: dict) -> str` (3)
- `def read_password(payload: dict) -> str` (7)
- `async def code_step(login, code: str) -> LoginStep` (10)
- `async def password_step(login, password: str) -> LoginStep` (10)
- `async def step_payload(step_coro) -> dict` (11)
- `class Login` (55)
  - `def send_code(self, payload: dict) -> dict` (16)
  - `def confirm_code(self, payload: dict) -> dict` (10)
  - `def confirm_password(self, payload: dict) -> dict` (10)

### `client/bridge/mail.py` — 50 строк

Почта для откликов в настройках: что записано и запись новой.

Зависит от: `backend.domain.mail_servers`, `backend.incoming`, `backend.repository.mail_account`, `client.bridge.answer`

- `class Mail` (40)
  - `def mail(self) -> dict` (16)
    - `async def run() -> dict` (10)
  - `def save_mail(self, payload: dict | None=None) -> dict` (17)
    - `async def run() -> dict` (5)

### `client/bridge/mark.py` — 167 строк

Отметка предмета в чёрном списке, поставленная из его карточки.

Зависит от: `backend.models`, `backend.repository`, `backend.repository.blacklist_marks`, `client.bridge.answer`, `client.bridge.refusals`

- `class MarkSubject` (14)
- `async def marked(hub, subject: MarkSubject, entity_id: int) -> dict` (12)
- `async def unmarked(hub, subject: MarkSubject, entity_id: int) -> dict` (10)
- `async def mark(session, subject: MarkSubject, entity_id: int) -> dict` (27)
- `async def unmark(session, subject: MarkSubject, entity_id: int) -> dict` (24)

### `client/bridge/media.py` — 87 строк

Вложение письма, каким его видит окно: адрес разметки и файл за адресом.

Зависит от: `backend.bot.media`, `backend.domain.image_types`, `client.serving`

- `def _media_url(stored_path: str | None) -> str | None` (19)
- `def media_file(url: str) -> Path | None` (11)
- `def _under_media(stored_path: str) -> str | None` (21)
- `def _image_type(blob: bytes) -> str` (8)
- `def _avatar_data_url(blob: bytes | None) -> str | None` (9)

### `client/bridge/page.py` — 89 строк

Запрос списка, прочитанный из нагрузки окна: сколько, откуда и что искать.

Зависит от: `backend.incoming`

- `class Page` (5)
- `def read_search(payload) -> str | None` (8)
- `def read_page(payload, *, default_limit: int | None=None) -> Page` (33)

### `client/bridge/payload.py` — 18 строк

Жалоба в журнал на негодную нагрузку, пришедшую из окна.

Зависит от: —

- `def _log_invalid_payload(slot: str, exc: Exception) -> None` (8)

### `client/bridge/pickers.py` — 130 строк

Списки кандидатов, которые окно показывает в модалке выбора.

Зависит от: `backend.repository`, `client.bridge.wire`

- `class PickerSubject` (16)
- `async def all_candidates(session, subject: PickerSubject) -> list[dict]` (18)
- `async def merge_picker(session, subject: PickerSubject, absorbed_id: int, search: str | None) -> dict` (21)
- `async def link_picker(session, subject: PickerSubject, vacancy, search: str | None) -> dict` (18)

### `client/bridge/profile.py` — 197 строк

Анкета соискателя: сведения о себе, навыки, места работы и проекты.

Зависит от: `backend.domain.salary`, `backend.domain.taxonomy`, `backend.incoming`, `backend.models`, `backend.payloads`, `backend.repository`, `backend.repository.profile_records`, `client.bridge.answer`, `client.bridge.choices`, `client.bridge.cv`, `client.bridge.cv_file`, `client.bridge.hub`, `client.bridge.refusals`, `client.bridge.wire`

- `class Profile(Cv)` (135)
  - `def get(self) -> dict` (19)
    - `async def run() -> dict` (14)
  - `def save(self, payload: dict) -> dict` (22)
    - `async def run() -> dict` (8)
  - `def skills(self) -> dict` (9)
    - `async def run() -> dict` (4)
  - `def save_skills(self, payload: dict) -> dict` (3)
  - `def experience(self) -> dict` (3)
  - `def save_experience(self, payload: dict) -> dict` (3)
  - `def projects(self) -> dict` (3)
  - `def save_projects(self, payload: dict) -> dict` (3)
  - `def _records(self, key: str, listing, to_dict) -> dict` (17)
    - `async def run() -> dict` (8)
  - `def _save_rows(self, payload: dict, key: str, saving) -> dict` (29)
    - `async def run() -> dict` (11)
- `def _read_profile_fields(payload: dict) -> dict` (26)

### `client/bridge/refusals.py` — 295 строк

Слова, которыми мост отказывает окну.

Зависит от: `backend.agent.availability`, `backend.bot.work`

- `def agent_refusals(table: dict, chat) -> dict` (7)

### `client/bridge/runner.py` — 92 строк

Цикл asyncio в своём потоке, куда поверхность окна отправляет работу.

Зависит от: —

- `class AsyncRunner` (77)
  - `def _run_loop(self) -> None` (38)
    - `def _quiet_pyrogram_shutdown(loop, context)` (26)
  - `def submit(self, coro: Coroutine[Any, Any, Any]) -> Future` (2)
  - `def stop(self) -> None` (24)
    - `async def _cancel_pending() -> None` (5)

### `client/bridge/settings.py` — 299 строк

Экран «Настройки»: всё, что окно спрашивает и правит на нём.

Зависит от: `adapters.browser`, `backend.agent.availability`, `backend.provider_config`, `backend.telegram_login`, `client.bridge.answer`, `client.bridge.bot_stop`, `client.bridge.hub`, `client.bridge.llm`, `client.bridge.login`, `client.bridge.mail`, `client.bridge.wire`

- `class Settings(Login, Llm, Mail)` (195)
  - `def get(self) -> dict` (37)
    - `async def run() -> dict` (28)
  - `def save(self, payload: dict | None=None) -> dict` (34)
    - `async def run() -> dict` (12)
  - `def logout(self) -> dict` (36)
    - `async def run() -> dict` (17)
  - `def cancel_login(self) -> dict` (18)
    - `async def run() -> dict` (3)
  - `async def _username(self) -> str` (22)
  - `async def _apply_providers(self, creds: dict[str, LlmProviderConfig]) -> list[str]` (10)
  - `async def _apply_app(self, app: dict, applied: list[str]) -> None` (15)
- `def _check_logout_without_bot(has_session: bool) -> None` (19)
- `async def _wait_connected(client) -> None` (8)
- `def _read_providers(payload: dict) -> dict[str, LlmProviderConfig]` (21)

### `client/bridge/source_page.py` — 72 строк

Страница вакансий одного источника — канала или агрегатора — для его карточки.

Зависит от: `backend.models.settings`, `backend.repository`, `client.bridge.answer`, `client.bridge.hub`, `client.bridge.page`, `client.bridge.wire`

- `class Source` (6)
- `def source_vacancies(hub: Hub, source: Source, payload: dict) -> dict` (12)
- `async def _paged(hub: Hub, source: Source, source_id: int, page: Page) -> dict` (23)

### `client/bridge/source_switch.py` — 29 строк

Общий выключатель источников одного рода — каналов или агрегаторов.

Зависит от: `client.bridge.answer`, `client.bridge.hub`

- `def switch_all(hub: Hub, key: str, where: str, payload: dict) -> dict` (15)
  - `async def run() -> dict` (3)

### `client/bridge/stats.py` — 58 строк

Экран «Статистика»: показатели за выбранный срок.

Зависит от: `backend.repository`, `client.bridge.answer`, `client.bridge.hub`

- `class Stats` (43)
  - `def _read(self, period: str, reading) -> dict` (15)
    - `async def run() -> dict` (3)
  - `def kpi(self, period: str) -> dict` (5)
  - `def status_breakdown(self, period: str) -> dict` (3)
  - `def hr_responses(self, period: str) -> dict` (3)
  - `def skills(self, period: str) -> dict` (3)
  - `def channels_pipeline(self, period: str) -> dict` (3)

### `client/bridge/system.py` — 413 строк ⚠ подошёл к 300

Домен «система»: то, чем страница живёт на любом экране.

Зависит от: `adapters`, `backend`, `backend.flows.handover`, `backend.incoming`, `backend.models`, `backend.repository`, `backend.repository.bot_mode`, `client.bridge.answer`, `client.bridge.app_update`, `client.bridge.desktop`, `client.bridge.hub`, `client.bridge.journal`, `client.bridge.llm`, `client.bridge.refusals`, `client.bridge.wipe`, `client.bridge.wire`

- `class System(Journal, Wipe, Desktop, AppUpdate)` (300)
  - `def initial(self) -> dict` (16)
    - `async def run() -> dict` (6)
  - `async def _mode(self) -> BotMode` (5)
  - `def set_mode(self, mode: str) -> dict` (26)
    - `async def run() -> dict` (7)
  - `def human_done(self, answer=None) -> dict` (6)
  - `def reveal_browser(self) -> dict` (5)
  - `def run_now(self) -> dict` (19)
  - `def new_vacancies(self) -> dict` (7)
    - `async def run() -> dict` (2)
  - `def apply_all_new(self) -> dict` (10)
  - `def stop_run(self) -> dict` (15)
    - `async def run() -> dict` (6)
  - `def unread_chats(self) -> dict` (13)
    - `async def run() -> dict` (4)
  - `def events(self, after) -> dict` (15)
  - `def health(self) -> dict` (3)
  - `def unread(self) -> dict` (3)
  - `async def _health(self) -> dict` (25)
  - `async def _unread(self) -> dict` (4)
  - `async def _models_alive(self) -> tuple[bool, bool]` (31)
  - `async def _probe_models(self) -> None` (7)
  - `async def _ask_models(self) -> tuple[bool, bool]` (5)
  - `def _time_new_links(self) -> None` (23)
  - `async def _time_models(self, kinds: list[str]) -> None` (16)
- `async def _speed_of(cfg, kind: str) -> int | None` (8)
- `def _probed(task: Future) -> None` (16)
- `def _after(asked) -> int | None` (21)

### `client/bridge/vacancies.py` — 324 строк ⚠ подошёл к 300

Экран «Вакансии»: список, карточка и правки в них.

Зависит от: `backend.domain.scoring`, `backend.incoming`, `backend.models`, `backend.repository`, `client.bridge.answer`, `client.bridge.events`, `client.bridge.form_payloads`, `client.bridge.hub`, `client.bridge.page`, `client.bridge.refusals`, `client.bridge.vacancy_actions`, `client.bridge.vacancy_contacts`, `client.bridge.vacancy_filter`, `client.bridge.vacancy_links`, `client.bridge.wire`

- `def _typed_text(raw) -> str | None` (8)
- `class Vacancies(VacancyActions, VacancyLinks, VacancyContacts)` (265)
  - `def list(self, payload: dict | None=None) -> dict` (15)
  - `def filter_options(self) -> dict` (19)
    - `async def run() -> dict` (4)
  - `async def _listed(self, filters) -> dict` (15)
  - `def detail(self, vacancy_id) -> dict` (31)
    - `async def run() -> dict` (13)
  - `def screening(self, vacancy_id: int) -> dict` (10)
    - `async def run() -> dict` (5)
  - `def save_notes(self, payload: dict) -> dict` (25)
    - `async def run() -> dict` (10)
  - `def save_history_explanation(self, payload: dict) -> dict` (38)
    - `async def run() -> dict` (21)
  - `def change_status(self, payload: dict) -> dict` (35)
    - `async def run() -> dict` (16)
  - `def create(self, payload: dict) -> dict` (28)
    - `async def run() -> dict` (6)
  - `def create_from_text(self, payload: dict) -> dict` (24)

### `client/bridge/vacancy_actions.py` — 117 строк

Действия над вакансией: перезапуск разбора, отклик, удаление.

Зависит от: `backend.applying.world`, `backend.domain.apply_order`, `backend.repository`, `client.bridge.answer`, `client.bridge.events`, `client.bridge.refusals`, `client.bridge.vacancy_links`

- `class VacancyActions` (94)
  - `def rerun(self, payload: dict) -> dict` (20)
  - `def apply_ways(self, vacancy_id: int) -> dict` (12)
    - `async def run() -> dict` (3)
  - `async def _available_ways(self, vacancy_id: int) -> list[Way]` (4)
  - `def apply_via(self, payload: dict) -> dict` (25)
    - `async def run() -> Way` (6)
  - `def delete(self, payload: dict) -> dict` (23)
    - `async def run() -> dict` (15)

### `client/bridge/vacancy_contacts.py` — 56 строк

Контакты вакансии, которые человек правит в карточке.

Зависит от: `backend.domain.contact_keys`, `backend.incoming`, `backend.models`, `backend.repository`, `client.bridge.answer`, `client.bridge.refusals`, `client.bridge.vacancy_links`, `client.bridge.wire`

- `class VacancyContacts` (37)
  - `def add_contact(self, payload: dict) -> dict` (19)
    - `async def run() -> dict` (8)
  - `def delete_contact(self, payload: dict) -> dict` (14)
    - `async def run() -> dict` (7)
- `async def _contacts_of(session, vacancy_id: int) -> dict` (3)

### `client/bridge/vacancy_filter.py` — 55 строк

Отбор списка вакансий, прочитанный из нагрузки окна.

Зависит от: `backend.incoming`, `backend.payloads`, `client.bridge.page`

- `def read_vacancy_filter(payload: dict, page: Page) -> VacancyFilter` (34)

### `client/bridge/vacancy_links.py` — 227 строк

Привязка вакансии к человеку и к компании: подборщики и их правки.

Зависит от: `backend.incoming`, `backend.models`, `backend.repository`, `client.bridge.answer`, `client.bridge.companies`, `client.bridge.form_payloads`, `client.bridge.hr`, `client.bridge.pickers`, `client.bridge.refusals`

- `async def require_vacancy(session, vacancy_id: int) -> None` (8)
- `class VacancyLinks` (158)
  - `def hr_picker(self, payload: dict) -> dict` (8)
  - `def company_picker(self, payload: dict) -> dict` (3)
  - `def create_options(self) -> dict` (18)
    - `async def run() -> dict` (6)
  - `def _open_picker(self, slot: str, payload: dict) -> dict` (11)
  - `def link_hr(self, payload: dict) -> dict` (7)
  - `def link_company(self, payload: dict) -> dict` (3)
  - `def _link(self, slot: str, payload: dict) -> dict` (15)
    - `async def run() -> dict` (3)
  - `def create_hr(self, payload: dict) -> dict` (7)
  - `def create_company(self, payload: dict) -> dict` (3)
  - `def _created(self, slot: str, payload: dict) -> dict` (26)
    - `async def run() -> dict` (5)
  - `async def _picker(self, kind, vacancy_id: int, search: str | None) -> dict` (5)
  - `async def _listing(self, session, kind, vacancy_id: int, search: str | None) -> dict` (12)
  - `async def _linked(self, setting, vacancy_id: int, other_id: int | None, action: str, missing: str)` (22)

### `client/bridge/wipe.py` — 101 строк

Снос всех данных приложения по просьбе из окна.

Зависит от: `backend.crypto`, `backend.wipe`, `client.bridge.answer`, `client.bridge.bot_stop`, `client.bridge.refusals`

- `class Wipe` (52)
  - `def wipe(self) -> dict` (40)
    - `async def run() -> dict` (20)
- `def _leave_later() -> None` (9)
- `def _leave() -> None` (9)

### `client/bridge/wire.py` — 490 строк ⚠ подошёл к 300

Перевод внутренних значений в словари, которые читает окно.

Зависит от: `backend.domain.skill_names`, `backend.models`, `client.bridge.media`

- `def _iso(dt: datetime | None) -> str | None` (17)
- `def _vacancy_mini_row_to_dict(v) -> dict` (20)
- `def _tg_creds_to_dict(tg) -> dict` (20)
- `def _llm_provider_to_dict(cfg) -> dict` (19)
- `def _enum_value(member) -> str | None` (2)
- `def _profile_to_dict(p, languages=None) -> dict | None` (28)
- `def _skill_to_dict(s) -> dict` (8)
- `def _exp_to_dict(e) -> dict` (12)
- `def _project_to_dict(p) -> dict` (8)
- `def _stack_items(stack, matched_set: set[str]) -> list[dict]` (8)
- `def _company_name(v) -> str | None` (12)
- `def _hr_face(hr) -> dict` (13)
- `def _status_change(row) -> dict` (15)
- `def _vacancy_event(row) -> dict` (8)
- `def _contact(c) -> dict` (2)
- `def _salary(v) -> dict` (17)
- `def _source(v) -> dict` (13)
- `def _vacancy_detail_to_dict(detail, matched_set: set[str], score_threshold: int) -> dict` (39)
- `def _hr_picker_row_to_dict(item) -> dict` (18)
- `def _hr_mini_row_to_dict(hr, vacancy_count: int) -> dict` (11)
- `def _message_row_to_dict(m) -> dict` (19)
- `def _blacklist_row_to_dict(row: Blacklist) -> dict` (14)
- `def _channel_row_to_dict(item) -> dict` (8)
- `def _channel_card_to_dict(detail) -> dict` (6)
- `def _channel_fields(ch) -> dict` (8)
- `def _company_picker_row_to_dict(item) -> dict` (14)
- `def _vacancy_list_row_to_dict(v, matched_set: set[str], activity_by_id: dict[int, Any] | None=None) -> dict` (34)
- `def _aggregator_row_to_dict(row) -> dict` (11)
- `def _aggregator_list_row_to_dict(row, vacancy_count: int, barred: bool) -> dict` (3)
- `def _screening_to_dict(shown) -> dict` (4)
- `def _source_stats_to_dict(stats) -> dict` (6)

### `client/bridge/wizard.py` — 126 строк

Порядок первого запуска: чем он продолжается и когда он кончен.

Зависит от: `backend.repository.app_settings`, `client.bridge.answer`, `client.bridge.hub`, `client.bridge.lifespan`, `client.bridge.wire`, `client.window_size`

- `class Wizard` (91)
  - `def state(self) -> dict` (21)
    - `async def run() -> dict` (11)
  - `def skip_cv(self) -> dict` (13)
    - `async def run() -> dict` (3)
  - `def complete(self) -> dict` (21)
    - `async def run() -> dict` (3)
  - `def enter_main_app(self) -> dict` (12)
- `def _steps_behind(rs) -> list[int]` (20)

### `client/raise_window.py` — 215 строк

Договор двух копий приложения о том, чьё окно показать человеку.

Зависит от: `config`

- `def socket_name() -> str` (12)
- `def port_of(name: str) -> int` (9)
- `class _RaiseHandler(socketserver.StreamRequestHandler)` (23)
  - `def handle(self) -> None` (18)
- `class _RaiseServer(socketserver.ThreadingTCPServer)` (30)
  - `def close(self) -> None` (4)
- `def listen(window, name: str | None=None) -> _RaiseServer | None` (17)
- `def _bring_forward(window) -> None` (12)
- `def _let_the_other_copy_come_forward() -> None` (14)
- `def ask_to_raise(name: str | None=None) -> bool` (18)

### `client/serving.py` — 163 строк

Файлы, которые страница окна читает по http.

Зависит от: —

- `def served_files(front_root: Path, media_root: Path) -> Callable` (34)
  - `def application(environ: dict, start_response: Callable) -> Iterable[bytes]` (18)
- `def _read(target: Path | None) -> bytes | None` (15)
- `def inside(root: Path, path: str) -> Path | None` (21)
- `def _or_index(path: str) -> str` (10)
- `def _content_type(target: Path) -> str` (17)

### `client/trouble_box.py` — 37 строк

Сказать человеку о беде, когда своего окна ещё нет.

Зависит от: —

- `def show_trouble(text: str) -> None` (11)

### `client/window.py` — 254 строк

Окно приложения: как оно открывается и чем гасится.

Зависит от: `adapters`, `adapters.telegram`, `backend.bot.media`, `backend.models`, `backend.repository.bot_mode`, `backend.runtime_settings`, `client`, `client.bridge`, `client.serving`, `config`

- `def run_ui() -> int` (32)
- `def _open_window(hub, *, settled: bool)` (19)
- `def _put_out_claude_code(runner) -> None` (6)
- `def _put_out(hub, runner, listening) -> None` (36)
- `async def prepare(session_factory) -> RuntimeSettings` (13)
- `def _open_runner() -> AsyncRunner` (4)
- `def _open_database() -> tuple[Any, async_sessionmaker]` (9)
- `def _await(future: Future) -> Any` (3)
- `def _icon() -> str | None` (11)
- `def _own_the_taskbar_icon() -> None` (14)
- `def _drop_stale_session_files(rs: RuntimeSettings) -> None` (24)

### `client/window_size.py` — 74 строк

Размеры окна: каким оно открывается и в какой миг вырастает.

Зависит от: —

- `def grow_to_main(window) -> None` (18)
- `def _unlock_frame(form) -> None` (27)
  - `def apply() -> None` (6)

## tests — 324 модулей

### `tests/adapters/test_agent_mcp.py` — 85 строк

Инструменты сессии доступны по своему адресу и только по нему.

Зависит от: `adapters.agent_mcp`

Тестов: 4

- `async def _echo(text: str) -> str` (3)

### `tests/adapters/test_app_tied_process.py` — 100 строк

Привязка к приложению: кого Windows снимет вместе с ним и кого не тронет.

Зависит от: `adapters`

Тестов: 4

- `def _alive(pid: int) -> bool` (5)
- `def _orphan(mode: str) -> int` (7)

### `tests/adapters/test_browser_choice.py` — 45 строк

Какой браузер водит агент: первый найденный из перечня.

Зависит от: `adapters.browser`

Тестов: 4

- `def _install(root: Path, relative: str) -> Path` (5)
- `def _roots(monkeypatch, tmp_path)` (4)

### `tests/adapters/test_browser_sending.py` — 139 строк

Профиль под симуляцией отклика: данные с сайта не уходят, капча проходится.

Зависит от: `adapters.browser`

Тестов: 9

- `class _Request` (3)
- `class _Route` (10)
  - `async def abort(self, *_reason)` (2)
  - `async def continue_(self, **_options)` (2)
- `async def _fate(method, url)` (4)
- `class _Context` (18)
  - `async def route(self, pattern, handler)` (2)
  - `async def add_init_script(self, script)` (2)
  - `def on(self, *_event)` (2)
  - `async def close(self)` (2)
- `class _Page` (5)
  - `def on(self, *_event)` (2)
- `class _Playwright` (11)
  - `async def start(self)` (2)
  - `async def launch_persistent_context(self, _path, **options)` (3)

### `tests/adapters/test_claude.py` — 263 строк

Следствия разговора с Claude через нынешние точки входа адаптеров.

Зависит от: `adapters`, `adapters.lm_chat`, `adapters.lm_studio`, `backend.provider_config`, `tests.fakes.claude`, `tests.fakes.llm`

Тестов: 16

- `def _body(client) -> dict` (3)
- `def wire(monkeypatch)` (19)
  - `def install(routes: dict) -> list` (9)
    - `async def relay(_transport, request)` (2)

### `tests/adapters/test_claude_code.py` — 361 строк ⚠ подошёл к 300

Следствия разговора с Claude через живой процесс Claude Code по подписке.

Зависит от: `adapters`, `adapters.claude_code`, `adapters.claude_code_process`, `adapters.lm_chat`, `adapters.lm_studio`, `backend.provider_config`, `tests.fakes.claude_code`, `tests.fakes.llm`

Тестов: 22

- `def _client() -> ClaudeCodeClient` (2)
- `def _model_of(process) -> str` (3)

### `tests/adapters/test_claude_code_agent.py` — 128 строк

Сессия агента: отдельный процесс Claude Code с инструментами приложения.

Зависит от: `adapters.claude_code_agent`, `adapters.claude_code_process`, `backend.agent.prompts.applier`, `backend.agent.prompts.frame`, `tests.fakes`

Тестов: 11


### `tests/adapters/test_cv_text.py` — 299 строк

Следствия чтения резюме с диска: что достаётся из файла и что мешает.

Зависит от: `adapters.cv_text`

Тестов: 17

- `def _tiny_pdf(pages: list[list[tuple[int, str]]]) -> bytes` (59)

### `tests/adapters/test_gguf_embed.py` — 169 строк

Следствия счёта векторов из файла модели; настоящая модель не грузится.

Зависит от: `adapters`, `adapters.gguf_embed`, `adapters.lm_studio`, `backend.provider_config`, `tests.fakes.gguf`

Тестов: 11

- `def journal(monkeypatch)` (3)

### `tests/adapters/test_lm_chat.py` — 164 строк

Следствия разговора с чат-моделью: что уходит и что получается.

Зависит от: `adapters.lm_chat`, `tests.fakes.llm`

Тестов: 5


### `tests/adapters/test_lm_embed.py` — 38 строк

Следствия обращения к модели встраиваний.

Зависит от: `adapters.lm_embed`, `tests.fakes.llm`

Тестов: 4


### `tests/adapters/test_lm_models.py` — 215 строк

Следствия перечня моделей у провайдера и проверки, что модель отвечает.

Зависит от: `adapters.lm_models`, `tests.fakes.llm`

Тестов: 15


### `tests/adapters/test_lm_studio.py` — 42 строк

Следствия соединения с провайдером моделей.

Зависит от: `adapters.lm_studio`, `backend.provider_config`

Тестов: 4


### `tests/adapters/test_smtp_mail.py` — 98 строк

Письмо уходит по SMTP с вложенным резюме и входом под паролем приложения.

Зависит от: `adapters.smtp_mail`, `tests.factories`

Тестов: 3

- `class _FakeSmtp` (31)
  - `def __enter__(self)` (2)
  - `def __exit__(self, *exc)` (4)
  - `def quit(self)` (2)
  - `def close(self)` (2)
  - `def starttls(self, **_options)` (2)
  - `def login(self, user, password)` (3)
  - `def send_message(self, message)` (2)
- `class _RudeSmtp(_FakeSmtp)` (5)
  - `def quit(self)` (2)

### `tests/backend/conftest.py` — 83 строк

Фикстуры слоя `backend`, собранные из модулей по предметам.

Зависит от: `tests.backend.fixtures.aggregators`, `tests.backend.fixtures.applying`, `tests.backend.fixtures.backfill`, `tests.backend.fixtures.bot`, `tests.backend.fixtures.entry`, `tests.backend.fixtures.flows`, `tests.backend.fixtures.listing`, `tests.backend.fixtures.logs`, `tests.backend.fixtures.rerun`, `tests.backend.fixtures.stats`

Отдаёт наружу: `applied`, `board`, `busy_slot`, `caught_up`, `channel_titles`, `chatting`, `chatting_on_fakes`, `clean_log_file`, `clean_root_logger`, `deliver`, `dm_pipeline`, `empty_media_dir`, `entry`, `hr_names`, `kit`, `kit_with`, `known_hr`, `lock_of_its_own`, `make_bot`, `mail_case`, `make_pipeline`, `manual_case`, `one_vector`, `outbox`, `parsing`, `ready_to_send`, `rerunning`, `sending_unlocked`, `silent_embedder`, `telegram_case`, `titles`, `turn_and_settle`, `two_vacancies`, `unparsed_vacancy`, `web_search`


### `tests/backend/fixtures/__init__.py` — 1 строк

Обстановка для проверок слоя `backend`, разложенная по предметам.

Зависит от: —


### `tests/backend/fixtures/aggregators.py` — 14 строк

Строка «Поиск по сети»: миграция заводит её раз, а стенд чистит таблицы после каждого теста.

Зависит от: `backend.models`, `tests.dbio`, `tests.factories_aggregators`

- `async def web_search(session_factory) -> Aggregator` (4)

### `tests/backend/fixtures/applying.py` — 190 строк

Стенд откликателя: набор агента и вакансии, на которые есть чем откликнуться.

Зависит от: `backend.applying`, `backend.bot`, `backend.domain.apply_order`, `backend.llm.agent_letter`, `backend.models`, `backend.repository.app_settings`, `tests.dbio`, `tests.factories`, `tests.factories_aggregators`, `tests.fakes.agent`, `tests.fakes.browser`

- `async def kit(make_pipeline)` (3)
- `def board(session_factory)` (13)
  - `async def make(**vacancy)` (8)
- `async def _pipeline(make_pipeline, *, simulated: bool, resume=None)` (7)
- `def kit_with(make_pipeline)` (7)
  - `async def make(steps, *, send_locked=False)` (2)
- `async def two_vacancies(session_factory)` (12)
- `def telegram_case(make_pipeline, session_factory, tmp_path, monkeypatch, outbox)` (24)
  - `async def make(*, prior_letter=False, flood_wait=None, simulated=False, hr_user_id=None)` (14)
- `def manual_case(make_bot, session_factory, tmp_path, monkeypatch)` (21)
  - `async def make(*, status=VacancyStatus.NEW, hang=False)` (14)
- `async def telegram_vacancy(session_factory, *, hr_user_id=None, status=VacancyStatus.NEW)` (7)
- `def _model_writes_the_letter(monkeypatch) -> None` (7)
  - `async def generate_cover_letter(block, parsed, client, model, *, channel_ref=None)` (2)
- `def mail_case(make_pipeline, session_factory, tmp_path, monkeypatch)` (31)
  - `async def make(*, server_refuses=False, simulated=False, mail=True, resume=True)` (22)
    - `def send_mail(account, mail)` (4)
    - `async def write_letter(ask, client, model)` (2)

### `tests/backend/fixtures/backfill.py` — 75 строк

Обстановка для проверок догона переписки: собеседник и прогон догона.

Зависит от: `backend.flows.dm`, `backend.flows.dm_backfill`, `backend.models`, `tests.dbio`, `tests.factories`, `tests.fakes.telegram_objects`

- `def theirs(msg_id, text)` (3)
- `def ours(msg_id, text, *, photo=None)` (3)
- `def _helpers(client, session_factory, **extra) -> DmHelpers` (14)
- `async def catch_up(client, hr, session_factory, *, hooks=None, **kwargs)` (9)
- `async def catch_up_everyone(client, session_factory, *, hooks=None, dialogs=None, **kwargs)` (15)
- `async def known_hr(session_factory)` (4)

### `tests/backend/fixtures/bot.py` — 320 строк ⚠ подошёл к 300

Обстановка для проверок бота: всё собрано на подделках, до сети не доходит.

Зависит от: `adapters.telegram`, `backend.bot`, `backend.bot.client`, `backend.bot.media`, `backend.crypto`, `backend.models`, `backend.repository.bot_mode`, `backend.runtime_settings`, `backend.task_stop`, `tests.dbio`, `tests.factories`, `tests.fakes.ingestion`, `tests.fakes.lm_studio`, `tests.fakes.telegram`, `tests.waiting`

- `async def slot_freed(bot) -> None` (3)
- `class Outbox` (18)
  - `async def send_dm(self, _client, target, text, attachment=None)` (5)
- `def row_saved_mid_send(session_factory, hr_id)` (20)
  - `async def save(answer) -> None` (10)
- `async def switch_to(session_factory, mode: BotMode) -> None` (5)
- `def make_bot(session_factory, monkeypatch)` (40)
  - `async def build(client=None, *, embed_url='http://provider.test') -> Bot` (17)
- `def empty_media_dir()` (13)
- `def chatting(session_factory, make_bot)` (17)
  - `async def build(*, mode=BotMode.FULL, client=None, **hr_fields)` (6)
- `def chatting_on_fakes(chatting)` (18)
  - `async def build(**kwargs)` (3)
- `async def busy_slot()` (18)
  - `def occupy(bot) -> None` (4)
- `def sending_unlocked(monkeypatch)` (10)
- `def outbox(monkeypatch, sending_unlocked)` (11)
- `def ready_to_send(session_factory, make_bot)` (24)
  - `async def build(*, status=VacancyStatus.NEW, mode=BotMode.FULL, hr=None)` (13)
- `def turn_and_settle(monkeypatch)` (36)
  - `async def run(bot, mode)` (18)
    - `async def next_mode(session)` (11)
- `def caught_up(monkeypatch)` (13)
  - `async def catch_up_missed_dms(client, *args, **kwargs)` (2)

### `tests/backend/fixtures/entry.py` — 74 строк

Точка входа с подменёнными шагами запуска — общая двум сторожам.

Зависит от: `main`

- `def lock_of_its_own(monkeypatch, tmp_path)` (12)
- `def entry(clean_root_logger, lock_of_its_own, monkeypatch)` (44)
  - `def check_keyring()` (2)
  - `def ensure_schema()` (2)
  - `def run_ui()` (3)

### `tests/backend/fixtures/fit.py` — 32 строк

Как тесты спрашивают зовы о пригодности — о роли, о языках.

Зависит от: `backend.llm.candidate`, `tests.factories`

- `async def asked(check, client, *, raw_text='обычный текст вакансии', profile=None, parsed=None)` (9)
- `async def verdict(check, client, *, raw_text='обычный текст вакансии', profile=None, parsed=None)` (11)

### `tests/backend/fixtures/flows.py` — 313 строк ⚠ подошёл к 300

Обстановка для проверок конвейера: он собран на подделках, модель молчит.

Зависит от: `backend.flows`, `backend.flows.dm`, `backend.flows.pipeline`, `backend.models`, `backend.payloads`, `backend.runtime_settings`, `backend.task_stop`, `tests.dbio`, `tests.factories`, `tests.fakes.lm_studio`, `tests.fakes.telegram`, `tests.fakes.telegram_objects`

- `def known_hr_client() -> FakeTelegramClient` (13)
- `def _pipeline_on_fakes(session_factory, client, settings) -> IngestionPipeline` (22)
  - `async def apply(vacancy_ids)` (2)
- `async def _put_out_backfills(pipelines) -> None` (10)
- `def _answer_instead_of_the_model(pipeline, monkeypatch) -> None` (35)
  - `async def parse_vacancy(text, client_, model, **kwargs)` (3)
  - `async def classify_post_genre(text, client_, model)` (3)
  - `def asking_fit(about: str)` (14)
    - `async def ask(parsed, text, client_, model, **kwargs)` (4)
- `async def make_pipeline(session_factory)` (24)
  - `async def build(client=None)` (7)
- `def one_vector(monkeypatch) -> list[str]` (15)
  - `async def embed(_client, _model, text)` (3)
- `def similar_by_hand(pipeline, monkeypatch) -> None` (17)
  - `async def unparsed(_pipeline, _vacancy_id)` (2)
- `def silent_embedder(monkeypatch, one_vector)` (11)
  - `async def silent(_client, _model, _text)` (2)
- `def deliver(session_factory)` (20)
  - `async def run(msg, *, client=None, schedule=None)` (10)
- `async def unparsed_vacancy(session_factory)` (17)
- `def _fit_answers_by_default(pipeline) -> None` (17)
- `async def parsing(make_pipeline, monkeypatch, unparsed_vacancy, session_factory)` (33)
- `async def dm_pipeline(monkeypatch, make_pipeline)` (18)
  - `async def classify(pipeline, hr_id)` (2)

### `tests/backend/fixtures/listing.py` — 55 строк

Перечни репозитория, сведённые к опознавательному знаку строки.

Зависит от: `backend.payloads`, `backend.repository.channels`, `backend.repository.hr_list`, `backend.repository.vacancies_list`

- `def titles(session)` (15)
  - `async def read(**kwargs) -> list[str]` (3)
- `def hr_names(session)` (13)
  - `async def read(**kwargs) -> list[str]` (3)
- `def channel_titles(session)` (10)
  - `async def read(**kwargs) -> list[str]` (5)

### `tests/backend/fixtures/logs.py` — 57 строк

Общая обстановка проверок журнала: корневой логгер, файл и готовая запись.

Зависит от: `config`

- `def clean_root_logger()` (20)
- `def clean_log_file()` (11)
- `def record(msg: str, *, name: str='проверка', level: int=logging.INFO)` (6)

### `tests/backend/fixtures/parse_stub.py` — 36 строк

Подставной разбор объявления, складывающий зовы в переданный список.

Зависит от: `backend.flows`

- `def parse_into(monkeypatch, calls: list, *, done=True, fails=()) -> None` (21)
  - `async def parse(pipeline, vacancy_id, text, username, *, allow_delete=True)` (5)

### `tests/backend/fixtures/rerun.py` — 71 строк

Обстановка для проверок повторного прогона вакансии.

Зависит от: `backend.flows`, `backend.models`, `tests.backend.fixtures.parse_stub`, `tests.dbio`, `tests.factories`, `tests.fakes.telegram`

- `class WithMessages(FakeTelegramClient)` (14)
  - `async def get_messages(self, chat_id, message_ids=None)` (5)
- `async def rerunning(make_pipeline, session_factory)` (15)
- `async def prepare(monkeypatch, make_pipeline, client)` (20)
  - `async def reload()` (2)
  - `async def embed(pipeline, text, what)` (3)

### `tests/backend/fixtures/stats.py` — 62 строк

Обстановка для проверок сводки: отклик и ответ на него.

Зависит от: `backend.models`, `backend.repository.stats_pipeline`, `tests.dbio`, `tests.factories`

- `def applied(session_factory)` (45)
  - `async def build(applied_at, *, answered_after=None, answer=VacancyStatus.ANSWERED, **overrides)` (20)
- `async def rows_by_channel(session, **kwargs) -> dict[int | None, dict]` (4)

### `tests/backend/test_adapters_github_release.py` — 59 строк

Последний релиз приложения на GitHub: что из ответа API берётся и когда релиза нет.

Зависит от: `adapters.github_release`, `tests.fakes.github_release`

Тестов: 6


### `tests/backend/test_adapters_telegraph.py` — 205 строк

Следствия, которые наблюдают тесты `adapters/telegraph.py`.

Зависит от: `adapters`

Тестов: 9

- `def _page(*, headline: str='Senior Manual QA', body: str='<p>Ищем QA</p>') -> str` (9)
- `def _client(handler) -> httpx.AsyncClient` (3)

### `tests/backend/test_agent_availability.py` — 23 строк

Агенту нужны водитель и браузер; без них агрегаторы заперты с подсказкой.

Зависит от: `adapters.browser`, `backend.agent.availability`, `backend.provider_config`

Тестов: 4


### `tests/backend/test_agent_human_gate.py` — 243 строк

Пауза на человека: браузер виден, окно знает, срок — час.

Зависит от: `backend.agent.human_gate`, `tests.fakes.browser`

Тестов: 17

- `def _gate(limit=60.0)` (5)

### `tests/backend/test_agent_prompts.py` — 126 строк

Сборка промптов агента: что код подставляет и чего в них быть не может.

Зависит от: `backend.agent.prompts.applier`, `backend.agent.prompts.frame`, `backend.agent.prompts.login`, `backend.agent.prompts.seeker`, `backend.domain.apply_order`, `backend.llm.rules`, `backend.models`, `backend.runtime_settings`, `tests.factories`, `tests.fakes.agent`

Тестов: 15

- `def _task(vacancy_text='Текст вакансии', profile_text='Анкета', method=ApplicationVia.FORM.value, **job) -> str` (5)

### `tests/backend/test_agent_sessions.py` — 69 строк

Сессия агента под надзором: срок человека, общий срок, остановка.

Зависит от: `backend.agent.kit`, `backend.agent.sessions`, `backend.agent.stops`, `tests.fakes.agent`

Тестов: 4


### `tests/backend/test_agent_tools_applier.py` — 156 строк

Откликатель пишет отклик только на свою вакансию и только своим способом.

Зависит от: `adapters.agent_mcp`, `backend.agent.jobs`, `backend.agent.tools_applier`, `backend.models`, `tests.dbio`, `tests.factories`, `tests.fakes.agent`

Тестов: 9

- `def _job(vacancy_id, **over) -> ApplyJob` (3)

### `tests/backend/test_agent_tools_browser.py` — 86 строк

Инструменты браузера: что агент видит и что доходит до страницы.

Зависит от: `backend.agent.tools_browser`, `tests.fakes.agent`, `tests.fakes.browser`

Тестов: 7

- `def _tools(page, resume=None)` (2)

### `tests/backend/test_agent_tools_common.py` — 118 строк

Общие инструменты агента: анкета, вход, итог, неудача.

Зависит от: `backend.agent.jobs`, `backend.agent.tools_common`, `backend.models`, `backend.repository.agent_profile`, `tests.dbio`, `tests.factories`, `tests.factories_aggregators`, `tests.fakes.agent`

Тестов: 9

- `class _Gate` (7)
  - `async def wait(self, kind, host, _browser)` (3)

### `tests/backend/test_agent_tools_letter.py` — 77 строк

Письмо для отклика: пишет приложение или сверяется письмо агента; две отбивки — предел.

Зависит от: `backend.agent.tools_letter`, `tests.dbio`, `tests.factories`, `tests.fakes.agent`, `tests.fakes.llm`

Тестов: 6

- `async def _letter(make_pipeline, session_factory, answers, *, writer='app')` (7)

### `tests/backend/test_agent_tools_seeker.py` — 224 строк

Инструменты искателя: известна ли вакансия и передача найденного в конвейер.

Зависит от: `backend.agent.jobs`, `backend.agent.tools_seeker`, `backend.models`, `tests.dbio`, `tests.factories`, `tests.factories_aggregators`, `tests.fakes.agent`

Тестов: 16

- `class _Queue` (6)
  - `def put(self, vacancy_id, text)` (2)
- `async def _seeker(make_pipeline, session_factory, *, limit=5)` (6)
- `async def _web_seeker(make_pipeline, session_factory)` (6)

### `tests/backend/test_app_version.py` — 30 строк

Новее ли релиз, чем запущенное приложение: по тегу вида `v1.2.3`.

Зависит от: `backend`, `backend.app_version`

Тестов: 3

- `def running_1_9_0(monkeypatch)` (3)

### `tests/backend/test_applying_browser.py` — 114 строк

Браузерный способ: одна сессия агента на кнопку агрегатора или форму работодателя.

Зависит от: `backend.agent.stops`, `backend.applying.browser`, `backend.applying.result`, `backend.domain.apply_order`, `backend.models`, `tests.backend.fixtures.applying`, `tests.dbio`, `tests.factories_aggregators`, `tests.fakes.agent`

Тестов: 10


### `tests/backend/test_applying_email.py` — 92 строк

Отклик письмом: модель приложения пишет, сервер почты принимает, отклик записывается.

Зависит от: `backend.applying.email`, `backend.applying.result`, `backend.domain.apply_order`, `backend.models`, `tests.dbio`, `tests.waiting`

Тестов: 8


### `tests/backend/test_applying_run.py` — 109 строк

Цикл откликателя: по каждой вакансии первый доступный способ, пока один не удастся.

Зависит от: `backend.applying`, `backend.applying.result`, `backend.domain.apply_order`, `backend.models`

Тестов: 8

- `def executors(monkeypatch)` (13)
  - `def fake(method)` (5)
    - `async def execute(kit, vacancy_id, way)` (3)

### `tests/backend/test_applying_telegram.py` — 75 строк

Отклик в Telegram: письмо, доставка и след в базе.

Зависит от: `backend.applying.result`, `backend.applying.telegram`, `backend.models`, `tests.backend.fixtures.applying`, `tests.dbio`, `tests.factories`

Тестов: 7


### `tests/backend/test_applying_telegram_letter.py` — 84 строк

Следствия составления короткого письма про очередную вакансию.

Зависит от: `backend.applying.telegram_letter`

Тестов: 6


### `tests/backend/test_applying_world.py` — 57 строк

Мир откликателя: что доступно прямо сейчас.

Зависит от: `backend.applying.result`, `backend.applying.world`, `backend.domain.apply_order`, `tests.dbio`, `tests.factories`, `tests.factories_aggregators`

Тестов: 7

- `async def _facts(session_factory, **vacancy)` (5)

### `tests/backend/test_bootstrap_schema.py` — 160 строк

Следствия подготовки схемы базы при запуске.

Зависит от: `alembic`, `backend.bootstrap`, `tests.conftest`, `tests.dbio`

Тестов: 3

- `def _revision_reached(db_file) -> str` (2)
- `def _project_of_two_revisions(root, db_file) -> None` (20)
- `def _revisions_in(paths) -> set[str]` (9)

### `tests/backend/test_bot_aggregators.py` — 354 строк ⚠ подошёл к 300

Обход агрегаторов в боте: место прогона, режимы, человек, сроки, ручные действия.

Зависит от: `backend.bot`, `backend.bot.turn`, `backend.models`, `tests.backend.fixtures.bot`, `tests.dbio`, `tests.factories`, `tests.factories_aggregators`, `tests.fakes.agent`, `tests.fakes.browser`, `tests.waiting`

Тестов: 21

- `def agent(monkeypatch)` (13)
  - `def install(bot, steps, *, human_limit=None)` (8)
- `async def sites(session_factory)` (5)
- `def _hold(release)` (5)
  - `async def step(tools)` (3)
- `def sought(monkeypatch)` (9)
  - `async def seek(kit, source)` (2)

### `tests/backend/test_bot_apply.py` — 101 строк

Ручной отклик одним зовом: выбранный способ через того же откликателя, в месте прогона.

Зависит от: `backend.applying`, `backend.applying.result`, `backend.bot.apply`, `backend.domain.apply_order`, `backend.models`, `tests.backend.fixtures.applying`, `tests.backend.fixtures.bot`, `tests.dbio`

Тестов: 10


### `tests/backend/test_bot_channels.py` — 168 строк

Следствия добавления канала из окна настроек.

Зависит от: `backend.models`, `tests.dbio`, `tests.factories`, `tests.fakes.telegram`, `tests.fakes.telegram_objects`

Тестов: 9


### `tests/backend/test_bot_chat_media.py` — 271 строк

Следствия отправки файла HR из вкладки «Контакты».

Зависит от: `backend.bot.media`, `backend.models`, `tests.backend.fixtures.bot`, `tests.dbio`, `tests.factories`

Тестов: 14

- `def _file(tmp_path, name: str, size: int=4)` (10)

### `tests/backend/test_bot_chat_send.py` — 186 строк

Следствия отправки сообщения HR из вкладки «Контакты».

Зависит от: `backend.models`, `tests.backend.fixtures.bot`, `tests.dbio`, `tests.factories`

Тестов: 11


### `tests/backend/test_bot_connect.py` — 159 строк

Следствия подъёма соединения с Telegram.

Зависит от: `backend.models`, `tests.backend.fixtures.backfill`, `tests.dbio`, `tests.fakes.ingestion`, `tests.fakes.telegram`

Тестов: 6


### `tests/backend/test_bot_dm_deletes.py` — 395 строк ⚠ подошёл к 300

Следствия удаления сообщения на стороне Telegram.

Зависит от: `backend.models`, `tests.dbio`, `tests.factories`, `tests.fakes.telegram_objects`

Тестов: 20

- `def _tombstone(msg_id: int, *, chat_id=777, username=None)` (6)
- `def _deletion_filter(client)` (7)

### `tests/backend/test_bot_dm_edits.py` — 247 строк

Следствия правки сообщения, пришедшей из Telegram.

Зависит от: `backend.models`, `tests.dbio`, `tests.factories`, `tests.fakes.telegram_objects`

Тестов: 13

- `def _edit(*, chat_id=777, username=None, msg_id=10, text='новая редакция', mine=False)` (12)

### `tests/backend/test_bot_dm_incoming.py` — 120 строк

Следствия входящего сообщения от HR.

Зависит от: `backend.models`, `tests.fakes.telegram_objects`

Тестов: 6

- `def dm_reader(monkeypatch)` (18)
  - `class Reader(list)` (6)
    - `async def __call__(self, msg, *_args, **_kwargs)` (3)

### `tests/backend/test_bot_dm_outgoing.py` — 281 строк

Следствия сообщения, отправленного HR с телефона или другого клиента.

Зависит от: `backend.models`, `tests.dbio`, `tests.factories`, `tests.fakes.telegram`, `tests.fakes.telegram_objects`

Тестов: 14


### `tests/backend/test_bot_logout.py` — 39 строк

Следствия выхода из учётной записи Telegram.

Зависит от: `tests.fakes.telegram`

Тестов: 2


### `tests/backend/test_bot_media_download.py` — 121 строк

Следствия скачивания вложения из входящего сообщения.

Зависит от: `backend.bot.media`, `tests.fakes.telegram`, `tests.fakes.telegram_objects`

Тестов: 8


### `tests/backend/test_bot_media_paths.py` — 145 строк

Следствия выбора способа отправки файла и места для скачанного.

Зависит от: `backend.bot.media`, `tests.factories`, `tests.fakes.telegram_objects`

Тестов: 10


### `tests/backend/test_bot_menu_actions.py` — 183 строк

Следствия команд из меню карточки вакансии.

Зависит от: `tests.fakes.ingestion`

Тестов: 12


### `tests/backend/test_bot_mode_reading.py` — 38 строк

Откуда бот берёт свой режим.

Зависит от: `backend.bot`, `backend.models`, `tests.backend.fixtures.bot`

Тестов: 2


### `tests/backend/test_bot_poll_slot.py` — 229 строк

Следствия ручного прогона, запущенного кнопкой окна.

Зависит от: `backend.models`, `tests.backend.fixtures.bot`, `tests.fakes.ingestion`, `tests.waiting`

Тестов: 16

- `def launched(monkeypatch) -> list` (9)
  - `async def seek_all(bot, kit)` (2)

### `tests/backend/test_bot_read_receipts.py` — 390 строк ⚠ подошёл к 300

Следствия отметок о прочтении — своих и чужих.

Зависит от: `backend.models`, `tests.dbio`, `tests.factories`, `tests.fakes.telegram`

Тестов: 22

- `def _outbox_read(user_id: int, max_id: int)` (5)

### `tests/backend/test_bot_run_loop.py` — 429 строк ⚠ подошёл к 300

Следствия одного оборота главного цикла бота.

Зависит от: `backend.bot`, `backend.models`, `tests.fakes.ingestion`, `tests.fakes.telegram`

Тестов: 25

- `async def _one_turn(chatting, mode, ingestion=None)` (9)

### `tests/backend/test_bot_session_string.py` — 84 строк

Следствия сверки строки сессии при запуске.

Зависит от: `backend.bot`, `tests.factories`, `tests.fakes.telegram`

Тестов: 4


### `tests/backend/test_bot_shared_provider.py` — 47 строк

Когда чат и векторы делят одно соединение с языковой моделью.

Зависит от: `backend.bot.client`, `backend.provider_config`

Тестов: 1

- `def _provider(base_url='http://a', api_key='ключ', model='qwen')` (3)

### `tests/backend/test_bot_signals.py` — 160 строк

Следствия сигналов, приходящих боту из чужого потока.

Зависит от: —

Тестов: 9

- `def closed_loop()` (5)

### `tests/backend/test_bot_slot.py` — 116 строк

Место прогона, занятое отдельной задачей: цикл бота не ждёт её, место держится до конца.

Зависит от: `backend.bot`, `tests.backend.fixtures.bot`

Тестов: 6


### `tests/backend/test_bot_turn.py` — 119 строк

Оборот одной задачей: недоразобранное, каналы, агрегаторы — и отклик на наборе этой работы.

Зависит от: `backend.agent.stops`, `backend.bot`, `backend.bot.turn`, `tests.fakes.agent`, `tests.waiting`

Тестов: 7

- `def bot_with_turn(make_bot, monkeypatch)` (27)
  - `async def build(*, channels_hang=False)` (21)
    - `async def recover()` (3)
    - `async def channels()` (4)
    - `async def seek_all(_bot, kit)` (2)

### `tests/backend/test_bot_update.py` — 64 строк

Скачивание обновления в месте прогона: ход идёт в полосу, занятое место — отказ.

Зависит от: `backend.bot.update`, `tests.fakes.github_release`

Тестов: 3

- `def _app_in(monkeypatch, tmp_path)` (4)
- `def handed(monkeypatch)` (5)

### `tests/backend/test_crypto.py` — 133 строк

Следствия шифрования секретов в `backend/crypto.py`.

Зависит от: `backend.crypto`

Тестов: 13


### `tests/backend/test_db_engine.py` — 93 строк

Следствия настроек, которые ставятся на каждое соединение с базой.

Зависит от: `adapters.db`

Тестов: 5

- `async def engine_on_disk(tmp_path)` (5)
- `async def _pragma(engine, name)` (4)

### `tests/backend/test_domain_apply_order.py` — 91 строк

Порядок способов отклика: Telegram, кнопка агрегатора, форма, почта.

Зависит от: `backend.domain.apply_order`, `tests.factories_aggregators`

Тестов: 13

- `def _vacancy(**over) -> VacancyFacts` (3)
- `def _world(**over) -> World` (3)

### `tests/backend/test_domain_blacklist.py` — 45 строк

Следствия, которые наблюдают тесты `backend/domain/blacklist.py`.

Зависит от: `backend.domain.blacklist`

Тестов: 7


### `tests/backend/test_domain_company_names.py` — 98 строк

Заглавная буква в названии компании.

Зависит от: `backend.domain.company_names`

Тестов: 7


### `tests/backend/test_domain_contact_keys.py` — 53 строк

Нормальная форма контакта вакансии: по ней два написания одного контакта

Зависит от: `backend.domain.contact_keys`

Тестов: 6


### `tests/backend/test_domain_dedup.py` — 68 строк

Следствия, которые наблюдают тесты поиска похожего вектора.

Зависит от: `backend.domain.dedup`

Тестов: 8


### `tests/backend/test_domain_embedding_cache.py` — 122 строк

Следствия кэша отпечатков, по которым отсеиваются повторы вакансий.

Зависит от: `backend.domain.dedup`

Тестов: 10


### `tests/backend/test_domain_fit_fields.py` — 68 строк

Следствия заслонов по полям-перечислениям: грейд и формат работы.

Зависит от: `backend.domain.fit_fields`

Тестов: 9


### `tests/backend/test_domain_hosts.py` — 98 строк

Адрес, разобранный на хост и остаток: по хосту сравнивают сайты, по остатку —

Зависит от: `backend.domain.hosts`

Тестов: 17


### `tests/backend/test_domain_salary.py` — 435 строк ⚠ подошёл к 300

Следствия, которые наблюдают тесты `backend/domain/salary.py`.

Зависит от: `backend.domain.salary`

Тестов: 33


### `tests/backend/test_domain_salary_numbers.py` — 176 строк

Следствия чтения самого числа в строке зарплаты.

Зависит от: `backend.domain.salary`

Тестов: 16


### `tests/backend/test_domain_scoring.py` — 175 строк

Следствия, которые наблюдают тесты `backend/domain/scoring.py`.

Зависит от: `backend.domain.scoring`, `tests.factories`

Тестов: 20


### `tests/backend/test_domain_sentence.py` — 20 строк

Законченная фраза: точка в конце, если своего знака конца нет.

Зависит от: `backend.domain.sentence`

Тестов: 1


### `tests/backend/test_domain_tenure.py` — 29 строк

Сроки мест работы: период, полные годы, стаж по навыку.

Зависит от: `backend.domain.tenure`, `tests.fakes.agent`

Тестов: 4

- `def _place(start, end=None)` (2)

### `tests/backend/test_domain_transitions.py` — 130 строк

Следствия, которые наблюдают тесты `backend/domain/transitions.py`.

Зависит от: `backend.domain.transitions`, `backend.models`

Тестов: 10

- `def ways_out(status: VacancyStatus) -> list[VacancyStatus]` (3)

### `tests/backend/test_domain_verdict.py` — 65 строк

Следствия, которые наблюдают тесты `backend/domain/verdict.py`.

Зависит от: `backend.domain.verdict`, `backend.models`, `tests.factories`

Тестов: 9


### `tests/backend/test_domain_wording.py` — 19 строк

Написание стоит в тексте словом, а не куском чужого слова.

Зависит от: `backend.domain.wording`

Тестов: 4


### `tests/backend/test_entry_point.py` — 199 строк

Следствия запуска приложения из единственной точки входа.

Зависит от: `backend.single_instance`

Тестов: 10

- `def shown(monkeypatch)` (7)

### `tests/backend/test_entry_point_log.py` — 303 строк ⚠ подошёл к 300

Следствия журнала приложения: файл, поворот, кодировка и падения.

Зависит от: `config`

Тестов: 11

- `def _write_through(module, text: str) -> str` (22)

### `tests/backend/test_flows_aggregator_name.py` — 150 строк

Имя агрегатора: как сервис зовут люди, а не его адрес.

Зависит от: `backend.flows.aggregator_name`, `backend.models`, `backend.provider_config`, `tests.dbio`, `tests.factories_aggregators`, `tests.fakes.llm`, `tests.fakes.site_home`

Тестов: 13

- `def _model_says(monkeypatch, answer: httpx.Response | BaseException) -> list` (5)
- `async def _name_of_created(session_factory, chat: LlmProviderConfig | None) -> str` (4)
- `def _image(body: bytes=_ICON) -> httpx.Response` (2)

### `tests/backend/test_flows_aggregator_seek.py` — 212 строк

Обход источника: искатель находит, конвейер разбирает, отобранное уходит

Зависит от: `backend.agent.jobs`, `backend.agent.stops`, `backend.flows.aggregator_round`, `backend.models`, `tests.backend.fixtures.flows`, `tests.backend.fixtures.parse_stub`, `tests.dbio`, `tests.factories`, `tests.factories_aggregators`, `tests.fakes.agent`

Тестов: 13

- `def parsed(monkeypatch)` (5)
- `def seek(make_pipeline, session_factory)` (16)
  - `async def run(steps, human_limit=3600.0, on_kit=None, **source)` (10)
- `async def _submit(tools, url=PAGE)` (2)
- `async def _submit_and_finish(tools)` (3)

### `tests/backend/test_flows_backfill_deletes.py` — 162 строк

Следствия сверки удалённого при догоне переписки.

Зависит от: `backend.models`, `tests.backend.fixtures.backfill`, `tests.dbio`, `tests.factories`, `tests.fakes.telegram`

Тестов: 5

- `class _WritesWhileReading(FakeTelegramClient)` (18)
  - `async def get_chat_history(self, target, limit=100)` (4)

### `tests/backend/test_flows_candidate_profile.py` — 95 строк

Следствия сборки среза профиля для проверки вакансии на пригодность.

Зависит от: `backend.llm.candidate`, `backend.models`, `tests.factories`

Тестов: 5


### `tests/backend/test_flows_catch_up.py` — 274 строк

Следствия догона переписок по всем HR разом.

Зависит от: `backend.domain.telegram_identity`, `backend.flows.dm_backfill`, `backend.models`, `tests.backend.fixtures.backfill`, `tests.dbio`, `tests.factories`, `tests.fakes.telegram`

Тестов: 10

- `async def _catch_up(session_factory, **kwargs)` (3)
- `async def _hrs(session_factory, count)` (10)

### `tests/backend/test_flows_channel_cursor.py` — 117 строк

Следствия отметки о разобранном и признака недоразобранной вакансии.

Зависит от: `backend.flows`, `backend.models`, `tests.dbio`, `tests.factories`

Тестов: 7


### `tests/backend/test_flows_channel_metadata.py` — 310 строк ⚠ подошёл к 300

Следствия обновления названий и картинок каналов.

Зависит от: `backend.flows`, `backend.models`, `tests.dbio`, `tests.factories`, `tests.fakes.telegram`, `tests.fakes.telegram_objects`

Тестов: 15

- `async def _channels(session_factory, *rows)` (4)

### `tests/backend/test_flows_channel_reading.py` — 331 строк ⚠ подошёл к 300

Следствия чтения новых сообщений одного канала.

Зависит от: `backend.flows`, `backend.models`, `tests.dbio`, `tests.factories`, `tests.fakes.telegram`, `tests.fakes.telegram_objects`

Тестов: 15

- `async def reading(monkeypatch, make_pipeline, session_factory)` (13)
  - `async def take(pipeline, channel_id, username, msg)` (2)

### `tests/backend/test_flows_channel_walk.py` — 377 строк ⚠ подошёл к 300

Следствия обхода каналов за один цикл.

Зависит от: `backend.agent.stops`, `backend.flows`, `backend.models`, `tests.dbio`, `tests.factories`, `tests.fakes.telegram`, `tests.fakes.telegram_objects`

Тестов: 19

- `async def walking(monkeypatch, make_pipeline)` (22)
  - `async def reload()` (2)
  - `async def poll(pipeline, channel_id, username, last_id)` (3)

### `tests/backend/test_flows_dm_buffer.py` — 190 строк

Следствия накопления входящих перед разбором ответа HR.

Зависит от: `backend.payloads`

Тестов: 10

- `def _texts(pipeline, hr_id)` (3)

### `tests/backend/test_flows_dm_debounce.py` — 229 строк

Договор копилки отложенного разбора: пачки, таймеры и начавшие.

Зависит от: `backend.flows.dm_debounce`

Тестов: 16

- `def _letter(tg_msg_id: int, text: str) -> dict` (15)

### `tests/backend/test_flows_dm_drain.py` — 272 строк

Следствия гашения отложенных разборов при остановке и выключении.

Зависит от: `backend.flows`, `backend.payloads`

Тестов: 13

- `def _outlasts_the_wait(started: asyncio.Event)` (13)
  - `async def reading(pipeline, hr_id)` (4)

### `tests/backend/test_flows_embedding_cache.py` — 117 строк

Подъём кэша векторов из базы — то, чем занят сам конвейер.

Зависит от: `backend.flows`, `backend.models`, `tests.dbio`, `tests.factories`

Тестов: 5


### `tests/backend/test_flows_embedding_text.py` — 132 строк

Отпечаток текста: что бывает, когда поставщик отпечатков не отвечает.

Зависит от: `adapters`, `backend.flows`, `tests.fakes.gguf`, `tests.fakes.llm`

Тестов: 5

- `class _Provider` (8)
  - `async def post(self, *_args, **_kwargs)` (2)
- `class _Pipeline` (6)

### `tests/backend/test_flows_empty_vacancy.py` — 376 строк ⚠ подошёл к 300

Следствия сохранения объявления, из которого нечего было взять.

Зависит от: `backend.domain.verdict`, `backend.flows`, `backend.flows.handover`, `backend.models`, `tests.backend.fixtures.flows`, `tests.dbio`, `tests.factories`, `tests.fakes.telegram`

Тестов: 16

- `async def emptied(make_pipeline, session_factory)` (20)
- `def caught_backfills(monkeypatch)` (9)
  - `async def backfill(hr_row_, *args, **kwargs)` (2)

### `tests/backend/test_flows_ghosting_timer.py` — 181 строк

Следствия проверки на молчание HR.

Зависит от: `backend.models`, `tests.dbio`, `tests.factories`

Тестов: 8

- `def _long_ago()` (3)
- `def _recently()` (3)

### `tests/backend/test_flows_handover.py` — 98 строк

Сбор отдаёт откликателю: годная после вердикта вакансия уходит отклику, догон

Зависит от: `backend.flows`, `backend.flows.handover`, `backend.models`, `tests.dbio`, `tests.factories`

Тестов: 9

- `async def _set_status(session_factory, vacancy_id, status)` (4)

### `tests/backend/test_flows_history_backfill.py` — 396 строк ⚠ подошёл к 300

Следствия догона переписки с одним HR.

Зависит от: `backend.flows.dm`, `backend.flows.dm_backfill`, `backend.models`, `tests.backend.fixtures.backfill`, `tests.dbio`, `tests.factories`, `tests.fakes.telegram`, `tests.fakes.telegram_objects`

Тестов: 17


### `tests/backend/test_flows_hr_backfill_spawn.py` — 152 строк

Следствия фонового догона переписки со свежезаведённым HR.

Зависит от: `backend.flows`, `backend.models`, `tests.dbio`, `tests.factories`

Тестов: 6

- `async def spawning(make_pipeline, session_factory, monkeypatch)` (21)
  - `async def backfill(hr_row_, dm, hooks, **kwargs)` (5)

### `tests/backend/test_flows_incoming_attribution.py` — 412 строк ⚠ подошёл к 300

К какой вакансии бот относит письмо HR и что делает дальше.

Зависит от: `backend.models`, `backend.payloads`, `backend.repository.messages`, `backend.repository.vacancies_life`, `tests.dbio`, `tests.factories`, `tests.fakes.telegram_objects`

Тестов: 13

- `async def _two_vacancies(session_factory)` (39)
- `async def _one_vacancy(session_factory, *, title, status)` (19)
- `async def _their_letters(session_factory) -> list` (3)
- `def _ignore(*args)` (6)

### `tests/backend/test_flows_incoming_gate.py` — 335 строк ⚠ подошёл к 300

Кого бот слушает во входящих личных сообщениях, а кого нет.

Зависит от: `backend.bot.media`, `backend.models`, `tests.dbio`, `tests.factories`, `tests.fakes.telegram`, `tests.fakes.telegram_objects`

Тестов: 18


### `tests/backend/test_flows_linked_article.py` — 164 строк

Следствия, которые наблюдает тест `backend/flows/linked_article.py`.

Зависит от: `adapters`, `backend.flows`

Тестов: 8

- `def fetched(monkeypatch)` (11)
  - `async def fetch_article(_client, url)` (3)

### `tests/backend/test_flows_new_vacancy.py` — 442 строк ⚠ подошёл к 300

Следствия заведения строки под новое объявление.

Зависит от: `adapters`, `backend.flows`, `backend.models`, `backend.payloads`, `tests.backend.fixtures.flows`, `tests.backend.fixtures.parse_stub`, `tests.backend.fixtures.rerun`, `tests.dbio`, `tests.factories`, `tests.fakes.telegram_objects`

Тестов: 21

- `def parses(monkeypatch)` (10)
- `async def _orphan_waiting_for_an_article(session_factory, created_at=None)` (15)

### `tests/backend/test_flows_parse_blockers.py` — 149 строк

Порядок заслонов пригодности: сперва бесплатные, потом платные.

Зависит от: `backend.flows`, `backend.llm.candidate`, `backend.models`, `backend.payloads`, `tests.dbio`

Тестов: 7


### `tests/backend/test_flows_parse_contacts.py` — 204 строк

Контакт, найденный разбором, ложится контактом вакансии, а заметки остаются

Зависит от: `backend.flows`, `backend.models`, `backend.repository.vacancies_card`, `backend.repository.vacancy_contacts`, `tests.dbio`, `tests.factories`, `tests.factories_aggregators`

Тестов: 9

- `async def _contacts(session_factory) -> list[tuple[str, str, str]]` (3)

### `tests/backend/test_flows_parse_persist.py` — 291 строк

Что остаётся в базе после разбора объявления.

Зависит от: `backend.flows`, `backend.models`, `backend.payloads`, `tests.dbio`, `tests.factories`

Тестов: 12


### `tests/backend/test_flows_parse_queue.py` — 39 строк

Очередь разбора: найденное агентом разбирается рядом с поиском, по одной.

Зависит от: `backend.flows.parse_queue`, `tests.backend.fixtures.parse_stub`

Тестов: 3


### `tests/backend/test_flows_parse_unanswered.py` — 152 строк

Что становится с объявлением, когда модель не дала ответа.

Зависит от: `adapters.lm_chat`, `backend.domain.verdict`, `backend.flows`, `backend.llm.answers`, `backend.models`, `tests.dbio`

Тестов: 6


### `tests/backend/test_flows_parse_verdict.py` — 452 строк ⚠ подошёл к 300

Какой приговор получает объявление после разбора.

Зависит от: `backend.flows`, `backend.llm.rules`, `backend.models`, `backend.payloads`, `backend.repository.blacklist_marks`, `tests.dbio`, `tests.factories`, `tests.factories_aggregators`

Тестов: 24

- `async def _barred(session_factory, vacancy_id: int, source_url: str | None) -> None` (6)

### `tests/backend/test_flows_pasted_intake.py` — 267 строк

Что бот делает с объявлением, вставленным человеком.

Зависит от: `backend.flows`, `backend.models`, `tests.backend.fixtures.flows`, `tests.dbio`, `tests.factories`

Тестов: 13

- `async def intake(make_pipeline, monkeypatch, one_vector)` (28)
  - `async def reload_resources()` (5)
  - `async def parse(pipeline_arg, vacancy_id, text, username, *, allow_delete=True)` (9)
- `def parse_calls(intake) -> list[tuple]` (7)

### `tests/backend/test_flows_post_intake.py` — 314 строк ⚠ подошёл к 300

Что бот делает с очередным объявлением из канала.

Зависит от: `adapters`, `backend.flows`, `tests.backend.fixtures.flows`, `tests.backend.fixtures.parse_stub`, `tests.fakes.llm`, `tests.fakes.telegram_objects`

Тестов: 14

- `async def intake(make_pipeline, monkeypatch, one_vector)` (16)
  - `async def save(pipeline, post, embedding)` (3)

### `tests/backend/test_flows_reply_reading.py` — 327 строк ⚠ подошёл к 300

Следствия разбора накопленного ответа HR.

Зависит от: `backend.flows`, `backend.models`, `backend.payloads`, `backend.repository.vacancies_life`, `tests.dbio`, `tests.factories`

Тестов: 13

- `async def reading(make_pipeline, session_factory, monkeypatch)` (36)
  - `async def classify_hr_reply(text, status, client, model)` (5)
- `def _buffer(pipeline, hr, vacancy, message, *texts)` (11)

### `tests/backend/test_flows_rerun_fingerprint.py` — 174 строк

Отпечаток вакансии при повторном прогоне и кэш отсева повторов.

Зависит от: `adapters`, `backend.flows`, `backend.models`, `tests.backend.fixtures.rerun`, `tests.dbio`, `tests.fakes.telegram_objects`

Тестов: 7


### `tests/backend/test_flows_resources.py` — 153 строк

Следствия перезагрузки настроек перед обходом каналов.

Зависит от: `backend.models`, `tests.dbio`, `tests.factories`

Тестов: 9


### `tests/backend/test_flows_vacancy_removal.py` — 167 строк

Следствия удаления вакансии конвейером.

Зависит от: `backend.flows`, `backend.models`, `tests.dbio`, `tests.factories`

Тестов: 8

- `async def with_a_vacancy(make_pipeline, session_factory)` (22)

### `tests/backend/test_flows_vacancy_rerun.py` — 299 строк

Следствия повторного прогона вакансии кнопкой из карточки.

Зависит от: `adapters`, `backend.flows`, `backend.models`, `backend.repository.vacancy_status`, `tests.backend.fixtures.rerun`, `tests.dbio`, `tests.factories`, `tests.fakes.telegram_objects`

Тестов: 15


### `tests/backend/test_flows_window_hooks.py` — 43 строк

Следствия оповещений окна из конвейера.

Зависит от: —

Тестов: 2


### `tests/backend/test_health.py` — 120 строк

Следствия вопроса «живо ли то, на чём держится работа».

Зависит от: `adapters`, `backend.health`, `backend.provider_config`, `tests.fakes.gguf`

Тестов: 5

- `class Stopped` (5)
  - `def __call__(self)` (2)
- `class Bot` (3)
- `def _provider(monkeypatch, *, listed: list[str]) -> list[str]` (23)
  - `def answer(request: httpx.Request) -> httpx.Response` (5)

### `tests/backend/test_llm_agent_letter.py` — 100 строк

Письмо вне Telegram: пишет чат-модель, проверяет сверка фактов.

Зависит от: `backend.llm.agent_letter`, `backend.llm.rules`, `tests.fakes.llm`

Тестов: 10

- `def _ask(**over) -> LetterAsk` (5)

### `tests/backend/test_llm_classify_reply.py` — 274 строк

Следствия разбора ответа HR в новый статус вакансии.

Зависит от: `backend.llm.hr_reply`, `backend.models`, `tests.fakes.llm`

Тестов: 16

- `def _allowed_line(client) -> str` (9)
- `def _verdict(status: str, explanation: str | None=None) -> httpx.Response` (3)
- `async def _read(text, status, client, model='qwen')` (9)

### `tests/backend/test_llm_company_arbiter.py` — 342 строк ⚠ подошёл к 300

Следствия обращения к модели как к арбитру при сведении компаний.

Зависит от: `backend.llm.company`, `backend.llm.rules`, `tests.fakes.llm`

Тестов: 19

- `class _Candidate` (8)
- `def _answer(matched_id=None, reasoning=None) -> httpx.Response` (3)
- `async def _ask(client, candidates, name='Сбербанк Тех', website=None)` (9)

### `tests/backend/test_llm_cover_letter.py` — 402 строк ⚠ подошёл к 300

Следствия составления письма-отклика.

Зависит от: `backend.llm.cover_letter`, `tests.factories`, `tests.fakes.llm`

Тестов: 24

- `def _client(letter: str, *, finish_reason: str='stop', factcheck=None)` (10)
- `async def _written(*args, **kwargs)` (10)

### `tests/backend/test_llm_cv_grounding.py` — 383 строк ⚠ подошёл к 300

Следствия сверки разобранного резюме с его же текстом.

Зависит от: `backend.llm.cv_grounding`, `backend.payloads`, `tests.factories_cv`

Тестов: 27


### `tests/backend/test_llm_cv_grounding_stack.py` — 282 строк

Что в разобранных местах работы и проектах не подтверждается текстом резюме.

Зависит от: `backend.llm.cv_grounding`, `tests.factories_cv`

Тестов: 14


### `tests/backend/test_llm_cv_items.py` — 270 строк

Следствия разбора навыков, опыта работы и проектов в `backend/llm/cv.py`.

Зависит от: `backend.llm.cv`, `tests.factories`, `tests.fakes.llm`

Тестов: 27

- `async def parse_sections(**sections)` (4)
- `async def only(section: str, item: dict)` (6)
- `async def one_skill(**fields)` (2)
- `async def one_job(**fields)` (3)
- `async def one_project(**fields)` (2)

### `tests/backend/test_llm_cv_native.py` — 119 строк

Следствия правила «родной язык у разобранной анкеты есть всегда».

Зависит от: `backend.llm.cv_native`, `backend.payloads`, `tests.factories_cv`

Тестов: 9


### `tests/backend/test_llm_cv_profile.py` — 362 строк ⚠ подошёл к 300

Следствия разбора профиля и языков в `backend/llm/cv.py`.

Зависит от: `backend.llm.cv`, `backend.models`, `tests.factories`, `tests.fakes.llm`

Тестов: 29

- `async def parse_answer(answer: str, text: str='резюме')` (8)
- `async def parse_profile(text: str='резюме', **fields)` (9)

### `tests/backend/test_llm_cv_response.py` — 204 строк

Следствия, которые наблюдает внешний слой `parse_cv`.

Зависит от: `backend.llm.cv`, `tests.factories`, `tests.fakes.llm`

Тестов: 17


### `tests/backend/test_llm_enum_values.py` — 31 строк

Следствия сверки значения со списком допустимых.

Зависит от: `backend.incoming`

Тестов: 1


### `tests/backend/test_llm_external.py` — 26 строк

Следствия подготовки чужого текста к вставке в промпт.

Зависит от: `backend.llm.external`

Тестов: 2


### `tests/backend/test_llm_factcheck.py` — 184 строк

Следствия второй проверки письма — сверки фактов с профилем.

Зависит от: `backend.llm.factcheck`, `tests.fakes.llm`

Тестов: 11


### `tests/backend/test_llm_fit_languages.py` — 163 строк

Следствия зова о языках вакансии.

Зависит от: `backend.llm.candidate`, `backend.llm.fit_languages`, `tests.backend.fixtures.fit`, `tests.factories`, `tests.fakes.llm`

Тестов: 7


### `tests/backend/test_llm_fit_validation.py` — 268 строк

Следствия общего у трёх зовов о пригодности.

Зависит от: `backend.llm.fit`, `backend.llm.fit_role`, `tests.backend.fixtures.fit`, `tests.factories`, `tests.fakes.llm`

Тестов: 16


### `tests/backend/test_llm_genre_answer.py` — 76 строк

Следствия ответа модели о жанре поста.

Зависит от: `backend.llm.genre`, `tests.fakes.llm`

Тестов: 5

- `async def _asked(answer: httpx.Response, text: str='Ищем в команду')` (3)

### `tests/backend/test_llm_json_extraction.py` — 275 строк

Следствия вырезания ответа-объекта из того, что вернула модель.

Зависит от: `backend.llm.answers`

Тестов: 18

- `async def _second_try(answer: str, finish: str='stop', **options)` (9)
  - `async def ask(room)` (2)

### `tests/backend/test_llm_profile_formatting.py` — 121 строк

Следствия подготовки сведений о кандидате для запроса к модели.

Зависит от: `backend.llm.candidate`

Тестов: 7

- `class _Skill` (6)

### `tests/backend/test_llm_stack_cleanup.py` — 326 строк ⚠ подошёл к 300

Следствия приведения названий технологий к единому виду.

Зависит от: `backend.llm.skills`

Тестов: 18


### `tests/backend/test_llm_vacancy_answer.py` — 375 строк ⚠ подошёл к 300

Следствия разбора ответа модели в разобранную вакансию.

Зависит от: `backend.llm.vacancy`, `tests.fakes.llm`

Тестов: 30

- `def _answer(**fields) -> str` (3)

### `tests/backend/test_llm_vacancy_request.py` — 306 строк ⚠ подошёл к 300

Следствия обращения к модели за разбором поста с вакансией.

Зависит от: `backend.llm.rules`, `backend.llm.vacancy`, `tests.fakes.llm`

Тестов: 17

- `def _parsed(**fields) -> httpx.Response` (3)

### `tests/backend/test_log_buffer.py` — 257 строк

Следствия кольца записей, которое показывает окну экран «Логи».

Зависит от: `backend.log_buffer`, `tests.backend.fixtures.logs`

Тестов: 16


### `tests/backend/test_log_file.py` — 44 строк

Следствия файла журнала: поворот по размеру и недоступный файл.

Зависит от: `backend.log_file`, `tests.backend.fixtures.logs`

Тестов: 1

- `def _busy(source, dest)` (3)

### `tests/backend/test_log_secrets.py` — 325 строк ⚠ подошёл к 300

Следствия вымарывания секретов и жалобы журнала на собственную беду.

Зависит от: `backend.log_buffer`, `backend.log_file`, `backend.log_secrets`, `tests.backend.fixtures.logs`

Тестов: 19

- `def _unbuildable()` (6)

### `tests/backend/test_message_text.py` — 151 строк

Следствия, которые наблюдают тесты `backend/message_text.py`.

Зависит от: `backend.message_text`, `tests.fakes.telegram_objects`

Тестов: 19


### `tests/backend/test_migration_aggregators.py` — 127 строк

Следствия схемной ревизии агрегаторов: что она заводит и что держит база.

Зависит от: `alembic`, `backend.bootstrap`, `backend.models`, `tests.conftest`, `tests.dbio`, `tests.factories`, `tests.factories_aggregators`

Тестов: 8


### `tests/backend/test_migration_apply_trail.py` — 36 строк

Ревизия следа откликов: одно событие отклика вместо пяти родов.

Зависит от: `alembic`, `backend.bootstrap`, `tests.dbio`

Тестов: 2

- `def _with_old_events(target) -> None` (5)

### `tests/backend/test_migration_engine.py` — 164 строк

Следствия того, каким движком alembic открывает базу и как его закрывает.

Зависит от: `alembic`, `backend.bootstrap`, `tests.conftest`, `tests.dbio`

Тестов: 4

- `def _learning_project(tmp_path, rebuild: str)` (14)
- `def _tenants(db_file) -> list[tuple]` (2)

### `tests/backend/test_notify.py` — 61 строк

Следствия, которые наблюдает оповещение окна `backend/notify.py`.

Зависит от: `backend.notify`

Тестов: 3


### `tests/backend/test_payloads_stack.py` — 53 строк

Следствия объединённого стека разобранной вакансии.

Зависит от: `tests.factories`

Тестов: 4


### `tests/backend/test_repository_agent_profile.py` — 166 строк

Анкета для агента: всё, на что опираются промпты, со стажем от кода.

Зависит от: `backend.llm.rules`, `backend.models`, `backend.repository.agent_profile`, `tests.dbio`, `tests.factories`, `tests.fakes.agent`

Тестов: 11

- `async def _person(session_factory, **fields)` (4)

### `tests/backend/test_repository_aggregator_blacklist.py` — 136 строк

Агрегатор в чёрном списке: запись по хосту, гашение, запрет включения и обхода.

Зависит от: `backend.models`, `backend.repository.aggregators`, `backend.repository.blacklist`, `backend.repository.blacklist_candidates`, `tests.dbio`, `tests.factories`, `tests.factories_aggregators`

Тестов: 10


### `tests/backend/test_repository_aggregators.py` — 110 строк

Ведение агрегаторов: заведение, включение, вход, удаление, порядок обхода.

Зависит от: `backend.models`, `backend.repository.aggregators`, `tests.dbio`, `tests.factories`, `tests.factories_aggregators`

Тестов: 10


### `tests/backend/test_repository_applications.py` — 127 строк

Отклик вне Telegram: строка, скрининг и Applied — одной транзакцией.

Зависит от: `backend.models`, `backend.repository.applications`, `tests.dbio`, `tests.factories`, `tests.factories_aggregators`

Тестов: 6

- `def _entry(vacancy_id, **over) -> ApplicationEntry` (6)
- `async def _record(session, entry)` (3)

### `tests/backend/test_repository_blacklist_adding.py` — 150 строк

Следствия заведения строки чёрного списка.

Зависит от: `backend.models`, `backend.repository.blacklist`, `tests.dbio`, `tests.factories`

Тестов: 9


### `tests/backend/test_repository_blacklist_candidates.py` — 209 строк

Следствия сбора подсказок для окна добавления в чёрный список.

Зависит от: `backend.repository.blacklist_candidates`, `tests.dbio`, `tests.factories`

Тестов: 10


### `tests/backend/test_repository_blacklist_editing.py` — 104 строк

Следствия правки значения и причины у строки чёрного списка.

Зависит от: `backend.models`, `backend.repository.blacklist`, `tests.dbio`, `tests.factories`

Тестов: 6


### `tests/backend/test_repository_blacklist_listing.py` — 31 строк

Следствия порядка в списке чёрного списка на экране.

Зависит от: `backend.repository.blacklist`, `tests.dbio`, `tests.factories`

Тестов: 1


### `tests/backend/test_repository_blacklist_matcher_values.py` — 61 строк

Следствия отбора значений, по которым отсеивают вакансии.

Зависит от: `backend.repository.blacklist_marks`, `tests.dbio`, `tests.factories`

Тестов: 3


### `tests/backend/test_repository_blacklist_removal.py` — 30 строк

Следствия удаления строки чёрного списка.

Зависит от: `backend.models`, `backend.repository.blacklist`, `tests.dbio`, `tests.factories`

Тестов: 2


### `tests/backend/test_repository_blacklist_switching.py` — 87 строк

Следствия гашения и включения строки чёрного списка.

Зависит от: `backend.models`, `backend.repository.blacklist`, `tests.dbio`, `tests.factories`

Тестов: 5


### `tests/backend/test_repository_bot_mode.py` — 55 строк

Следствия чтения и записи режима бота.

Зависит от: `backend.models`, `backend.repository.bot_mode`, `tests.dbio`, `tests.factories`

Тестов: 4


### `tests/backend/test_repository_channel_cursor.py` — 27 строк

Следствия сброса отметки разобранного у канала.

Зависит от: `backend.models`, `backend.repository.channels`, `tests.dbio`, `tests.factories`

Тестов: 2


### `tests/backend/test_repository_channel_detail.py` — 246 строк

Следствия сборки карточки канала с воронкой отбора.

Зависит от: `backend.domain.funnel`, `backend.models`, `backend.repository.channels`, `tests.dbio`, `tests.factories`

Тестов: 9


### `tests/backend/test_repository_channel_list_filter.py` — 48 строк

Следствия отбора по строке в списке каналов.

Зависит от: `tests.dbio`, `tests.factories`

Тестов: 3


### `tests/backend/test_repository_channel_list_order.py` — 76 строк

Следствия порядка в списке каналов-источников.

Зависит от: `tests.dbio`, `tests.factories`

Тестов: 4


### `tests/backend/test_repository_channel_list_rows.py` — 49 строк

Следствия наполнения строки списка каналов.

Зависит от: `backend.repository.channels`, `tests.dbio`, `tests.factories`

Тестов: 2


### `tests/backend/test_repository_channel_lookup.py` — 33 строк

Следствия поиска канала по нику.

Зависит от: `backend.repository.channels`, `tests.dbio`, `tests.factories`

Тестов: 2


### `tests/backend/test_repository_channel_marks.py` — 25 строк

Следствия записи канала в чёрный список.

Зависит от: `backend.repository.blacklist_marks`, `backend.repository.channels`, `tests.factories`

Тестов: 2


### `tests/backend/test_repository_channel_removal.py` — 58 строк

Следствия удаления канала-источника.

Зависит от: `backend.models`, `backend.repository.channels`, `tests.dbio`, `tests.factories`

Тестов: 2


### `tests/backend/test_repository_channel_switching.py` — 105 строк

Следствия управления включённостью канала.

Зависит от: `backend.models`, `backend.repository.channels`, `tests.dbio`, `tests.factories`

Тестов: 7

- `async def _listed_and_clean(session_factory, *, is_active: bool)` (11)

### `tests/backend/test_repository_company_autolink_llm.py` — 240 строк

Следствия обращения к языковой модели при сведении компаний.

Зависит от: `backend.repository.companies_matching`, `tests.dbio`, `tests.factories`

Тестов: 9

- `class Arbiter` (21)
  - `async def __call__(self, client, model, *, parsed_name, parsed_website, candidates)` (13)
- `def arbiter(monkeypatch)` (14)
  - `def install(**kwargs) -> Arbiter` (4)
- `async def resolve(session, name, arbiter_fake=None, **kwargs)` (9)

### `tests/backend/test_repository_company_autolink_rules.py` — 438 строк ⚠ подошёл к 300

Следствия автоматического сведения разобранной компании к существующей.

Зависит от: `backend.models`, `backend.repository.companies_matching`, `tests.dbio`, `tests.factories`

Тестов: 22


### `tests/backend/test_repository_company_blacklist_marks.py` — 132 строк

Следствия переезда отметки чёрного списка вслед за именем компании.

Зависит от: `backend.models`, `backend.repository.companies_card`, `tests.dbio`, `tests.factories`

Тестов: 5


### `tests/backend/test_repository_company_card.py` — 130 строк

Следствия сборки карточки компании для боковой панели контактов.

Зависит от: `backend.repository.blacklist_marks`, `backend.repository.companies_card`, `backend.repository.hr_list`, `tests.dbio`, `tests.factories`

Тестов: 7


### `tests/backend/test_repository_company_creation.py` — 78 строк

Следствия заведения компании вручную.

Зависит от: `backend.repository.companies_card`

Тестов: 6


### `tests/backend/test_repository_company_edits.py` — 129 строк

Следствия правки полей компании.

Зависит от: `backend.repository.companies_card`, `tests.dbio`, `tests.factories`

Тестов: 8


### `tests/backend/test_repository_company_keys.py` — 225 строк

Следствия приведения имени и сайта компании к сравнимому виду.

Зависит от: `backend.domain.company_hosts`, `backend.domain.hosts`, `backend.repository.companies_keys`

Тестов: 11


### `tests/backend/test_repository_company_list.py` — 158 строк

Следствия сборки списка компаний со счётчиками.

Зависит от: `backend.repository.companies_list`, `tests.dbio`, `tests.factories`

Тестов: 9

- `async def names(session, **kwargs) -> list[str]` (4)

### `tests/backend/test_repository_company_merge.py` — 202 строк

Следствия слияния двух записей об одной компании.

Зависит от: `backend.models`, `backend.repository.companies_card`, `tests.dbio`, `tests.factories`

Тестов: 12


### `tests/backend/test_repository_company_removal.py` — 44 строк

Следствия удаления компании.

Зависит от: `backend.models`, `backend.repository.companies_card`, `tests.dbio`, `tests.factories`

Тестов: 2


### `tests/backend/test_repository_hr_attribution.py` — 248 строк

Следствия привязки ответа HR к вакансии, о которой он пишет.

Зависит от: `backend.repository.hr_identify`, `tests.dbio`, `tests.factories`

Тестов: 9


### `tests/backend/test_repository_hr_blacklist_marks.py` — 262 строк

Следствия сопоставления HR со строками чёрного списка.

Зависит от: `backend.models`, `backend.repository.blacklist_marks`, `backend.repository.hr_card`, `backend.repository.hr_identify`, `tests.dbio`, `tests.factories`, `tests.fakes.telegram`

Тестов: 14


### `tests/backend/test_repository_hr_card.py` — 117 строк

Следствия сборки карточки HR для боковой панели контактов.

Зависит от: `backend.repository.hr_card`, `tests.dbio`, `tests.factories`

Тестов: 6


### `tests/backend/test_repository_hr_creation.py` — 39 строк

Следствия заведения HR вручную с экрана контактов.

Зависит от: `backend.repository.hr_card`, `backend.repository.hr_identify`

Тестов: 2


### `tests/backend/test_repository_hr_edits.py` — 147 строк

Следствия правки полей HR.

Зависит от: `backend.repository.hr_card`, `tests.dbio`, `tests.factories`

Тестов: 9


### `tests/backend/test_repository_hr_identity.py` — 140 строк

Следствия опознания отправителя входящего сообщения.

Зависит от: `backend.models`, `backend.repository.hr_identify`, `tests.dbio`, `tests.factories`, `tests.fakes.telegram_objects`

Тестов: 7


### `tests/backend/test_repository_hr_letter_history.py` — 104 строк

Следствия подсчёта писем, отправленных HR за последнее время.

Зависит от: `backend.repository.hr_identify`, `tests.dbio`, `tests.factories`

Тестов: 4


### `tests/backend/test_repository_hr_list_catchup.py` — 25 строк

Следствия перечней, с которых бот догоняет пропущенное после простоя.

Зависит от: `backend.repository.hr_list`, `tests.dbio`, `tests.factories`

Тестов: 1


### `tests/backend/test_repository_hr_list_filter.py` — 81 строк

Следствия отбора по строке и постраничности в списке HR.

Зависит от: `tests.dbio`, `tests.factories`

Тестов: 5


### `tests/backend/test_repository_hr_list_order.py` — 92 строк

Следствия порядка в списке HR.

Зависит от: `tests.dbio`, `tests.factories`

Тестов: 5


### `tests/backend/test_repository_hr_list_rows.py` — 148 строк

Следствия наполнения строки списка HR.

Зависит от: `backend.repository.hr_list`, `tests.dbio`, `tests.factories`

Тестов: 5


### `tests/backend/test_repository_hr_merge.py` — 208 строк

Следствия слияния двух записей об одном человеке.

Зависит от: `backend.models`, `backend.repository.hr_card`, `tests.dbio`, `tests.factories`

Тестов: 11


### `tests/backend/test_repository_hr_removal.py` — 96 строк

Следствия удаления записи об HR.

Зависит от: `backend.models`, `backend.repository.hr_card`, `tests.dbio`, `tests.factories`

Тестов: 4


### `tests/backend/test_repository_hr_upsert.py` — 154 строк

Следствия опознания или заведения HR по данным из Telegram.

Зависит от: `backend.repository.hr_identify`, `tests.dbio`, `tests.factories`, `tests.fakes.telegram_objects`

Тестов: 9


### `tests/backend/test_repository_mail_account.py` — 93 строк

Почта для откликов: пароль лежит шифром, популярные почты настраиваются сами.

Зависит от: `backend.log_secrets`, `backend.models`, `backend.repository.mail_account`, `tests.backend.fixtures.logs`, `tests.dbio`

Тестов: 10


### `tests/backend/test_repository_message_changes.py` — 116 строк

Следствия того, что репозиторий делает с уже сохранённой строкой переписки.

Зависит от: `backend.models`, `backend.repository.messages`, `tests.dbio`, `tests.factories`

Тестов: 5


### `tests/backend/test_repository_message_paging.py` — 201 строк

Следствия чтения переписки страницами.

Зависит от: `backend.repository.messages`, `tests.dbio`, `tests.factories`

Тестов: 9

- `async def texts(session, hr_id, **kwargs) -> tuple[list[str], bool]` (4)

### `tests/backend/test_repository_message_saving.py` — 69 строк

Следствия сохранения входящего сообщения.

Зависит от: `backend.payloads`, `backend.repository.messages`, `tests.dbio`, `tests.factories`

Тестов: 2


### `tests/backend/test_repository_message_unread.py` — 142 строк

Следствия подсчёта непрочитанных входящих сообщений.

Зависит от: `backend.repository.hr_list`, `backend.repository.messages`, `tests.dbio`, `tests.factories`

Тестов: 7


### `tests/backend/test_repository_profile_block.py` — 225 строк

Следствия сборки блока «Информация о кандидате» для письма-отклика.

Зависит от: `backend.repository.profile_block`, `tests.dbio`, `tests.factories`

Тестов: 13


### `tests/backend/test_repository_profile_cv_saving.py` — 337 строк ⚠ подошёл к 300

Следствия записи разобранного резюме в профиль.

Зависит от: `backend.models`, `backend.payloads`, `backend.repository.profile`, `backend.repository.profile_cv`, `backend.repository.profile_experience`, `backend.repository.profile_projects`, `backend.repository.profile_skills`, `tests.dbio`, `tests.factories`, `tests.factories_cv`

Тестов: 16


### `tests/backend/test_repository_profile_experience.py` — 283 строк

Следствия сохранения мест работы профиля.

Зависит от: `backend.models`, `backend.repository.profile_experience`, `backend.repository.profile_records`, `tests.dbio`, `tests.factories`

Тестов: 14

- `def _row(**overrides) -> dict` (5)

### `tests/backend/test_repository_profile_fields.py` — 62 строк

Следствия чтения и записи основных полей профиля.

Зависит от: `backend.repository.profile`, `backend.repository.profile_skills`, `tests.dbio`, `tests.factories`

Тестов: 5


### `tests/backend/test_repository_profile_languages.py` — 67 строк

Следствия замены списка языков профиля.

Зависит от: `backend.repository.profile_languages`, `tests.dbio`, `tests.factories`

Тестов: 4


### `tests/backend/test_repository_profile_projects.py` — 74 строк

Следствия сохранения проектов профиля.

Зависит от: `backend.repository.profile_experience`, `backend.repository.profile_projects`, `backend.repository.profile_records`, `tests.dbio`, `tests.factories`

Тестов: 4


### `tests/backend/test_repository_profile_skills.py` — 306 строк ⚠ подошёл к 300

Следствия сохранения списка навыков профиля.

Зависит от: `backend.models`, `backend.repository.profile_skills`, `tests.dbio`, `tests.factories`

Тестов: 14

- `async def names_and_levels(session) -> list[tuple[str, int]]` (3)

### `tests/backend/test_repository_stats_breakdown.py` — 196 строк

Следствия разбивки вакансий по статусам за период.

Зависит от: `backend.models`, `backend.repository.stats_statuses`, `tests.dbio`, `tests.factories`

Тестов: 9


### `tests/backend/test_repository_stats_funnel.py` — 217 строк

Следствия воронки канала на экране статистики: шаги и доли.

Зависит от: `backend.models`, `tests.backend.fixtures.stats`, `tests.dbio`, `tests.factories`

Тестов: 7


### `tests/backend/test_repository_stats_kpi.py` — 280 строк

Следствия сводных счётчиков в шапке экрана статистики.

Зависит от: `backend.models`, `backend.repository.stats_kpi`, `tests.dbio`, `tests.factories`

Тестов: 12

- `def _four_steps(vacancy_id: int, when)` (11)

### `tests/backend/test_repository_stats_period.py` — 68 строк

Следствия перевода кода периода в границу отсчёта.

Зависит от: `backend.repository.stats_common`

Тестов: 3


### `tests/backend/test_repository_stats_pipeline.py` — 364 строк ⚠ подошёл к 300

Следствия таблицы «каналы»: что канал прислал и сколько из этого мусор.

Зависит от: `backend.domain.verdict`, `backend.models`, `backend.repository.aggregators`, `backend.repository.stats_pipeline`, `tests.backend.fixtures.stats`, `tests.dbio`, `tests.factories`, `tests.factories_aggregators`

Тестов: 16

- `async def _rows_by_source(session) -> dict[tuple, dict]` (3)

### `tests/backend/test_repository_stats_response_time.py` — 265 строк

Следствия подсчёта срока ответа на отклик.

Зависит от: `backend.models`, `backend.repository.stats_responses`, `tests.dbio`, `tests.factories`

Тестов: 14


### `tests/backend/test_repository_stats_response_weekday.py` — 57 строк

Следствия распределения ответов HR по дням недели.

Зависит от: `backend.repository.stats_responses`

Тестов: 2

- `def _monday(hour: int=12) -> datetime` (7)
- `def _local_monday_after_midnight() -> datetime` (12)

### `tests/backend/test_repository_stats_skills.py` — 184 строк

Следствия подсчёта технологий, встречающихся в вакансиях.

Зависит от: `backend.repository.stats_skills`, `tests.dbio`, `tests.factories`

Тестов: 11

- `async def labels(session, **kwargs) -> list[str]` (4)

### `tests/backend/test_repository_trash_marks.py` — 103 строк

Отметки о мусоре: по одной на объявление, сколько бы раз его ни разбирали.

Зависит от: `backend.models`, `backend.repository.vacancies_life`, `tests.dbio`, `tests.factories`, `tests.factories_aggregators`

Тестов: 5

- `async def _noted(session, channel_id: int, msg_id: int, reason: str) -> None` (5)

### `tests/backend/test_repository_vacancy_brief.py` — 34 строк

Вакансия текстом для агента: чья она, где она и её текст — данными.

Зависит от: `backend.repository.vacancy_brief`, `tests.dbio`, `tests.factories`, `tests.factories_aggregators`

Тестов: 3


### `tests/backend/test_repository_vacancy_detail.py` — 139 строк

Следствия чтения карточки вакансии.

Зависит от: `backend.models`, `backend.repository.vacancies_card`, `tests.dbio`, `tests.factories`

Тестов: 7


### `tests/backend/test_repository_vacancy_events.py` — 42 строк

Следствия записи события в ленту обработки вакансии.

Зависит от: `backend.repository.vacancies_card`, `backend.repository.vacancies_life`, `tests.dbio`, `tests.factories`

Тестов: 2


### `tests/backend/test_repository_vacancy_filters.py` — 217 строк

Следствия отбора в `list_vacancies` по колонкам самой вакансии.

Зависит от: `backend.models`, `tests.dbio`, `tests.factories`

Тестов: 14


### `tests/backend/test_repository_vacancy_ghosting.py` — 237 строк

Следствия автоматического перевода молчащих вакансий в «пропала».

Зависит от: `backend.models`, `backend.repository.vacancies_card`, `backend.repository.vacancies_ghosting`, `tests.dbio`, `tests.factories`

Тестов: 12


### `tests/backend/test_repository_vacancy_joins.py` — 374 строк ⚠ подошёл к 300

Следствия отбора в `list_vacancies` по тому, что лежит в соседних таблицах.

Зависит от: `backend.repository.vacancies_list`, `tests.dbio`, `tests.factories`, `tests.factories_aggregators`

Тестов: 19


### `tests/backend/test_repository_vacancy_links.py` — 266 строк

Следствия привязки вакансии к HR и компании и её удаления.

Зависит от: `backend.models`, `backend.repository.vacancies_card`, `backend.repository.vacancies_life`, `tests.dbio`, `tests.factories`, `tests.factories_aggregators`

Тестов: 14


### `tests/backend/test_repository_vacancy_mini_lists.py` — 279 строк

Следствия трёх коротких списков вакансий, привязанных к одному владельцу.

Зависит от: `backend.models`, `backend.repository.vacancies_mini`, `tests.dbio`, `tests.factories`, `tests.factories_aggregators`

Тестов: 10


### `tests/backend/test_repository_vacancy_notes.py` — 78 строк

Следствия правки заметки вакансии.

Зависит от: `backend.repository.vacancies_card`, `tests.dbio`, `tests.factories`

Тестов: 5


### `tests/backend/test_repository_vacancy_options.py` — 293 строк

Следствия двух справочных запросов по вакансиям.

Зависит от: `backend.repository.vacancies_list`, `tests.dbio`, `tests.factories`

Тестов: 14


### `tests/backend/test_repository_vacancy_salary.py` — 137 строк

Следствия отбора вакансий по зарплате.

Зависит от: `tests.dbio`, `tests.factories`

Тестов: 7


### `tests/backend/test_repository_vacancy_sort.py` — 299 строк

Следствия порядка выдачи в `list_vacancies`.

Зависит от: `backend.models`, `tests.dbio`, `tests.factories`

Тестов: 15


### `tests/backend/test_repository_vacancy_status.py` — 328 строк ⚠ подошёл к 300

Следствия смены статуса вакансии — руками, откликом и автоматически.

Зависит от: `backend.models`, `backend.payloads`, `backend.repository.vacancies_card`, `backend.repository.vacancy_status`, `tests.dbio`, `tests.factories`

Тестов: 18


### `tests/backend/test_runtime_settings_load.py` — 259 строк

Следствия чтения настроек из базы в память.

Зависит от: `backend.crypto`, `backend.models`, `backend.runtime_settings`, `tests.dbio`, `tests.factories`

Тестов: 22


### `tests/backend/test_runtime_settings_masking.py` — 74 строк

Следствия сокрытия секретов от журнала при записи настроек.

Зависит от: `backend.runtime_settings`, `backend.tg_credentials`, `tests.factories`

Тестов: 4


### `tests/backend/test_runtime_settings_values.py` — 264 строк

Следствия типизированных свойств `RuntimeSettings`.

Зависит от: `backend.runtime_settings`

Тестов: 29

- `def settings(**app) -> RuntimeSettings` (16)

### `tests/backend/test_runtime_settings_writes.py` — 233 строк

Следствия записи настроек: у одних методов их два, у других — одно.

Зависит от: `adapters`, `backend.crypto`, `backend.models`, `backend.runtime_settings`, `tests.dbio`, `tests.factories`

Тестов: 18


### `tests/backend/test_schema_and_models.py` — 42 строк

Схема базы и объявления моделей не разошлись.

Зависит от: `backend.models`

Тестов: 1


### `tests/backend/test_single_instance.py` — 153 строк

Следствия сторожа единственности приложения.

Зависит от: `backend.single_instance`

Тестов: 6

- `def _lock_once_it_is_free(lock_path: Path, seconds: float=5.0)` (14)

### `tests/backend/test_task_stop.py` — 23 строк

Погашенная задача кончилась к возврату: после остановки она ничего не допишет.

Зависит от: `backend.task_stop`

Тестов: 1


### `tests/backend/test_telegram_adapter.py` — 259 строк

Следствия сборки клиента Telegram и отправки личного сообщения.

Зависит от: `adapters.telegram`, `config`, `tests.factories`, `tests.fakes.telegram`

Тестов: 11

- `class DialogServer` (52)
  - `async def invoke(self, query, **_options)` (13)
  - `def _messages(self, page)` (15)
  - `async def resolve_peer(self, peer_id)` (2)
- `def _raw_dialog(peer_id: int)` (11)
- `def _raw_message(peer_id: int, message_id: int, *, date: int)` (4)

### `tests/backend/test_telegram_identity.py` — 156 строк

Следствия, которые наблюдают тесты `backend/domain/telegram_identity.py`.

Зависит от: `backend.domain.telegram_identity`

Тестов: 9

- `class Contact` (7)

### `tests/backend/test_telegram_login.py` — 363 строк ⚠ подошёл к 300

Следствия входа в Telegram по коду.

Зависит от: `backend.runtime_settings`, `backend.telegram_login`, `tests.fakes.telegram`

Тестов: 22

- `def clients(monkeypatch)` (16)
  - `def build(**kwargs)` (5)
- `async def login(session_factory, clients)` (4)
- `async def sent(login, *, phone='+79991234567')` (3)

### `tests/backend/test_telegram_lookup.py` — 151 строк

Следствия, которые наблюдают тесты `backend/telegram_lookup.py`.

Зависит от: `backend.telegram_lookup`, `tests.fakes.telegram`, `tests.fakes.telegram_objects`

Тестов: 14


### `tests/backend/test_telegram_time.py` — 47 строк

Следствия, которые наблюдает тест `backend/telegram_time.py`.

Зависит от: `backend.telegram_time`

Тестов: 3


### `tests/backend/test_update_download.py` — 90 строк

Скачивание обновления: файл ложится, только если сошёлся с релизом; иначе его нет.

Зависит от: `backend.app_version`, `backend.update_download`, `tests.fakes.github_release`

Тестов: 7

- `def target(tmp_path)` (2)
- `def _quiet(got, total)` (2)

### `tests/backend/test_updater.py` — 165 строк

Подмена exe: копия ждёт выхода приложения, заменяет его файл и запускает новый.

Зависит от: `backend`

Тестов: 9

- `def app(tmp_path)` (7)
- `def started(monkeypatch, tmp_path)` (12)
- `def leftovers(tmp_path, monkeypatch)` (8)

### `tests/backend/test_wipe.py` — 272 строк

Следствия сноса данных: что остаётся в каталоге после «удалить всё».

Зависит от: `backend.single_instance`, `backend.wipe`, `config`

Тестов: 10

- `def lock_let_go()` (9)
- `def data_dir(tmp_path, monkeypatch)` (7)
- `def held_by_someone_else(monkeypatch, what: str) -> None` (13)
  - `def _refuse(*args, **kwargs)` (2)

### `tests/client/conftest.py` — 232 строк

Стенд моста: поверхность окна поверх настоящей базы, без окна и без канала.

Зависит от: `backend.log_buffer`, `backend.runtime_settings`, `client`, `client.bridge`, `tests.fakes.llm`, `tests.fakes.ui_bot`

- `class LoopRunner` (37)
  - `def submit(self, coro) -> Future` (4)
  - `async def drain(self) -> None` (12)
- `async def runner() -> LoopRunner` (3)
- `async def runtime_settings(session_factory) -> RuntimeSettings` (7)
- `async def hub(runtime_settings, session_factory, runner)` (24)
- `async def api(hub) -> Api` (3)
- `def ask()` (12)
  - `async def _ask(method, *args)` (2)
- `def provider_says(monkeypatch)` (19)
  - `def _answer(routes) -> None` (6)
- `def told(hub, runner)` (18)
  - `async def _told()` (8)
- `def with_bot(hub)` (9)
  - `def _put(**answers) -> UiBot` (4)
- `class WindowThatGrows` (18)
  - `def move(self, x: int, y: int) -> None` (2)
  - `def resize(self, width: int, height: int) -> None` (2)
- `def growing_window(monkeypatch) -> WindowThatGrows` (12)
- `class WindowThatPicks` (16)
  - `def create_file_dialog(self, *_args, **_kwargs)` (5)

### `tests/client/test_bot_contract.py` — 174 строк

Шов имён между мостом и ботом.

Зависит от: `backend.bot`, `backend.bot.client`, `backend.bot.pasted`, `backend.bot.rerun`, `client.bridge`, `client.bridge.refusals`, `tests.fakes.ui_bot`

Тестов: 8

- `def _is_the_bot(node: ast.expr) -> bool` (9)
- `def _touched_on_the_bot() -> set[str]` (14)
- `def _asked_of_the_bot() -> list[str]` (11)
- `def _hooks_set_in(what) -> set[str]` (13)
- `def _hooks_the_bot_declares() -> set[str]` (3)
- `def _rerun_outcomes() -> set[str]` (3)
- `def _pasted_outcomes() -> set[str]` (3)

### `tests/client/test_bridge_aggregators.py` — 301 строк ⚠ подошёл к 300

Домен «Агрегаторы»: перечень, заведение, удаление, включение, вход и обход.

Зависит от: `backend.agent.availability`, `backend.bot.work`, `backend.models`, `backend.repository.aggregators`, `tests.dbio`, `tests.factories`, `tests.factories_aggregators`, `tests.fakes.site_home`

Тестов: 25


### `tests/client/test_bridge_answer.py` — 132 строк

Следствия общей части моста: чем окну отвечают на любой запрос.

Зависит от: `client.bridge.answer`

Тестов: 6


### `tests/client/test_bridge_apply_via.py` — 68 строк

Отклик выбранным способом: какие способы доступны у вакансии и запуск одного из них.

Зависит от: `backend.domain.apply_order`, `backend.models`, `tests.backend.fixtures.applying`, `tests.dbio`, `tests.factories`, `tests.factories_aggregators`

Тестов: 5

- `async def _vacancy(session_factory, **over)` (6)

### `tests/client/test_bridge_blacklist.py` — 230 строк

Следствия слотов чёрного списка: записи заслона и весь их перечень.

Зависит от: `backend.models`, `tests.dbio`, `tests.factories`

Тестов: 15


### `tests/client/test_bridge_blacklist_hints.py` — 57 строк

Следствия подсказок к форме заслона: кого окно предлагает выбрать.

Зависит от: `tests.dbio`, `tests.factories`

Тестов: 3


### `tests/client/test_bridge_bot_stop.py` — 47 строк

Следствия остановки бота: чем кончается ожидание, которого не дождались.

Зависит от: `client.bridge.bot_stop`, `tests.fakes.ui_bot`

Тестов: 2


### `tests/client/test_bridge_channel_actions.py` — 230 строк

Следствия действий над каналом, которым нужен поднятый бот.

Зависит от: `backend.models`, `tests.dbio`, `tests.factories`

Тестов: 13


### `tests/client/test_bridge_channels.py` — 226 строк

Следствия домена канала, которым хватает одной базы.

Зависит от: `backend.models`, `tests.dbio`, `tests.factories`

Тестов: 11


### `tests/client/test_bridge_choice_sets.py` — 35 строк

Следствия отбора значений из закрытых наборов при чтении форм окна.

Зависит от: `backend.domain.taxonomy`, `backend.incoming`

Тестов: 2


### `tests/client/test_bridge_companies.py` — 324 строк ⚠ подошёл к 300

Следствия домена компании: перечень, карточка, написания, слияние, заслон.

Зависит от: `tests.dbio`, `tests.factories`

Тестов: 17


### `tests/client/test_bridge_cv.py` — 244 строк

Следствия резюме — файла, путь к которому помнит окно.

Зависит от: `backend.models`, `tests.client.conftest`, `tests.dbio`, `tests.factories`, `tests.fakes.llm`

Тестов: 13

- `def resume_on_disk(tmp_path, api, ask)` (10)
  - `async def _put(body: str, name: str='резюме.txt') -> str` (5)
- `async def chat_model(session_factory, runtime_settings)` (4)
- `async def model_says(chat_model, provider_says)` (7)
  - `def _answer(payload: dict) -> None` (2)

### `tests/client/test_bridge_events.py` — 218 строк

Следствия очереди живых событий: что узнаёт окно, спросившее «что нового».

Зависит от: `client.bridge.events`

Тестов: 12


### `tests/client/test_bridge_hr.py` — 314 строк ⚠ подошёл к 300

Следствия карточки HR: перечень, правка, слияние, чёрный список.

Зависит от: `tests.dbio`, `tests.factories`

Тестов: 18


### `tests/client/test_bridge_hr_chat.py` — 244 строк

Следствия переписки: что окно показывает и чем отвечают на отправку.

Зависит от: `tests.client.conftest`, `tests.dbio`, `tests.factories`

Тестов: 12


### `tests/client/test_bridge_journal.py` — 126 строк

Следствия домена журнала: что человек видит на экране записей.

Зависит от: `backend.log_buffer`

Тестов: 5

- `def journal()` (20)

### `tests/client/test_bridge_lifespan.py` — 257 строк

Следствия подъёма и гашения моста: что окно заводит, открываясь и закрываясь.

Зависит от: `backend.telegram_login`, `client.bridge`, `tests.fakes.ui_login`

Тестов: 10

- `class Silent` (2)
- `class Stoppable(Silent)` (11)
  - `def cancel_current_poll(self) -> None` (2)
  - `def request_stop(self) -> None` (2)

### `tests/client/test_bridge_list_payload.py` — 67 строк

Следствия чтения нагрузки списка — той, что четыре экрана шлют одинаково.

Зависит от: `tests.dbio`, `tests.factories`

Тестов: 3


### `tests/client/test_bridge_llm.py` — 429 строк ⚠ подошёл к 300

Следствия проверки языковой модели: что окно узнаёт, нажав «проверить».

Зависит от: `tests.client.conftest`, `tests.fakes.gguf`, `tests.fakes.llm`

Тестов: 22

- `def _busy_provider(free: asyncio.Event)` (23)
  - `def make(_cfg)` (13)
    - `async def answer(request)` (8)

### `tests/client/test_bridge_login.py` — 196 строк

Следствия входа в Telegram: три шага, о которых окно спрашивает по одному.

Зависит от: `backend.crypto`, `backend.telegram_login`, `tests.dbio`, `tests.factories`, `tests.fakes.ui_login`

Тестов: 10


### `tests/client/test_bridge_media.py` — 21 строк

Снимок, вшитый в ответ окну: тип в адресе — тот, что у самих байтов.

Зависит от: `client.bridge.media`

Тестов: 1


### `tests/client/test_bridge_model_speed.py` — 134 строк

Следствия запомненного замера скорости моделей.

Зависит от: `tests.fakes.llm`

Тестов: 4

- `def models_say(monkeypatch, answers: list[bool])` (16)
  - `async def alive(_cfg, kind)` (4)
- `def timed(monkeypatch, ms: int | None) -> list[str]` (10)
  - `async def speed(_cfg, kind)` (3)
- `async def health_after_drain(api, ask, runner) -> dict` (5)

### `tests/client/test_bridge_paging.py` — 74 строк

Следствия признака продолжения — того, по которому окно решает, просить ли ещё.

Зависит от: `tests.dbio`, `tests.factories`

Тестов: 4


### `tests/client/test_bridge_profile.py` — 307 строк ⚠ подошёл к 300

Следствия слотов анкеты — того, что человек рассказывает о себе.

Зависит от: —

Тестов: 17

- `async def _saved_person(api, ask, **extra) -> None` (4)

### `tests/client/test_bridge_runner.py` — 170 строк

Следствия мотора, в котором окно исполняет свою работу.

Зависит от: `client.bridge.runner`

Тестов: 8

- `def real_runner()` (16)
- `def _troubled(real_runner, exc: BaseException) -> None` (11)

### `tests/client/test_bridge_settings.py` — 165 строк

Следствия экрана настроек: что записано и что показано на экране.

Зависит от: `adapters.browser`, `backend.agent.availability`, `backend.models`

Тестов: 11


### `tests/client/test_bridge_shell.py` — 281 строк

Следствия обращения к оболочке: что окно отдаёт системе, а что нет.

Зависит от: `client.bridge.desktop`, `client.serving`

Тестов: 14

- `def opened(monkeypatch) -> list` (8)
- `def refused_by_the_system(monkeypatch) -> None` (9)
- `def media(monkeypatch, tmp_path)` (10)

### `tests/client/test_bridge_stats.py` — 89 строк

Следствия домена статистики: чей ответ и за какой срок приходит в окно.

Зависит от: `tests.dbio`, `tests.factories`

Тестов: 7


### `tests/client/test_bridge_system.py` — 305 строк ⚠ подошёл к 300

Следствия домена «система»: чем занят бот и что показывает нижняя полоса.

Зависит от: `backend.app_version`, `backend.models`, `tests.dbio`, `tests.factories`, `tests.fakes.github_release`

Тестов: 22

- `def handed_over(hub)` (5)

### `tests/client/test_bridge_vacancies.py` — 431 строк ⚠ подошёл к 300

Следствия слотов вакансий, которым хватает одной базы.

Зависит от: `backend.models`, `tests.dbio`, `tests.factories`, `tests.factories_aggregators`

Тестов: 22


### `tests/client/test_bridge_vacancy_actions.py` — 299 строк

Следствия действий над вакансией, которым нужен поднятый бот.

Зависит от: `tests.dbio`, `tests.factories`, `tests.factories_aggregators`

Тестов: 16

- `def mailable_vacancy(session_factory)` (10)
  - `async def _put()` (5)
- `def broken_vacancy(with_bot, mailable_vacancy)` (11)
  - `async def _put()` (6)
    - `async def broken(vacancy_id, way)` (2)
- `def _by_mail(vacancy) -> dict` (2)

### `tests/client/test_bridge_vacancy_contacts.py` — 77 строк

Контакты вакансии в карточке: человек добавляет и удаляет их руками.

Зависит от: `backend.models`, `tests.dbio`, `tests.factories`, `tests.factories_aggregators`

Тестов: 6


### `tests/client/test_bridge_vacancy_create.py` — 427 строк ⚠ подошёл к 300

Следствия заведения вакансии руками: что после него видно в списке и в карточке.

Зависит от: `tests.dbio`, `tests.factories`

Тестов: 25

- `async def created(ask, api, **fields) -> int` (9)
- `async def profile_knowing(session_factory, name: str, level: int) -> None` (10)

### `tests/client/test_bridge_vacancy_links.py` — 228 строк

Следствия связывания вакансии с HR и компанией — вместе с подборщиками.

Зависит от: `tests.dbio`, `tests.factories`

Тестов: 11


### `tests/client/test_bridge_wipe.py` — 173 строк

Следствие удаления всех данных: в каком порядке это происходит.

Зависит от: `tests.fakes.ui_bot`

Тестов: 4

- `def wipe_steps(monkeypatch, hub)` (26)
  - `async def _wipe_all(engine) -> list[str]` (3)

### `tests/client/test_bridge_wire.py` — 28 строк

Следствия перевода внутренних значений в словари для окна.

Зависит от: `client.bridge.wire`

Тестов: 2


### `tests/client/test_bridge_wizard.py` — 229 строк

Следствия первого запуска: с какого шага он продолжается и чем кончается.

Зависит от: `backend.crypto`, `backend.models`, `backend.runtime_settings`, `tests.dbio`, `tests.factories`

Тестов: 11


### `tests/client/test_form_payloads.py` — 224 строк

Следствия чтения нагрузок форм «добавить HR» и «добавить компанию».

Зависит от: `backend.repository.companies_card`, `backend.repository.hr_identify`, `client.bridge.form_payloads`

Тестов: 17


### `tests/client/test_front_vocabulary.py` — 161 строк

Согласие перечней окна с перечнями бэкенда.

Зависит от: `backend.domain.taxonomy`, `backend.domain.verdict`, `backend.models.enums`, `backend.models.settings`

Тестов: 8

- `def _array(module: str, name: str) -> str` (10)
- `def _object(module: str, name: str) -> str` (10)
- `def _strings(module: str, name: str) -> list[str]` (3)
- `def _values(module: str, name: str) -> list[str]` (3)
- `def _skip_reasons_the_backend_writes() -> set[str]` (18)

### `tests/client/test_page_contract.py` — 158 строк

Шов имён: сходятся ли имена, которыми страница зовёт мост, с самим мостом.

Зависит от: —

Тестов: 6

- `def _sources() -> list[Path]` (7)
- `def _called(text: str) -> set[tuple[str, str]]` (3)
- `def _pages_that_call() -> list[Path]` (9)

### `tests/client/test_raise_window.py` — 159 строк

Следствия просьбы второй копии вывести вперёд уже открытое окно.

Зависит от: `client.raise_window`

Тестов: 7

- `class WindowDouble` (11)
  - `def restore(self) -> None` (2)
  - `def show(self) -> None` (2)
- `def copies()` (16)
  - `def start(window, name)` (4)

### `tests/client/test_web_serving.py` — 140 строк

Следствия раздачи по http: что окно получает по своему адресу.

Зависит от: `client.serving`

Тестов: 7

- `def _app(front, media=None)` (3)
- `def _get(app, path: str) -> tuple[str, dict, bytes]` (10)
  - `def start_response(status: str, headers: list[tuple[str, str]]) -> None` (3)

### `tests/client/test_window.py` — 290 строк

Следствия открытия и закрытия окна: что приложение делает вокруг него.

Зависит от: `backend.models`, `backend.repository.bot_mode`, `client`, `tests.backend.fixtures.bot`

Тестов: 10

- `class FakeWebview` (12)
  - `def create_window(self, title: str, url=None, **options)` (3)
  - `def start(self, **options) -> None` (2)
- `class StubRunner` (19)
  - `def submit(self, coro) -> Future` (5)
  - `def stop(self) -> None` (2)
- `class StubHub` (4)
- `def opened(monkeypatch, runtime_settings, session_factory)` (30)
  - `class StubListener` (3)
    - `def close(self) -> None` (2)
  - `def claude_code_off()` (3)
- `class _Settings` (5)
- `def _sessions(tmp_path, monkeypatch)` (8)

### `tests/client/test_window_size.py` — 35 строк

Рост окна в тот миг, когда мастер закончен.

Зависит от: `client`

Тестов: 2


### `tests/conftest.py` — 452 строк ⚠ подошёл к 300

Стенд: подмена каталога данных, хранилища ключей и базы.

Зависит от: `adapters`, `adapters.db`, `adapters.telegram`, `alembic`, `backend`, `backend.bootstrap`, `config`, `tests.fakes.keyring`

- `def _data_dir_without_appdata() -> Path` (15)
- `def _temporary_data_dir()` (3)
- `def memory_keyring() -> MemoryKeyring` (3)
- `def _appdata_guard()` (27)
- `def database_url() -> str` (9)
- `def migrations_target(tmp_path, monkeypatch) -> Path` (13)
- `def _schema(database_url)` (13)
- `class TelegramReached(BaseException)` (10)
- `def _telegram_is_unreachable(monkeypatch)` (39)
  - `async def _refuse(*_args, **_kwargs)` (7)
- `class ProviderReached(BaseException)` (6)
- `def _anthropic_is_unreachable(monkeypatch)` (16)
  - `async def _refuse(*_args, **_kwargs)` (5)
- `def _claude_code_is_unreachable(monkeypatch)` (21)
  - `async def _refuse(*_args, **_kwargs)` (5)
- `class EngineReached(BaseException)` (7)
- `def _model_engine_is_locked(monkeypatch)` (15)
  - `def _refuse(*_args, **_kwargs)` (5)
- `def _sending_locked(monkeypatch)` (10)
- `def _secrets_forgotten(monkeypatch)` (9)
- `async def _clear_all_tables(engine: AsyncEngine) -> None` (37)
- `async def _empty_database(database_url) -> None` (9)
- `async def _clean_database(_schema, database_url)` (19)
- `async def engine(_schema, database_url)` (14)
- `def session_factory(engine) -> async_sessionmaker[AsyncSession]` (8)
- `async def session(session_factory)` (16)

### `tests/dbio.py` — 69 строк

Короткие обращения к базе из теста.

Зависит от: —

- `async def put(session_factory, *rows) -> None` (6)
- `async def only_row(session_factory, model)` (4)
- `async def all_rows(session_factory, model) -> list` (8)
- `def sqlite_rows(db_file, sql: str) -> list[tuple]` (11)
- `def sqlite_write(db_file, *statements: str) -> None` (10)
- `def sqlite_tables(db_file) -> set[str]` (3)

### `tests/factories.py` — 442 строк ⚠ подошёл к 300

Построение объектов, которые тесты подают на вход коду.

Зависит от: `backend.models`, `backend.payloads`, `backend.tg_credentials`

- `def at(minutes: int) -> datetime` (3)
- `def days_ago(days: float) -> datetime` (8)
- `def resume_file(folder, name: str='Резюме.pdf')` (5)
- `def photo_head(suffix: str) -> bytes` (7)
- `def _empty_vacancy() -> dict` (23)
- `def parsed_vacancy(**overrides) -> ParsedVacancy` (7)
- `def skill_fields(**overrides) -> dict` (7)
- `def profile_skill(name: str, level: int | None=None, aliases: list | None=None, **overrides) -> ProfileSkill` (10)
- `def tg_account_row(**overrides) -> TgAccount` (18)
- `def llm_config_row(kind: LlmConfigKind, **overrides) -> LlmConfig` (9)
- `def app_setting_row(key: str, value: str | None, **overrides) -> AppSetting` (5)
- `def bot_state_row(mode: BotMode) -> BotState` (3)
- `def vacancy_row(**overrides) -> Vacancy` (19)
- `def hr_row(**overrides) -> HR` (5)
- `def company_row(**overrides) -> Company` (5)
- `def channel_row(**overrides) -> TelegramChannel` (5)
- `def person_fields(**overrides) -> dict` (12)
- `def profile_row(**overrides) -> Profile` (3)
- `def profile_skill_row(profile_id: int, name: str, **overrides) -> ProfileSkill` (3)
- `def experience_fields(**overrides) -> dict` (14)
- `def experience_row(profile_id: int, **overrides) -> ProfileExperience` (3)
- `def project_fields(**overrides) -> dict` (3)
- `def project_row(profile_id: int, **overrides) -> ProfileProject` (3)
- `def blacklist_row(kind: str, value: str, **overrides) -> Blacklist` (5)
- `def message_row(**overrides) -> Message` (11)
- `def unread_probe(hr_id: int) -> list[Message]` (20)
- `def unread_probe_with_a_neighbour(hr_id: int, other_hr_id: int) -> list[Message]` (13)
- `def channel_marks() -> list[Blacklist]` (13)
- `def marked_channels() -> list[TelegramChannel]` (15)
- `def company_marks() -> list[Blacklist]` (15)
- `def marked_companies() -> list[Company]` (5)
- `def vacancy_event_row(vacancy_id: int, **overrides) -> VacancyEvent` (5)
- `def status_history_row(vacancy_id: int, **overrides) -> VacancyStatusHistory` (10)
- `def tg_creds(**overrides) -> TgAccountConfig` (16)

### `tests/factories_aggregators.py` — 67 строк

Строки и факты откликов: агрегаторы, контакты вакансии, отклики, почта, мир откликателя.

Зависит от: `backend.crypto`, `backend.domain.apply_order`, `backend.models`, `backend.repository.aggregators`, `tests.factories`

- `def aggregator_row(**overrides) -> Aggregator` (5)
- `def web_search_row(**overrides) -> Aggregator` (3)
- `def vacancy_contact_row(vacancy_id: int, value: str, **overrides) -> VacancyContact` (6)
- `def application_row(vacancy_id: int, **overrides) -> Application` (9)
- `def screening_row(application_id: int, position: int, **overrides) -> Screening` (5)
- `def mail_account_row() -> MailAccount` (4)
- `def world_of(**overrides) -> World` (6)

### `tests/factories_cv.py` — 75 строк

Разобранное резюме — то, что разбор отдаёт записи анкеты и сверке с текстом.

Зависит от: `backend.payloads`, `tests.factories`

- `def parsed_cv_profile(**overrides) -> ParsedCvProfile` (24)
- `def parsed_cv_skill(name: str, **overrides) -> ParsedCvSkill` (3)
- `def parsed_cv_place(**overrides) -> ParsedCvExperience` (9)
- `def parsed_cv_project(**overrides) -> ParsedCvProject` (3)
- `def parsed_cv(**overrides) -> ParsedCv` (11)

### `tests/fakes/agent.py` — 108 строк

Набор сессии агента без браузера, водителя и человека.

Зависит от: `backend.agent.human_gate`, `backend.agent.jobs`, `backend.agent.kit`, `backend.domain.apply_order`, `tests.fakes.browser`

- `class LimitHit(Exception)` (2)
- `def tool(tools, name)` (3)
- `def apply_job(vacancy_id: int, *, method='form', target='https://company.test/apply', aggregator_id=None, **overrides) -> ApplyJob` (7)
- `def scripted(steps: list[Callable[[dict[str, Callable]], Awaitable]])` (19)
  - `async def run(plan: SessionPlan) -> AgentEnd` (8)
- `def finish_step(result: str='done', reason: str='')` (5)
  - `async def step(tools)` (2)
- `def fail_step(reason: str)` (5)
  - `async def step(tools)` (2)
- `def record_step(target: str, via: str='form')` (5)
  - `async def step(tools)` (2)
- `def captcha_step()` (5)
  - `async def step(tools)` (2)
- `def login_step(logged_in: bool)` (6)
  - `async def step(tools)` (3)
- `def silent_gate(limit_sec: float=3600.0) -> HumanGate` (3)
- `def scripted_kit(pipeline, steps, *, human_limit: float=3600.0) -> AgentKit` (4)
- `def work_kit(bot) -> AgentKit` (3)
- `def kit_for(pipeline, *, browser=None, gate=None, run_session=None) -> AgentKit` (3)

### `tests/fakes/browser.py` — 130 строк

Браузер агента с заданными страницами: что открыто, что нажато, что отказало.

Зависит от: —

- `class _Chooser` (6)
  - `async def set_files(self, files, **_options)` (2)
- `class _ChooserInfo` (20)
  - `async def __aenter__(self)` (3)
  - `async def __aexit__(self, kind, *_rest)` (4)
  - `def value(self)` (4)
    - `async def _chooser()` (2)
- `class _Locator` (7)
  - `async def aria_snapshot(self, **_options)` (3)
- `class FakePage` (49)
  - `def fail_if_asked(self, selector)` (3)
  - `async def goto(self, url, **_options)` (4)
  - `async def title(self)` (2)
  - `def locator(self, selector)` (2)
  - `async def click(self, selector, **_options)` (4)
  - `async def fill(self, selector, text, **_options)` (3)
  - `async def select_option(self, selector, value, **_options)` (3)
  - `async def set_input_files(self, selector, files, **_options)` (3)
  - `def expect_file_chooser(self, **_options)` (2)
  - `async def go_back(self, **_options)` (2)
- `class FakeBrowser` (34)
  - `async def page(self)` (2)
  - `async def show(self)` (2)
  - `async def hide_back(self)` (2)
  - `async def open_profile(self, profile_id: int, sending: bool=True, as_person: bool=False)` (4)
  - `async def clear_cache(self)` (2)
  - `async def close(self)` (2)
  - `async def wait_closed(self, limit_sec: float) -> bool` (4)

### `tests/fakes/claude.py` — 83 строк

Подделка API Anthropic: настоящий клиент SDK поверх подставного транспорта.

Зависит от: `adapters.claude`, `tests.fakes.llm`

- `def claude(routes: dict) -> ClaudeClient` (12)
- `def _reply(content: list, stop_reason: str, **extra) -> httpx2.Response` (13)
- `def message(text: str, *, stop_reason: str='end_turn') -> httpx2.Response` (9)
- `def refusal(category: str='cyber') -> httpx2.Response` (7)
- `def model_list(*ids: str) -> httpx2.Response` (16)

### `tests/fakes/claude_code.py` — 157 строк

Подделка Claude Code: живой процесс подменён, обмен с ним и разбор настоящие.

Зависит от: `adapters`

- `def _answer(text: str | None, **fields) -> dict` (3)
- `def result(text: str | None, *, stop_reason: str='end_turn') -> dict` (5)
- `def failure(text: str, *, status: int | None=None) -> dict` (9)
- `class _Stdin` (12)
  - `def write(self, data: bytes) -> None` (5)
  - `async def drain(self) -> None` (2)
- `class _Stdout` (6)
  - `async def readline(self) -> bytes` (2)
- `class Process` (51)
  - `def heard(self, line: dict) -> None` (22)
  - `def _push(self, message: dict) -> None` (2)
  - `async def next_line(self) -> bytes` (6)
  - `def kill(self) -> None` (3)
  - `async def wait(self) -> int` (2)
- `class Calls` (16)
- `def install(monkeypatch, replies: list, *, cli: str | None=CLI) -> Calls` (18)
  - `async def spawn(argv, env)` (6)

### `tests/fakes/gguf.py` — 54 строк

Подделка движка эмбеддингов: настоящая модель в тестах не грузится.

Зависит от: `adapters`

- `class Model` (16)
  - `def embed(self, text: str) -> list` (5)
  - `def close(self) -> None` (2)
- `def model_file(folder) -> str` (5)
- `def engine(monkeypatch, load) -> None` (3)
- `def failing_engine(monkeypatch, trouble: BaseException) -> None` (7)
  - `def load(_path)` (2)
- `def engine_journal(monkeypatch) -> list[str]` (5)

### `tests/fakes/github_release.py` — 73 строк

Подделка GitHub: API релизов и скачивание файла поверх подставного транспорта.

Зависит от: `adapters.github_release`, `tests.fakes.http`

- `def download_url(tag: str, asset: str=ASSET) -> str` (2)
- `def serve_latest(monkeypatch, prepared: httpx.Response | BaseException, files: dict[str, httpx.Response | BaseException] | None=None) -> None` (9)
- `def in_pieces(content: bytes, size: int=64 * 1024) -> httpx.Response` (8)
  - `async def pieces()` (3)
- `def serve_newer(monkeypatch, served: httpx.Response | BaseException | None=None, content: bytes=APP, digest=FROM_CONTENT) -> None` (7)
- `def release_answer(tag: str, *, asset: str=ASSET, content: bytes=APP, digest=FROM_CONTENT) -> httpx.Response` (14)

### `tests/fakes/http.py` — 24 строк

Подделка HTTP для адаптеров со своим сборщиком клиента: настоящий `httpx`

Зависит от: `tests.fakes.llm`

- `def serve(monkeypatch, make_client: str, routes: dict) -> None` (11)
  - `def _client() -> httpx.AsyncClient` (2)

### `tests/fakes/ingestion.py` — 169 строк

Подделка конвейера сбора и оповещений окна о ходе цикла.

Зависит от: `backend.flows.dm`, `backend.flows.dm_backfill`, `backend.flows.pipeline`

- `class FakeIngestion` (119)
  - `async def recover_orphan_vacancies(self)` (4)
  - `async def check_ghosting_timeouts(self)` (4)
  - `async def cancel_pending_dm_classifications(self, drain: bool=False)` (4)
  - `def mark_shutting_down(self)` (4)
  - `def spawn_backfill(self, work, what: str, *, extra: dict | None=None) -> None` (15)
  - `def schedule_dm_classification(self, hr_id, *rest)` (3)
  - `def dm_helpers(self) -> DmHelpers` (7)
  - `def dm_hooks(self) -> DmHooks` (3)
  - `def update_dm_buffer_text(self, hr_id: int, tg_message_id: int, text: str) -> None` (2)
  - `def remove_dm_buffer_msg(self, hr_id: int, tg_message_id: int) -> None` (2)
  - `async def poll_one_channel(self, channel_id: int)` (3)
  - `async def poll_active_channels(self)` (4)
  - `async def rerun_pipeline_for_vacancy(self, vacancy_id: int)` (3)
  - `async def ingest_pasted_text(self, text: str, posted_at)` (3)
  - `async def forget_vacancy(self, vacancy_id: int)` (3)
  - `async def _answer(self, *, outcome=_OWN)` (11)
- `class WindowHooks` (24)
  - `def start(self) -> None` (4)
  - `def end(self) -> None` (4)
  - `def on_progress(self, stage, label, current, total) -> None` (4)
- `def wire(bot, ingestion, hooks=None)` (8)

### `tests/fakes/keyring.py` — 32 строк

Хранилище ключей в памяти вместо системного.

Зависит от: —

- `class MemoryKeyring(keyring.backend.KeyringBackend)` (22)
  - `def get_password(self, service: str, username: str) -> str | None` (2)
  - `def set_password(self, service: str, username: str, password: str) -> None` (2)
  - `def delete_password(self, service: str, username: str) -> None` (7)

### `tests/fakes/llm.py` — 287 строк

Подделка провайдера LLM: настоящий клиент поверх подставного транспорта.

Зависит от: `adapters.lm_chat`

- `def _troubles() -> list[tuple[str, object, str]]` (22)
- `def provider_trouble(*extra)` (9)
- `def provider_trouble_named(*extra)` (7)
- `def _picker(routes: dict)` (19)
  - `def pick(key: tuple[str, str])` (6)
- `def handler(routes: dict, sent: list, http)` (23)
  - `def handle(request)` (12)
- `def provider(routes: dict[tuple[str, str], httpx.Response | BaseException | list], *, api_key: str='') -> httpx.AsyncClient` (22)
- `def models_response(*ids: str) -> httpx.Response` (3)
- `def parsed_vacancy_answer(**fields) -> dict` (8)
- `def chat_json(payload: dict, *, finish_reason: str='stop') -> httpx.Response` (9)
- `def fit_answer(verdict: str, reason: str | None=None) -> httpx.Response` (8)
- `def letter_answer(body: str, subject: str='Отклик') -> httpx.Response` (3)
- `def factcheck_answer(verdict: str, issues=()) -> httpx.Response` (8)
- `def messages_of(request: httpx.Request) -> dict[str, str]` (9)
- `def data_block(request: httpx.Request) -> str` (9)
- `def warning_before_the_block(request: httpx.Request) -> str` (9)
- `def chat_response(content: str | None, *, finish_reason: str='stop') -> httpx.Response` (14)
- `def chat_request(**over) -> ChatRequest` (16)
- `def embeddings_request() -> httpx.Request` (3)
- `def embeddings_refused(status: int, text: str='') -> httpx.HTTPStatusError` (5)

### `tests/fakes/lm_studio.py` — 18 строк

Пустое соединение с языковой моделью — для сборок, что до неё не ходят.

Зависит от: —

- `class LmClient` (9)
  - `async def aclose(self) -> None` (2)

### `tests/fakes/site_home.py` — 29 строк

Подделка главной страницы сайта: настоящий клиент поверх подставного транспорта.

Зависит от: `tests.fakes.http`

- `def serve_home(monkeypatch, prepared: httpx.Response | BaseException, pages: dict | None=None) -> None` (9)
- `def home_page(*, head: str='') -> httpx.Response` (3)

### `tests/fakes/telegram.py` — 309 строк ⚠ подошёл к 300

Подделка клиента Pyrogram: отвечает на обращения и записывает их.

Зависит от: `tests.fakes.telegram_objects`

- `class FakeTelegramClient` (284)
  - `def loop(self)` (4)
  - `def add_handler(self, handler) -> None` (2)
  - `def _refuse_cold(self, target) -> None` (10)
  - `def _fail_if_asked(self, method: str) -> None` (6)
  - `async def get_chat(self, chat_id)` (14)
  - `async def get_chat_history(self, target, limit=100)` (12)
  - `async def invoke(self, query, retries=3, timeout=10.0, sleep_threshold=None)` (55)
  - `async def resolve_peer(self, peer_id)` (5)
  - `async def get_users(self, username)` (18)
  - `async def download_media(self, target, file_name=None, in_memory=False)` (21)
  - `async def _accept(self, kind: str, target, payload, caption=None)` (16)
  - `async def send_message(self, target, text)` (2)
  - `async def send_photo(self, target, path)` (2)
  - `async def send_document(self, target, path, caption=None)` (4)
  - `async def read_chat_history(self, target)` (4)
  - `async def connect(self)` (3)
  - `async def disconnect(self)` (3)
  - `async def send_code(self, phone)` (4)
  - `async def sign_in(self, phone_number=None, phone_code_hash=None, phone_code=None)` (3)
  - `async def check_password(self, password)` (3)
  - `async def get_me(self)` (6)
  - `async def start(self)` (3)
  - `async def stop(self)` (3)
  - `async def log_out(self)` (3)
  - `async def export_session_string(self)` (3)

### `tests/fakes/telegram_objects.py` — 195 строк

Построители объектов Telegram для проверок.

Зависит от: `tests.factories`

- `def message(*, text=None, caption=None, **extra) -> SimpleNamespace` (9)
- `def link_entity(*, offset: int, length: int, url: str) -> SimpleNamespace` (14)
- `def url_entity(*, offset: int, length: int) -> SimpleNamespace` (9)
- `def incoming(*, user_id=777, username=None, text='здравствуйте', **extra)` (26)
- `def my_dm(*, chat_id=777, username=None, msg_id=10, text='ответ с телефона', photo=None)` (27)
- `def post(msg_id: int, *, text=_UNSET, **extra)` (14)
- `def photo(*, small_file_id=None, big_file_id=None) -> SimpleNamespace` (3)
- `def document(name: str | None) -> SimpleNamespace` (3)
- `def chat(*, title=None, photo=None, **extra) -> SimpleNamespace` (3)
- `def user(*, username=None, photo=None, **extra) -> SimpleNamespace` (15)
- `def dialog(peer_id: int, top_message: int | None=None)` (17)

### `tests/fakes/ui_bot.py` — 152 строк

Бот, каким его видит окно: обращения, которые делает мост.

Зависит от: `backend.bot.pasted`, `backend.bot.rerun`

- `class Sent` (4)
- `class UiBot` (111)
  - `def _refuse_if_asked(self) -> None` (3)
  - `async def force_poll_once(self) -> str` (3)
  - `def cancel_current_poll(self) -> None` (2)
  - `def request_stop(self) -> None` (2)
  - `def kick(self) -> None` (2)
  - `async def run(self, *, once: bool=False) -> None` (7)
  - `async def ui_rerun_vacancy_pipeline(self, vacancy_id: int) -> RerunOutcome` (3)
  - `async def ui_ingest_pasted_text(self, text, posted_at) -> PastedOutcome` (3)
  - `async def ui_forget_vacancy(self, vacancy_id: int) -> bool` (3)
  - `async def mark_hr_chat_read(self, hr_id: int) -> int` (3)
  - `async def send_to_hr_chat(self, hr_id: int, text: str) -> Sent` (4)
  - `async def send_to_hr_media(self, hr_id: int, file_path: str) -> Sent` (4)
  - `async def log_out_session(self) -> None` (4)
  - `async def poll_channel_now(self, channel_id: int) -> str` (3)
  - `async def add_channel(self, username: str) -> tuple[int | None, str]` (3)
  - `async def run_aggregator_now(self, aggregator_id: int) -> str` (3)
  - `async def login_aggregator(self, aggregator_id: int) -> str` (3)
  - `async def apply_chosen_way(self, vacancy_id: int, way) -> str` (3)
  - `async def apply_all_new(self) -> str` (3)
  - `async def download_update(self) -> str` (3)
  - `def human_done(self, answer=None) -> None` (2)
  - `def reveal_browser(self) -> None` (2)
  - `async def delete_aggregator(self, aggregator_id: int) -> str` (3)

### `tests/fakes/ui_login.py` — 47 строк

Вход в Telegram, каким его видит окно: три шага и отказ от попытки.

Зависит от: `backend.telegram_login`

- `class UiLogin` (36)
  - `async def send_code(self, api_id: int, api_hash: str, phone: str) -> LoginStep` (3)
  - `async def confirm_code(self, code: str) -> LoginStep` (3)
  - `async def confirm_password(self, password: str) -> LoginStep` (3)
  - `async def forget(self) -> None` (3)

### `tests/test_config.py` — 66 строк

Следствия, которые наблюдают тесты `config.py`.

Зависит от: `config`, `tests.conftest`

Тестов: 6


### `tests/test_fakes_telegram.py` — 32 строк

Верность подделки Telegram настоящему клиенту.

Зависит от: `tests.fakes.telegram`

Тестов: 2


### `tests/test_harness_safety.py` — 198 строк

Сторож стенда: падает, если подмена не сработала.

Зависит от: `adapters`, `adapters.claude`, `adapters.gguf_embed`, `adapters.lm_chat`, `adapters.lm_studio`, `adapters.telegram`, `backend.models`, `backend.provider_config`, `config`, `tests.conftest`

Тестов: 14


### `tests/test_package_shadowing.py` — 32 строк

Сторож сборки: чужой каталог в `sys.path` не подменяет модули проекта.

Зависит от: —

Тестов: 1


### `tests/waiting.py` — 11 строк

Ожидание в тестах — с потолком: не наступи условие, тест падает, а не виснет.

Зависит от: —

- `async def wait_until(condition) -> None` (6)
  - `async def met()` (3)

## Абстракции с одной реализацией

- `AppUpdate` — наследник один: `System`
- `ChannelActions` — наследник один: `Channels`
- `Cv` — наследник один: `Profile`
- `Desktop` — наследник один: `System`
- `HrChat` — наследник один: `Hr`
- `Journal` — наследник один: `System`
- `Llm` — наследник один: `Settings`
- `Login` — наследник один: `Settings`
- `Mail` — наследник один: `Settings`
- `Model` — наследник один: `Failing`
- `Silent` — наследник один: `Stoppable`
- `VacancyActions` — наследник один: `Vacancies`
- `VacancyContacts` — наследник один: `Vacancies`
- `VacancyLinks` — наследник один: `Vacancies`
- `Wipe` — наследник один: `System`
- `_FakeSmtp` — наследник один: `_RudeSmtp`
