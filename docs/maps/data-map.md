# Карта данных

Собирается из кода, а не ведётся руками.
Править руками нельзя — правки затрёт следующая сборка.
У набора называется размер, а не содержимое.

## .

### `config.py`

- `APP_NAME` = `'JobBot'`
- `LOG_KEPT` = `3`
- `_DB_NAME` = `'jobbot.db'`

### `main.py`

- `LOG_BYTES` = `5 * 1024 * 1024`
- `logger` = `logging.getLogger(__name__)`

## adapters

### `adapters/agent_mcp.py`

- `SERVER_NAME` = `'jobbot'`
- `_START_SEC` = `10`
- `_GRACE_SEC` = `0.5`
- `_CLOSE_WAIT_SEC` = `5`
- `logger` = `logging.getLogger(__name__)`
- `class ToolServer`
  - `url: str`
  - `_server: uvicorn.Server`
  - `_task: asyncio.Task`

### `adapters/app_tied_process.py`

- `_log` = `logging.getLogger(__name__)`
- `_KILL_ON_JOB_CLOSE` = `8192`
- `_EXTENDED_LIMIT_INFORMATION` = `9`
- `_PROCESS_SET_QUOTA` = `256`
- `_PROCESS_TERMINATE` = `1`
- `_SNAPPROCESS` = `2`
- `_INVALID_HANDLE` = `wintypes.HANDLE(-1).value`
- `class _IoCounters(ctypes.Structure)`
  - `_fields_` = `[(name, ctypes.c_uint64) for name in ('ReadOpera…`
- `class _BasicLimit(ctypes.Structure)`
  - `_fields_` = `набор из 9`
- `class _ExtendedLimit(ctypes.Structure)`
  - `_fields_` = `набор из 6`
- `class _ProcessEntry(ctypes.Structure)`
  - `_fields_` = `набор из 10`
- `_job` = `None`

### `adapters/browser.py`

- `logger` = `logging.getLogger(__name__)`
- `BROWSER_DIR` = `get_data_dir() / 'browser'`
- `_PROGRAMS` = `набор из 3`
- `BROWSER_NAMES` = `набор из 6`
- `CHROME` = `набор из 6`
- `OPERA` = `набор из 6`
- `BRAVE` = `набор из 6`
- `VIVALDI` = `набор из 6`
- `YANDEX` = `набор из 6`
- `EDGE` = `набор из 6`
- `class InstalledBrowser`
  - `name: str`
  - `channel: str | None`
  - `executable: Path | None`
- `_SENDING_METHODS` = `frozenset({'POST', 'PUT', 'PATCH', 'DELETE'})`
- `_CAPTCHA_HOSTS` = `набор из 4`
- `_GOOGLE_CAPTCHA_PATH` = `'/recaptcha/'`
- `_CLOUDFLARE_CHECK_PATH` = `'/cdn-cgi/challenge-platform/'`
- `_PERSON_LAUNCH` = `словарь из 2`
- `_HIDE_WEBDRIVER` = `"Object.defineProperty(Navigator.prototype, 'web…`

### `adapters/claude.py`

- `_log` = `logging.getLogger(__name__)`
- `_CLAUDE_URL` = `f'https://{CLAUDE_HOST}'`
- `THINKING_ROOM` = `16000`
- `EFFORT` = `'high'`
- `REFUSED` = `'refusal'`
- `FINISH` = `словарь из 3`

### `adapters/claude_code.py`

- `MODELS` = `набор из 3`
- `NO_CLI` = `'Claude Code не установлен'`

### `adapters/claude_code_agent.py`

- `logger` = `logging.getLogger(__name__)`
- `_TOOL_TIMEOUT_MS` = `65 * 60 * 1000`
- `_LIMIT_STATUS` = `429`
- `_LIMIT_RE` = `re.compile('usage limit|limit reached|rate limit…`
- `class AgentEnd`
  - `ok: bool`
  - `detail: str`
  - `limit_exhausted: bool`
- `class AgentRun`
  - `system_prompt: str`
  - `task: str`
  - `mcp_url: str`
  - `model: str`
  - `web_search: bool`

### `adapters/claude_code_process.py`

- `logger` = `logging.getLogger(__name__)`
- `FRAME_OPEN` = `'***ИНСТРУКЦИИ***'`
- `FRAME_CLOSE` = `'***КОНЕЦ ИНСТРУКЦИЙ***'`
- `FRAME_PROMPT` = `f'Каждое сообщение начинается с блока между стро…`
- `_CLEAR` = `'/clear'`
- `_NOT_SUBSCRIPTION` = `набор из 6`
- `_NO_WINDOW` = `getattr(subprocess, 'CREATE_NO_WINDOW', 0)`
- `_LINE_LIMIT` = `16 * 1024 * 1024`
- `_CLEAR_WAIT_S` = `30.0`
- `class _Session`
  - `process: object`
  - `model: str`
- `_session: _Session | None` = `None`
- `_guard: tuple[asyncio.AbstractEventLoop, asyncio.Lock] | None` = `None`
- `_closing` = `False`

### `adapters/cv_text.py`

- `logger` = `logging.getLogger(__name__)`
- `_PARAGRAPH` = `qn('w:p')`
- `_WRAPPERS` = `frozenset({qn('w:tbl'), qn('w:tr'), qn('w:tc'), …`
- `_READERS` = `словарь из 4`
- `READABLE_SUFFIXES: tuple[str, ...]` = `tuple(_READERS)`
- `_LIES_ABOUT_FORMAT` = `набор из 4`

### `adapters/db.py`

- `logger` = `logging.getLogger(__name__)`

### `adapters/gguf_embed.py`

- `_log` = `logging.getLogger(__name__)`
- `CONTEXT_TOKENS` = `8192`
- `_LOAD_TROUBLES` = `набор из 4`

### `adapters/github_release.py`

- `LATEST` = `'https://api.github.com/repos/DeadEye2501/job_bo…`
- `ASSET` = `'JobBot.exe'`
- `_TIMEOUT_SEC` = `20.0`
- `_USER_AGENT` = `'JobBot-updater'`
- `class Release`
  - `tag: str`
  - `url: str`
  - `size: int`
  - `sha256: str`

### `adapters/lm_chat.py`

- `CHAT_PATH` = `'/v1/chat/completions'`
- `CUT_BY_LIMIT` = `'length'`
- `MODEL_REFUSED` = `claude.REFUSED`
- `class ChatRequest`
  - `purpose: str`
  - `messages: list[dict[str, str]]`
  - `max_tokens: int`
  - `temperature: float` = `0.0`
  - `timeout: float | None` = `None`
- `class ChatAnswer`
  - `text: str | None` = `None`
  - `finish_reason: str | None` = `None`
  - `error: str | None` = `None`

### `adapters/lm_embed.py`

- `EMBED_PATH` = `'/v1/embeddings'`

### `adapters/lm_models.py`

- `_log` = `logging.getLogger(__name__)`
- `PING` = `'ping'`
- `_EMBED_MARKERS` = `набор из 4`

### `adapters/lm_studio.py`

- `LLM_REQUEST_TIMEOUT_SEC` = `180.0`
- `LmClient` = `httpx.AsyncClient | claude.ClaudeClient | claude…`

### `adapters/site_home.py`

- `FETCH_TIMEOUT_SEC` = `8.0`
- `_USER_AGENT` = `'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Apple…`
- `_TITLE_SEPARATORS_RE` = `re.compile(' [-—|] ')`
- `_DECLARING_META` = `набор из 2`
- `_ICON_RELS` = `набор из 3`
- `_FALLBACK_ICON` = `'/favicon.ico'`
- `_ICON_LIMIT_BYTES` = `256 * 1024`
- `class SiteHints`
  - `declared: tuple[str, ...]` = `набор из 0`
  - `title_parts: tuple[str, ...]` = `набор из 0`
- `class SiteHome`
  - `hints: SiteHints`
  - `icons: tuple[str, ...]`

### `adapters/smtp_mail.py`

- `logger` = `logging.getLogger(__name__)`
- `_TIMEOUT_SEC` = `60`
- `class MailAccountConfig`
  - `address: str`
  - `host: str`
  - `port: int`
  - `password: str` = `field(repr=False)`
- `class OutgoingMail`
  - `to: str`
  - `subject: str`
  - `body: str`
  - `attachment: Path`

### `adapters/telegram.py`

- `_log` = `logging.getLogger(__name__)`
- `SESSIONS_DIR` = `get_data_dir() / 'sessions'`
- `SESSION_NAME` = `'job_bot'`
- `SEND_LOCKED` = `False`
- `_DIALOG_PAGE` = `100`

### `adapters/telegraph.py`

- `logger` = `logging.getLogger(__name__)`
- `ARTICLE_URL_RE` = `re.compile('https?://telegra\\.ph/[^\\s)\\]]*[^\…`
- `FETCH_TIMEOUT_SEC` = `20.0`
- `_USER_AGENT` = `'Mozilla/5.0 (compatible; JobBot/1.0)'`
- `_GONE_FOR_GOOD` = `frozenset({404, 410, 451})`

## alembic

### `alembic/env.py`

- `config` = `context.config`
- `target_metadata` = `Base.metadata`

### `alembic/versions/6cc10045aeb6_projects.py`

- `revision: str` = `'6cc10045aeb6'`
- `down_revision: Union[str, Sequence[str], None]` = `'c4d7e2a915b3'`
- `branch_labels: Union[str, Sequence[str], None]` = `None`
- `depends_on: Union[str, Sequence[str], None]` = `None`

### `alembic/versions/a9c3e1f07b42_aggregators.py`

- `revision: str` = `'a9c3e1f07b42'`
- `down_revision: Union[str, Sequence[str], None]` = `'e560edf8b958'`
- `branch_labels: Union[str, Sequence[str], None]` = `None`
- `depends_on: Union[str, Sequence[str], None]` = `None`
- `_SOURCE_COLUMNS` = `набор из 2`
- `_PROFILE_COLUMNS` = `набор из 6`

### `alembic/versions/c4d7e2a915b3_one_apply_trail.py`

- `revision: str` = `'c4d7e2a915b3'`
- `down_revision: Union[str, Sequence[str], None]` = `'a9c3e1f07b42'`
- `branch_labels: Union[str, Sequence[str], None]` = `None`
- `depends_on: Union[str, Sequence[str], None]` = `None`
- `_GONE_KINDS` = `набор из 4`

### `alembic/versions/e560edf8b958_init.py`

- `revision: str` = `'e560edf8b958'`
- `down_revision: Union[str, Sequence[str], None]` = `None`
- `branch_labels: Union[str, Sequence[str], None]` = `None`
- `depends_on: Union[str, Sequence[str], None]` = `None`

## backend

### `backend/agent/availability.py`

- `NO_DRIVER` = `'Для агрегаторов нужен Claude Code: выберите его…`
- `NO_BROWSER` = `f"Не найден браузер на движке Chromium: {', '.jo…`

### `backend/agent/human_gate.py`

- `logger` = `logging.getLogger(__name__)`
- `LIMIT_SEC` = `3600.0`
- `_DONE` = `'готово'`
- `_STOPPED` = `'обход остановлен; заверши работу'`
- `_NO_BROWSER` = `_NoBrowser()`

### `backend/agent/jobs.py`

- `class Source`
  - `id: int`
  - `name: str`
  - `host: str | None`
  - `last_run_at: datetime | None`
- `class Finished`
  - `result: str`
  - `reason: str`
- `class Failed`
  - `reason: str`
- `class Applied`
  - `application_id: int`
- `Outcome` = `Finished | Failed | Applied`
- `class LoginJob`
  - `source: Source`
  - `outcome: Outcome | None` = `None`
- `class SeekJob`
  - `source: Source`
  - `limit: int`
  - `submitted: int` = `0`
  - `found: list[int]` = `field(default_factory=list)`
  - `refused: bool` = `False`
  - `outcome: Outcome | None` = `None`
- `class ApplyJob`
  - `vacancy_id: int`
  - `way: Way`
  - `profile_id: int`
  - `simulated: bool`
  - `letter_writer: str`
  - `letter_checks: int` = `0`
  - `outcome: Outcome | None` = `None`
- `RESULTS` = `словарь из 3`
- `HUMAN_KINDS` = `набор из 2`

### `backend/agent/kit.py`

- `class SessionPlan`
  - `system_prompt: str`
  - `task: str`
  - `tools: list[Callable]`
  - `web_search: bool`
- `RunSession` = `Callable[[SessionPlan], Awaitable[AgentEnd]]`
- `T` = `TypeVar('T')`
- `class AgentKit`
  - `pipeline: IngestionPipeline`
  - `browser: BrowserHost`
  - `gate: HumanGate`
  - `run_session: RunSession`
  - `today: date`

### `backend/agent/prompts/applier.py`

- `APPLIER_PROMPT` = `'Твоя задача — откликнуться на одну вакансию одн…`
- `_SIMULATION` = `'Режим симуляции: пройди всё до последней кнопки…`
- `_METHODS` = `словарь из 2`
- `_WRITERS` = `dict(zip(LETTER_WRITERS, ('Письмо пишет: приложе…`

### `backend/agent/prompts/frame.py`

- `_INTRO` = `'Ты работаешь агентом приложения, которое ищет р…`
- `_RULES_BEFORE_HUMAN` = `набор из 6`
- `_HUMAN_RULE` = `'Капча — need_human с kind="captcha"; слетевший …`
- `_RULES_AFTER_HUMAN` = `набор из 2`
- `_BROWSER` = `'Браузер. browser_snapshot отдаёт страницу текст…`

### `backend/agent/prompts/login.py`

- `LOGIN_PROMPT` = `'Твоя задача — понять, вошёл ли человек на этот …`

### `backend/agent/prompts/screening.py`

- `SCREENING_RULES` = `'Скрининг — вопросы работодателя в форме отклика…`

### `backend/agent/prompts/seeker.py`

- `_SELECTION` = `'Отбор — средний. После тебя каждую вакансию про…`
- `SEEKER_PROMPT` = `'Твоя задача — найти на сайте агрегатора свежие …`
- `WEB_SEEKER_PROMPT` = `'Твоя задача — найти по всей сети свежие ваканси…`

### `backend/agent/sessions.py`

- `SESSION_LIMIT_SEC` = `3 * 3600`

### `backend/agent/stops.py`

- `RUN_STOPPERS` = `набор из 2`

### `backend/agent/tools_applier.py`

- `_ALLOWED` = `словарь из 2`
- `_Text` = `Annotated[str, StringConstraints(strip_whitespac…`
- `class ScreeningPair(TypedDict)`
  - `question: _Text`
  - `answer: _Text`
- `class _Report`
  - `via: str`
  - `target: str`
  - `letter: str | None`
  - `screening: list[tuple[bool, str]]`

### `backend/agent/tools_browser.py`

- `logger` = `logging.getLogger(__name__)`
- `_WAIT_MS` = `15000`
- `_SNAPSHOT_LIMIT` = `60000`
- `_CUT_MARK` = `'\n… снимок обрезан: страница длиннее, чем помещ…`

### `backend/agent/tools_common.py`

- `_ALREADY_APPLIED` = `'Отклик уже записан, итог не меняется: второй от…`

### `backend/agent/tools_letter.py`

- `_CHECKS_ALLOWED` = `2`
- `_ENOUGH` = `'отбито дважды: отправляй без письма, если поле …`

### `backend/agent/tools_seeker.py`

- `WHAT` = `'найденная агентом вакансия'`
- `BARRED` = `'сайт в чёрном списке человека'`
- `class _Page`
  - `text: str`
  - `url: str`
  - `published: str`
  - `contacts: list[str]`

### `backend/app_version.py`

- `VERSION` = `'1.2.0'`

### `backend/applying/browser.py`

- `_NO_OUTCOME` = `'агент закончил без итога'`

### `backend/applying/email.py`

- `logger` = `logging.getLogger(__name__)`

### `backend/applying/result.py`

- `logger` = `logging.getLogger(__name__)`
- `class TelegramClosed`
  - `until: float`
- `class SiteClosed`
  - `site_id: int`
- `Lesson` = `TelegramClosed | SiteClosed`
- `class Missed`
  - `reason: str`
  - `lesson: Lesson | None` = `None`
- `class Unfit`
  - `reason: str`
- `Outcome` = `Literal['applied'] | Missed | Unfit`
- `GONE` = `Missed('вакансия удалена')`

### `backend/applying/run.py`

- `logger` = `logging.getLogger(__name__)`
- `Executor` = `Callable[[AgentKit, int, Way], Awaitable[Outcome…`
- `EXECUTORS: dict[str, Executor]` = `словарь из 4`

### `backend/applying/telegram.py`

- `logger` = `logging.getLogger(__name__)`
- `class _Errand`
  - `vacancy_id: int`
  - `hr_id: int`
  - `peer: int | str`
  - `parsed: ParsedVacancy`
  - `prior_count: int`
  - `title: str`
  - `channel_ref: str | None`

### `backend/applying/telegram_ban.py`

- `logger` = `logging.getLogger(__name__)`

### `backend/applying/telegram_letter.py`

- `logger` = `logging.getLogger(__name__)`
- `RECENT_SEND_WINDOW_DAYS` = `14`
- `class Letter`
  - `text: str`
  - `attachment: object | None`

### `backend/applying/world.py`

- `AWAITS_APPLICATION` = `Vacancy.status == VacancyStatus.NEW`

### `backend/bootstrap.py`

- `logger` = `logging.getLogger(__name__)`
- `_PROJECT_ROOT` = `Path(__file__).resolve().parent.parent`

### `backend/bot/aggregators.py`

- `logger` = `logging.getLogger(__name__)`
- `AgentOutcome` = `Literal[work.WorkOutcome, 'missing', 'locked', '…`

### `backend/bot/apply.py`

- `ApplyOutcome` = `Literal[work.WorkOutcome, 'failed', 'unfit', 'mi…`

### `backend/bot/can_send.py`

- `NO_TARGET` = `'нет адресата'`
- `BLACKLISTED` = `'чёрный список'`
- `SENDING_LOCKED` = `'отправка заглушена'`
- `class SendPermission`
  - `target: int | str | None` = `None`
  - `refusal: str | None` = `None`
  - `blacklist_value: str | None` = `None`

### `backend/bot/channels.py`

- `logger` = `logging.getLogger(__name__)`
- `ChannelPollOutcome` = `Literal[work.WorkOutcome, flow_channels.PollOutc…`
- `ChannelAddOutcome` = `Literal['created', 'exists', 'invalid', 'error']`

### `backend/bot/chat.py`

- `logger` = `logging.getLogger(__name__)`
- `EMPTY_MESSAGE` = `'Пустое сообщение.'`
- `_REFUSAL_TEXTS` = `словарь из 3`

### `backend/bot/client.py`

- `logger` = `logging.getLogger(__name__)`
- `class Bot`
  - `loop: asyncio.AbstractEventLoop | None`
  - `current_poll_task: asyncio.Task | None`
  - `launched_task: asyncio.Task | None`
  - `dialogs: list[DialogPeer] | None`

### `backend/bot/loop.py`

- `logger` = `logging.getLogger(__name__)`
- `_SETTLE_SEC` = `8`

### `backend/bot/media.py`

- `logger` = `logging.getLogger(__name__)`
- `MEDIA_DIR` = `get_data_dir() / 'media'`
- `PHOTO_EXTS` = `набор из 4`
- `_PHOTO_TYPES` = `набор из 3`
- `PHOTO_SIZE_LIMIT` = `10 * 1024 * 1024`
- `DOCUMENT_SIZE_LIMIT` = `50 * 1024 * 1024`

### `backend/bot/pasted.py`

- `logger` = `logging.getLogger(__name__)`
- `PastedOutcome` = `Literal[work.WorkOutcome, flow_pasted.PastedInta…`

### `backend/bot/rerun.py`

- `logger` = `logging.getLogger(__name__)`
- `RerunOutcome` = `Literal[work.WorkOutcome, flow_rerun.RerunPipeli…`

### `backend/bot/slot.py`

- `logger` = `logging.getLogger(__name__)`
- `CycleOutcome` = `Literal['ok', 'busy', 'cancelled', 'error']`

### `backend/bot/turn.py`

- `logger` = `logging.getLogger(__name__)`

### `backend/bot/update.py`

- `logger` = `logging.getLogger(__name__)`
- `_LABEL` = `'Обновление'`
- `DownloadOutcome` = `Literal[slot.CycleOutcome, update_download.Updat…`

### `backend/bot/updates.py`

- `logger` = `logging.getLogger(__name__)`

### `backend/bot/work.py`

- `logger` = `logging.getLogger(__name__)`
- `HUMAN_TIMEOUT_NOTE` = `'Капча не пройдена — работа остановлена.'`
- `LIMIT_NOTE` = `'Исчерпан лимит подписки Claude Code — работа ос…`
- `AgentStop` = `Literal['human_timeout', 'limit']`
- `WorkOutcome` = `Literal[slot.CycleOutcome, AgentStop]`

### `backend/crypto.py`

- `logger` = `logging.getLogger(__name__)`
- `_KEYRING_SERVICE` = `'JobBot'`
- `_KEYRING_KEY` = `'master_key'`
- `_REJECTED_KEYRING_BACKENDS` = `набор из 5`

### `backend/domain/alphabet.py`

- `CYRILLIC_LETTER` = `re.compile('[а-яёА-ЯЁ]')`
- `LATIN_LETTER` = `re.compile('[a-zA-Z]')`
- `CYRILLIC_WORD` = `re.compile('[а-яёА-ЯЁ]+')`

### `backend/domain/apply_order.py`

- `VIA_TELEGRAM` = `ApplicationVia.TELEGRAM.value`
- `VIA_AGGREGATOR` = `ApplicationVia.AGGREGATOR.value`
- `VIA_FORM` = `ApplicationVia.FORM.value`
- `VIA_EMAIL` = `ApplicationVia.EMAIL.value`
- `class Way`
  - `method: str`
  - `target: str`
  - `aggregator_id: int | None`
- `class KnownSite`
  - `id: int`
  - `host: str | None`
  - `logged_in: bool` = `True`
- `class VacancyFacts`
  - `hr_handle: str | None`
  - `source_url: str | None`
  - `source_site: KnownSite | None`
  - `contacts: list[str]`
- `class World`
  - `telegram_open: bool`
  - `mail_ready: bool`
  - `agent_ready: bool`
  - `sites: list[KnownSite]`
  - `closed_sites: set[int]`

### `backend/domain/company_hosts.py`

- `AGGREGATOR_HOSTS` = `frozenset({'t.me', 'telegram.me', 'telegram.org'…`
- `AGGREGATOR_BRANDS` = `frozenset({'indeed', 'stepstone'})`

### `backend/domain/company_names.py`

- `ADDRESS_START_RE` = `re.compile('^[a-z][a-z0-9+.\\-]*://', re.IGNOREC…`

### `backend/domain/contact_keys.py`

- `EMAIL_PATTERN` = `'[^\\s@]+@[^\\s@]+\\.[a-zA-Z]{2,}'`
- `PHONE_PATTERN` = `'\\+?\\d[\\d\\s()-]{7,}\\d'`
- `_SCHEMES` = `набор из 2`
- `_ADDRESS_RE` = `re.compile(EMAIL_PATTERN)`
- `_PHONE_RE` = `re.compile(PHONE_PATTERN)`

### `backend/domain/currency.py`

- `CURRENCY_WRITINGS: tuple[tuple[str, str], ...]` = `набор из 6`

### `backend/domain/dedup.py`

- `logger` = `logging.getLogger(__name__)`

### `backend/domain/funnel.py`

- `FIT_EXCLUDE: frozenset[VacancyStatus]` = `frozenset({VacancyStatus.NOT_FIT, VacancyStatus.…`
- `APPLIED: frozenset[VacancyStatus]` = `frozenset({VacancyStatus.APPLIED, VacancyStatus.…`
- `RESPONDED: frozenset[VacancyStatus]` = `frozenset({VacancyStatus.ANSWERED, VacancyStatus…`
- `INVITED: frozenset[VacancyStatus]` = `frozenset({VacancyStatus.INVITATION, VacancyStat…`
- `IN_PROGRESS_STEP: frozenset[VacancyStatus]` = `frozenset({VacancyStatus.INVITATION, VacancyStat…`

### `backend/domain/hosts.py`

- `class AddressParts(NamedTuple)`
  - `host: str`
  - `path: str`
  - `query: str`
  - `fragment: str`
- `_ZONE_SECOND_LEVELS` = `frozenset({'co', 'com', 'net', 'org', 'ac', 'gov…`

### `backend/domain/image_types.py`

- `_IMAGE_SIGNATURES` = `набор из 4`

### `backend/domain/mail_servers.py`

- `SSL_PORT` = `465`
- `STARTTLS_PORT` = `587`
- `_GMAIL` = `набор из 2`
- `_YANDEX` = `набор из 2`
- `_MAIL_RU` = `набор из 2`
- `_OUTLOOK` = `набор из 2`
- `_KNOWN_SERVERS` = `словарь из 12`

### `backend/domain/resume_marks.py`

- `RESUME_MARKS` = `frozenset({'#cv', '#resume', '#резюме', '#ищураб…`
- `AMBIGUOUS_MARKS` = `frozenset({'#available', '#cv_'})`
- `_MARK` = `re.compile('(?<!\\S)#\\w+')`

### `backend/domain/salary.py`

- `_AMOUNT_RE` = `re.compile('(?P<num>\\d+(?:[ \xa0\u202f\u2009,.]…`
- `_CURRENCY_WORD` = `'|'.join((word for _, word in CURRENCY_WRITINGS)…`
- `_RANGE_GLUE_RE` = `re.compile(f'\\s*(?:(?:{_CURRENCY_WORD})\\s*)?(?…`
- `_THOUSAND` = `набор из 3`
- `_FRACTION_RE` = `re.compile('[.,]\\d{1,2}$')`
- `_MAX_AMOUNT` = `2 ** 63 - 1`
- `_NEGOTIABLE_RE` = `re.compile('собесед|договорённ|договоренн|догово…`
- `_LEADING_NOT_MONEY_RE` = `re.compile('опыт\\w*|стаж\\w*|бонус\\w*|преми\\w…`
- `_TRAILING_NOT_MONEY_RE` = `re.compile('лет|года|раза?|дней|дня|день|месяца|…`
- `_PREPOSITIONS` = `'от|до|с'`
- `_WORD_BEFORE_RE` = `re.compile(f'([a-zа-яё]+)(?:\\s+(?:{_PREPOSITION…`
- `_PREPOSITION_RE` = `re.compile(f'(?<![а-яё])({_PREPOSITIONS})\\s*$')`
- `_CURRENCY_BEFORE_RE` = `re.compile(f'(?:{_CURRENCY_WORD})\\s*$')`
- `_CURRENCY_AFTER_RE` = `re.compile(f'^\\s*(?:{_CURRENCY_WORD})')`
- `_WORD_AFTER_RE` = `re.compile('^(?:-[а-яё]{1,2})?\\s*([a-zа-яё]+)')`
- `_CURRENCIES: tuple[tuple[str, re.Pattern[str]], ...]` = `tuple(((sign, re.compile(word)) for sign, word i…`

### `backend/domain/scoring.py`

- `logger` = `logging.getLogger(__name__)`

### `backend/domain/sentence.py`

- `_ENDED_RE` = `re.compile('[.!?…:][»\\"\')\\]]*$')`

### `backend/domain/skill_names.py`

- `T` = `TypeVar('T')`
- `_SEPARATORS_RE` = `re.compile('[\\s\\-_./]+')`

### `backend/domain/spellings.py`

- `T` = `TypeVar('T')`

### `backend/domain/taxonomy.py`

- `GRADES: tuple[str, ...]` = `набор из 4`
- `WORK_FORMATS: tuple[str, ...]` = `набор из 3`
- `GRADE_SPELLINGS: dict[str, tuple[str, ...]]` = `словарь из 4`
- `WORK_FORMAT_SPELLINGS: dict[str, tuple[str, ...]]` = `словарь из 3`
- `WORK_FORMAT_LABELS_RU: dict[str, str]` = `словарь из 3`
- `CEFR_LEVELS: tuple[str, ...]` = `набор из 6`
- `NATIVE_LEVEL` = `'native'`
- `LEVEL_SPELLINGS: dict[str, tuple[str, ...]]` = `словарь из 6`
- `LEVELS_BY_SPELLING: tuple[tuple[str, str], ...]` = `tuple(sorted(((spelling.replace('-', ' '), level…`
- `LEVEL_WHEN_UNTOLD: str` = `CEFR_LEVELS[-1]`
- `LANGUAGE_LEVELS: tuple[str, ...]` = `CEFR_LEVELS + (NATIVE_LEVEL,)`

### `backend/domain/telegram_identity.py`

- `_TG_USERNAME_RE` = `re.compile('^[A-Za-z][A-Za-z0-9_]{4,31}$')`
- `_TG_TYPED_USERNAME_RE` = `re.compile('^[A-Za-z][A-Za-z0-9_]{3,31}$')`
- `_TG_RESERVED_PATHS` = `набор из 6`
- `class DialogPeer`
  - `peer_id: int`
  - `username: str | None` = `None`

### `backend/domain/transitions.py`

- `ALLOWED_AUTO_TRANSITIONS: dict[VacancyStatus, frozenset[VacancyStatus]]` = `словарь из 11`
- `GHOSTING_TIMEOUT_DAYS` = `14`
- `GHOSTING_ELIGIBLE_FROM: frozenset[VacancyStatus]` = `frozenset({VacancyStatus.APPLIED, VacancyStatus.…`
- `APPLY_MOVES_FROM: frozenset[VacancyStatus]` = `frozenset({VacancyStatus.NEW, VacancyStatus.NOT_…`

### `backend/domain/verdict.py`

- `EMPTY_SKIP_PREFIX` = `'empty: '`
- `EMPTY_SKIP_REASON` = `f'{EMPTY_SKIP_PREFIX}no meaningful fields'`
- `TRASH_SKIP_PREFIX` = `'trash: '`
- `JUNK_SKIP_PREFIXES` = `набор из 2`
- `LLM_SKIP_PREFIX` = `'llm: '`
- `TRUNCATED_SKIP_REASON` = `f'{LLM_SKIP_PREFIX}ответ модели не поместился'`
- `REFUSED_SKIP_REASON` = `f'{LLM_SKIP_PREFIX}модель отказалась отвечать'`

### `backend/flows/aggregator_name.py`

- `logger` = `logging.getLogger(__name__)`

### `backend/flows/aggregator_round.py`

- `logger` = `logging.getLogger(__name__)`

### `backend/flows/channels.py`

- `logger` = `logging.getLogger(__name__)`
- `BATCH_FLUSH_EVERY` = `10`
- `_SILENCE_BEFORE_DROPPING_THE_CHANNEL` = `3`
- `PollOutcome` = `Literal['ok', 'missing', 'blacklisted', 'error']`

### `backend/flows/cleanup.py`

- `logger` = `logging.getLogger(__name__)`
- `_NO_TRASH_EVENT` = `object()`

### `backend/flows/dm.py`

- `logger` = `logging.getLogger(__name__)`
- `OutgoingDmOutcome` = `Literal['stored', 'already_stored', 'not_stored'…`
- `class DmHelpers`
  - `session_factory: Any`
  - `lm_client: Any` = `None`
  - `lm_chat_model: str | None` = `None`
  - `client: Any` = `None`
  - `schedule_classification: Any` = `None`
- `class _Attachment`
  - `kind: str | None` = `None`
  - `path: str | None` = `None`
  - `name: str | None` = `None`

### `backend/flows/dm_backfill.py`

- `logger` = `logging.getLogger(__name__)`
- `_DM_CATCHUP_BATCH_SIZE` = `20`
- `_DM_CATCHUP_BATCH_DELAY_SEC` = `1.0`
- `class DmHooks`
  - `on_message_persisted: Any` = `None`
  - `on_vacancies_changed: Any` = `None`

### `backend/flows/dm_classify.py`

- `logger` = `logging.getLogger(__name__)`

### `backend/flows/dm_sync.py`

- `logger` = `logging.getLogger(__name__)`

### `backend/flows/embeddings.py`

- `logger` = `logging.getLogger(__name__)`
- `_EMBED_MAX_CHARS` = `6000`

### `backend/flows/events.py`

- `logger` = `logging.getLogger(__name__)`

### `backend/flows/fit_refusal.py`

- `logger` = `logging.getLogger(__name__)`

### `backend/flows/ghosting.py`

- `logger` = `logging.getLogger(__name__)`

### `backend/flows/ingest.py`

- `logger` = `logging.getLogger(__name__)`

### `backend/flows/intake.py`

- `logger` = `logging.getLogger(__name__)`

### `backend/flows/linked_article.py`

- `logger` = `logging.getLogger(__name__)`
- `_MAX_ARTICLES` = `3`

### `backend/flows/parse.py`

- `logger` = `logging.getLogger(__name__)`
- `class Judged`
  - `stored: bool`
  - `fresh_hr: HR | None` = `None`

### `backend/flows/parse_queue.py`

- `logger` = `logging.getLogger(__name__)`

### `backend/flows/parse_write.py`

- `logger` = `logging.getLogger(__name__)`
- `class Outcome`
  - `status: VacancyStatus`
  - `skip_reason: str | None`
  - `score: int`
  - `keep_previous_stack: bool`

### `backend/flows/pasted.py`

- `logger` = `logging.getLogger(__name__)`
- `PastedIntakeOutcome` = `Literal['ok', 'duplicate', 'embed', 'llm', 'tras…`
- `WHAT` = `'вставленный текст'`

### `backend/flows/pipeline.py`

- `logger` = `logging.getLogger(__name__)`
- `class LmProviders`
  - `chat_client: object`
  - `chat_model: str`
  - `embed_client: object`
  - `embed_model: str`
- `class IngestionPipeline`
  - `profile_block: str`
  - `skills_cache: list[ProfileSkill]`
  - `profile_cache: CandidateProfile`
  - `blacklist_patterns: list[str]`
  - `dm_debounce: DmDebounce`
  - `DM_CLASSIFY_DEBOUNCE_SEC` = `60.0`
  - `DM_CLASSIFY_STOP_TIMEOUT_SEC` = `5.0`

### `backend/flows/rerun.py`

- `logger` = `logging.getLogger(__name__)`
- `class _Origin`
  - `raw_text: str`
  - `channel_username: str`
  - `msg_id: int | None`
  - `status: VacancyStatus`
  - `history_id: int | None`
- `RerunPipelineOutcome` = `Literal['ok', 'missing', 'no_text', 'llm']`
- `RECOVERED_PER_TURN` = `10`
- `LONGEST_WAIT` = `timedelta(days=1)`

### `backend/flows/sameness.py`

- `class Match`
  - `kind: str`
  - `vacancy_id: int | None`
  - `embedding: list[float] | None`

### `backend/health.py`

- `logger` = `logging.getLogger(__name__)`

### `backend/incoming.py`

- `_HOMOGLYPHS` = `str.maketrans('авсеАВСЕ', 'abceABCE')`

### `backend/llm/agent_letter.py`

- `logger` = `logging.getLogger(__name__)`
- `MAX_LETTER_TOKENS` = `2500`
- `WRITE_LETTER_PROMPT` = `'Ты пишешь сопроводительное письмо к отклику на …`
- `class Letter`
  - `subject: str`
  - `body: str`
- `class LetterAsk`
  - `profile_text: str`
  - `title: str`
  - `vacancy_text: str`
  - `language: str`
  - `limit: int | None`

### `backend/llm/answers.py`

- `ONLY_JSON` = `'Никакого текста вне JSON. Никакого markdown. Ни…`
- `QUOTE_TRANSLATION` = `str.maketrans({'“': '"', '”': '"', '‘': "'", '’'…`
- `TRUNCATED_TROUBLE` = `'truncated'`

### `backend/llm/candidate.py`

- `class CandidateLanguage`
  - `name: str`
  - `level: str`
- `class CandidateProfile`
  - `title: str | None` = `None`
  - `location: str | None` = `None`
  - `grades: list[str]` = `field(default_factory=list)`
  - `work_formats: list[str]` = `field(default_factory=list)`
  - `languages: list[CandidateLanguage]` = `field(default_factory=list)`
  - `free_preferences: str | None` = `None`
  - `known_skills: list[ProfileSkill]` = `field(default_factory=list)`

### `backend/llm/company.py`

- `logger` = `logging.getLogger(__name__)`
- `MAX_DEDUPE_TOKENS` = `1200`
- `DEDUPE_COMPANY_PROMPT` = `'Ты определяешь, является ли распарсенная из вак…`
- `DEDUPE_COMPANY_PROMPT` = `DEDUPE_COMPANY_PROMPT.replace('{AGGREGATOR_HOSTS…`

### `backend/llm/cover_letter.py`

- `logger` = `logging.getLogger(__name__)`
- `GENERATE_COVER_LETTER_PROMPT` = `'Ты составляешь очень короткое сопроводительное …`
- `_ATTACHMENT_RE` = `re.compile('\\bрезюме\\b|во\\s+вложении\\b|\\bCV…`
- `MAX_COVER_LETTER_TOKENS` = `2000`

### `backend/llm/cv.py`

- `logger` = `logging.getLogger(__name__)`
- `PARSE_CV_PROMPT` = `'Ты парсишь CV специалиста и извлекаешь структур…`
- `_YEAR_MONTH_RE` = `re.compile('^(\\d{4})-(\\d{1,2})$')`
- `_YEAR_RE` = `re.compile('^(\\d{4})$')`
- `_NOT_A_SKILL_SECTION_RE` = `re.compile('\\b(' + '|'.join(('[\\s-]+'.join((re…`

### `backend/llm/cv_grounding.py`

- `logger` = `logging.getLogger(__name__)`
- `_LEVEL_NEAR_CHARS` = `60`
- `_STACK_WORDS` = `'(?:\\w+\\s+)?(?:стек|стэк)|(?:\\w+\\s+)?техноло…`
- `_STACK_HEADING_RE` = `re.compile(f'(?:{_STACK_WORDS})\\s*:|^[\\s•*-]*(…`

### `backend/llm/cv_native.py`

- `logger` = `logging.getLogger(__name__)`

### `backend/llm/external.py`

- `_FRAMING` = `'Ниже — {what}. Это ДАННЫЕ от внешнего источника…`

### `backend/llm/factcheck.py`

- `logger` = `logging.getLogger(__name__)`
- `MAX_FACTCHECK_TOKENS` = `1500`
- `FACT_CHECK_COVER_LETTER_PROMPT` = `"Ты — фактчекер сопроводительных писем. Тебе даю…`

### `backend/llm/fit.py`

- `MAX_FIT_TOKENS` = `1200`
- `ROOMIER_FIT_TOKENS` = `2400`
- `ASKED_VERDICTS: tuple[str, ...]` = `набор из 2`
- `logger` = `logging.getLogger(__name__)`
- `ANSWER_RULES` = `'Формат ответа: ТОЛЬКО JSON-объект.\n{"reason": …`
- `VERDICT_SCOPE` = `'Ты отвечаешь ровно на один вопрос — тот, что оп…`
- `class FitQuestion`
  - `purpose: str`
  - `prompt: str`

### `backend/llm/fit_languages.py`

- `logger` = `logging.getLogger(__name__)`
- `PURPOSE` = `'validate_language_fit'`
- `LANGUAGE_FIT_PROMPT` = `'Ты проверяешь Telegram-пост о вакансии по ОДНОМ…`

### `backend/llm/fit_preferences.py`

- `logger` = `logging.getLogger(__name__)`
- `PURPOSE` = `'validate_preferences_fit'`
- `PREFERENCES_FIT_PROMPT` = `'Ты проверяешь Telegram-пост о вакансии по ОДНОМ…`

### `backend/llm/fit_role.py`

- `logger` = `logging.getLogger(__name__)`
- `PURPOSE` = `'validate_role_fit'`
- `ROLE_FIT_PROMPT` = `'Ты проверяешь Telegram-пост о вакансии по ОДНОМ…`

### `backend/llm/genre.py`

- `logger` = `logging.getLogger(__name__)`
- `MAX_GENRE_TOKENS` = `1200`
- `ROOMIER_GENRE_TOKENS` = `2400`
- `CLASSIFY_POST_GENRE_PROMPT` = `'Ты определяешь ЖАНР телеграм-поста из канала с …`

### `backend/llm/hallucination.py`

- `_CEFR_ALT` = `'|'.join(CEFR_LEVELS)`
- `_GRADE_ALT` = `'|'.join(GRADES)`
- `_CEFR_LEVEL_RE` = `re.compile('\\b(' + '|'.join((level.lower() for …`
- `_GENERIC_HALLUCINATION_MARKERS: tuple[tuple[re.Pattern[str], re.Pattern[str]], ...]` = `набор из 2`
- `_REASON_STYLE_VIOLATIONS: tuple[re.Pattern[str], ...]` = `набор из 10`
- `_LANGUAGE_ROOT_OVERRIDES: dict[str, str]` = `словарь из 23`
- `_MIN_LANG_ROOT_LEN` = `4`

### `backend/llm/hr_reply.py`

- `logger` = `logging.getLogger(__name__)`
- `MAX_CLASSIFY_TOKENS` = `1200`
- `CLASSIFY_HR_REPLY_PROMPT_TEMPLATE` = `'Ты классифицируешь ответ HR-а кандидату по тому…`

### `backend/llm/rules.py`

- `RESUME_MARK_LINE` = `', '.join((f'«{mark}»' for mark in sorted(RESUME…`
- `SELF_OFFER_MARKERS` = `'\n'.join(('РУССКИЙ: «ищу работу», «ищу вакансию…`
- `FACT_KINDS` = `'\n'.join(('- Технологии, инструменты, языки, фр…`
- `NOT_IN_THE_PROFILE` = `'нет в блоке кандидата ни дословно, ни по смыслу…`
- `TONE_RULE` = `'Всё, что пишешь работодателю от имени человека,…`
- `GENDER_RULE` = `'Родовые формы — по полю «Пол» анкеты; пол не ук…`
- `LATIN_NAME_RULE` = `'Имя и фамилию пиши алфавитом текста, в котором …`
- `ATTRIBUTION_RULES` = `'\n'.join(('- Атрибуция достижений: каждое дости…`
- `FACTS_RULE` = `'Факты о человеке — только из анкеты; анкета и е…`
- `EXAMPLE_SOURCE` = `'При прочих равных пример из места работы приори…`
- `LETTER_SHAPE` = `'Состав письма:\n1. Приветствие.\n2. Кто пишет: …`
- `LETTER_RULES` = `'\n'.join((LETTER_SHAPE, 'Голос и факты:', TONE_…`
- `_TEMPLATE_PLACEHOLDER_RE` = `re.compile('<[\\wА-Яа-яЁё][^>\\n]{0,40}>')`
- `AGGREGATOR_HOSTS_LINE` = `', '.join(sorted(AGGREGATOR_HOSTS | AGGREGATOR_B…`
- `GRADE_MARKERS` = `', '.join((f"«{grade}/{'/'.join(spellings)}»" fo…`
- `FORMAT_MARKERS` = `', '.join((f"«{'/'.join((one, *(w for w in spell…`
- `NOT_A_SKILL_SECTIONS: tuple[str, ...]` = `набор из 7`
- `NOT_A_SKILL_LINE` = `', '.join((f'«{one}»' for one in NOT_A_SKILL_SEC…`
- `REQUIREMENT_WRAPPERS: tuple[str, ...]` = `набор из 10`
- `WRAPPER_LINE` = `', '.join((f'«{one}»' for one in REQUIREMENT_WRA…`
- `APPLY_CONTACTS` = `'Telegram (@username, t.me/...), email (jobs@acm…`
- `GEO_LIMIT_MARKERS` = `'«Удалённо в РФ», «удалёнка только из России», «…`
- `VACANCY_TEXT_CHARS` = `6000`

### `backend/llm/site_name.py`

- `logger` = `logging.getLogger(__name__)`
- `MAX_SITE_NAME_TOKENS` = `1200`
- `MAX_NAME_CHARS` = `40`
- `SITE_NAME_PROMPT` = `'Задача — назвать сервис по адресу его сайта так…`

### `backend/llm/skills.py`

- `logger` = `logging.getLogger(__name__)`
- `_VERSION_SUFFIX_RE` = `re.compile('[\\s.\\-_]*[vV]?\\d+(?:[.\\-_]\\d+)*…`
- `_DIGIT_BELONGS_TO_NAME` = `frozenset({'s3', 'c4', 'web3', 'html5', 'css3', …`
- `_WRAPPER_HEAD` = `'^\\s*(?:[а-яё]+\\s+){0,2}(?:' + '|'.join(REQUIR…`
- `_WRAPPED_BY_PREPOSITION_RE` = `re.compile(_WRAPPER_HEAD + '.*?\\s(?:с|со|в|во|н…`
- `_WRAPPED_BARE_RE` = `re.compile(_WRAPPER_HEAD + '\\s+(?P<tail>\\S.*)$…`
- `_MAX_WRAPPED_WORDS` = `4`
- `_LISTED_RE` = `re.compile('\\s*,\\s*|\\s+(?:и|and)\\s+', re.IGN…`

### `backend/llm/vacancy.py`

- `logger` = `logging.getLogger(__name__)`
- `MAX_PARSE_TOKENS` = `1200`
- `ROOMIER_PARSE_TOKENS` = `2400`
- `_GRADE_VALUES` = `'"' + ' | '.join(GRADES) + ' | null"'`
- `_FORMAT_VALUES` = `'"' + ' | '.join(WORK_FORMATS) + ' | null"'`
- `PARSE_VACANCY_PROMPT` = `'Ты разбираешь текст объявления о вакансии и изв…`
- `_DOMAIN` = `'(?:www\\.)?[a-zA-Z0-9-]+\\.[a-zA-Z]{2,}'`
- `_TRAILING_URL_RE` = `re.compile(f'\\s*(https?://[^\\s)]+|{_DOMAIN}(?:…`
- `_CONTACT_ADDRESS_RE` = `re.compile(f'\n      {EMAIL_PATTERN}            …`
- `_LABELLED_ADDRESS_RE` = `re.compile('\\(([^()\\s]+)\\)\\s*$')`
- `_DESCRIPTION_MAX_CHARS` = `1500`

### `backend/log_buffer.py`

- `LEVEL_LIMITS` = `словарь из 4`
- `_handler` = `LogBufferHandler()`

### `backend/log_file.py`

- `class LogFileHandler(RotatingFileHandler)`
  - `_complained` = `False`

### `backend/log_secrets.py`

- `_SECRET_PATTERNS: tuple[re.Pattern[str], ...]` = `набор из 7`
- `_REDACTED` = `'***'`
- `_KNOWN_SECRETS: frozenset[str]` = `frozenset()`

### `backend/models/application.py`

- `class Application(IdMixin, Base)`
  - `__tablename__` = `'application'`
  - `__table_args__` = `набор из 1`
  - `vacancy_id: Mapped[int]` = `mapped_column(ForeignKey('vacancy.id'))`
  - `aggregator_id: Mapped[int | None]` = `mapped_column(ForeignKey('aggregator.id'))`
  - `via: Mapped[ApplicationVia]` = `mapped_column(enum_column(ApplicationVia, 'appli…`
  - `target: Mapped[str]`
  - `letter: Mapped[str | None]`
  - `sent_at: Mapped[datetime]` = `mapped_column(DateTime(timezone=True))`
  - `chat_anchor: Mapped[str | None]`
- `class Screening(IdMixin, CreatedAtMixin, Base)`
  - `__tablename__` = `'screening'`
  - `__table_args__` = `набор из 1`
  - `application_id: Mapped[int]` = `mapped_column(ForeignKey('application.id'))`
  - `from_us: Mapped[bool]`
  - `text: Mapped[str]`
  - `position: Mapped[int]`

### `backend/models/base.py`

- `class IdMixin`
  - `id: Mapped[int]` = `mapped_column(primary_key=True, sort_order=-100)`
- `class CreatedAtMixin`
  - `created_at: Mapped[datetime]` = `mapped_column(DateTime(timezone=True), server_de…`
- `class UpdatedAtMixin`
  - `updated_at: Mapped[datetime]` = `mapped_column(DateTime(timezone=True), server_de…`

### `backend/models/contacts.py`

- `class TelegramChannel(IdMixin, Base)`
  - `__tablename__` = `'telegram_channel'`
  - `username: Mapped[str | None]`
  - `title: Mapped[str | None]`
  - `is_active: Mapped[bool]` = `mapped_column(server_default=expression.true())`
  - `last_processed_msg_id: Mapped[int | None]` = `mapped_column(BigInteger)`
  - `avatar: Mapped[bytes | None]` = `mapped_column(LargeBinary)`
- `class Aggregator(IdMixin, Base)`
  - `__tablename__` = `'aggregator'`
  - `__table_args__` = `набор из 1`
  - `name: Mapped[str]`
  - `host: Mapped[str | None]`
  - `is_active: Mapped[bool]` = `mapped_column(server_default=expression.false())`
  - `is_logged_in: Mapped[bool]` = `mapped_column(server_default=expression.false())`
  - `last_run_at: Mapped[datetime | None]` = `mapped_column(DateTime(timezone=True))`
  - `avatar: Mapped[bytes | None]` = `mapped_column(LargeBinary)`
- `class HR(IdMixin, Base)`
  - `__tablename__` = `'hr'`
  - `__table_args__` = `набор из 1`
  - `name: Mapped[str | None]`
  - `telegram_username: Mapped[str | None]`
  - `telegram_user_id: Mapped[int | None]` = `mapped_column(BigInteger)`
  - `notes: Mapped[str | None]`
  - `avatar: Mapped[bytes | None]` = `mapped_column(LargeBinary)`
- `class Company(IdMixin, Base)`
  - `__tablename__` = `'company'`
  - `name: Mapped[str]` = `mapped_column(unique=True)`
  - `aliases: Mapped[list[str]]` = `mapped_column(JSON, server_default=text("'[]'"))`
  - `website: Mapped[str | None]`
  - `notes: Mapped[str | None]`
  - `avatar: Mapped[bytes | None]` = `mapped_column(LargeBinary)`

### `backend/models/enums.py`

- `class BotMode(enum.Enum)`
  - `OFF` = `'Off'`
  - `DM_ONLY` = `'DM Only'`
  - `FULL` = `'Full'`
- `class VacancyStatus(enum.Enum)`
  - `NEW` = `'New'`
  - `APPLIED` = `'Applied'`
  - `ANSWERED` = `'Answered'`
  - `TEST` = `'Test'`
  - `INVITATION` = `'Invitation'`
  - `IN_PROGRESS` = `'In Progress'`
  - `DECLINE` = `'Decline'`
  - `GHOSTING` = `'Ghosting'`
  - `SCAM` = `'Scam'`
  - `NOT_FIT` = `'Not Fit'`
  - `OFFER` = `'Offer'`
- `class StatusHistorySource(enum.Enum)`
  - `SYSTEM` = `'system'`
  - `USER` = `'user'`
- `class LlmConfigKind(enum.Enum)`
  - `CHAT` = `'chat'`
  - `EMBED` = `'embed'`
- `class ContactAddedBy(enum.Enum)`
  - `PARSE` = `'parse'`
  - `AGENT` = `'agent'`
  - `USER` = `'user'`
- `class ApplicationVia(enum.Enum)`
  - `TELEGRAM` = `'telegram'`
  - `AGGREGATOR` = `'aggregator'`
  - `FORM` = `'form'`
  - `EMAIL` = `'email'`
- `class SalaryPeriod(enum.Enum)`
  - `HOUR` = `'hour'`
  - `MONTH` = `'month'`
  - `YEAR` = `'year'`
- `class Gender(enum.Enum)`
  - `MALE` = `'male'`
  - `FEMALE` = `'female'`

### `backend/models/message.py`

- `class Message(IdMixin, Base)`
  - `__tablename__` = `'message'`
  - `__table_args__` = `набор из 2`
  - `is_incoming: Mapped[bool]` = `mapped_column(server_default=expression.false())`
  - `hr_id: Mapped[int | None]` = `mapped_column(ForeignKey('hr.id'))`
  - `vacancy_id: Mapped[int | None]` = `mapped_column(ForeignKey('vacancy.id'))`
  - `text: Mapped[str]`
  - `tg_message_id: Mapped[int | None]` = `mapped_column(BigInteger)`
  - `sent_at: Mapped[datetime]` = `mapped_column(DateTime(timezone=True), server_de…`
  - `read_at: Mapped[datetime | None]` = `mapped_column(DateTime(timezone=True))`
  - `is_edited: Mapped[bool]` = `mapped_column(server_default=expression.false())`
  - `is_deleted: Mapped[bool]` = `mapped_column(server_default=expression.false())`
  - `media_kind: Mapped[str | None]`
  - `media_path: Mapped[str | None]`
  - `media_name: Mapped[str | None]`

### `backend/models/profile.py`

- `profile_experience_skills` = `Table('profile_experience_skills', Base.metadata…`
- `profile_project_skills` = `Table('profile_project_skills', Base.metadata, C…`
- `STACK_LINKS` = `набор из 2`
- `class Profile(IdMixin, UpdatedAtMixin, Base)`
  - `__tablename__` = `'profile'`
  - `first_name: Mapped[str]`
  - `last_name: Mapped[str]`
  - `title: Mapped[str]`
  - `email: Mapped[str]`
  - `phone: Mapped[str | None]`
  - `location: Mapped[str | None]`
  - `telegram_username: Mapped[str | None]`
  - `github_url: Mapped[str | None]`
  - `education: Mapped[str | None]`
  - `work_format: Mapped[list[str]]` = `mapped_column(JSON, server_default=text("'[]'"))`
  - `grades: Mapped[list[str]]` = `mapped_column(JSON, server_default=text("'[]'"))`
  - `free_preferences: Mapped[str | None]`
  - `expected_salary: Mapped[int | None]`
  - `expected_salary_currency: Mapped[str | None]`
  - `expected_salary_period: Mapped[SalaryPeriod | None]` = `mapped_column(enum_column(SalaryPeriod, 'salary_…`
  - `first_name_latin: Mapped[str | None]`
  - `last_name_latin: Mapped[str | None]`
  - `gender: Mapped[Gender | None]` = `mapped_column(enum_column(Gender, 'gender'))`
- `class ProfileLanguage(IdMixin, Base)`
  - `__tablename__` = `'profile_language'`
  - `__table_args__` = `набор из 1`
  - `profile_id: Mapped[int]` = `mapped_column(ForeignKey('profile.id'))`
  - `language: Mapped[str]`
  - `level: Mapped[str]`
- `class ProfileSkill(IdMixin, Base)`
  - `__tablename__` = `'profile_skills'`
  - `profile_id: Mapped[int]` = `mapped_column(ForeignKey('profile.id'))`
  - `category: Mapped[str]`
  - `name: Mapped[str]`
  - `level: Mapped[int]`
  - `aliases: Mapped[list[str]]` = `mapped_column(JSON, server_default=text("'[]'"))`
- `class ProfileExperience(IdMixin, Base)`
  - `__tablename__` = `'profile_experience'`
  - `profile_id: Mapped[int]` = `mapped_column(ForeignKey('profile.id'))`
  - `company: Mapped[str]`
  - `company_url: Mapped[str | None]`
  - `role: Mapped[str]`
  - `start_date: Mapped[date]`
  - `end_date: Mapped[date | None]`
  - `achievements: Mapped[list[str]]` = `mapped_column(JSON, server_default=text("'[]'"))`
  - `responsibilities: Mapped[list[str]]` = `mapped_column(JSON, server_default=text("'[]'"))`
  - `skills: Mapped[list['ProfileSkill']]` = `relationship(secondary=profile_experience_skills…`
- `class ProfileProject(IdMixin, Base)`
  - `__tablename__` = `'profile_project'`
  - `profile_id: Mapped[int]` = `mapped_column(ForeignKey('profile.id'))`
  - `name: Mapped[str]`
  - `url: Mapped[str | None]`
  - `about: Mapped[list[str]]` = `mapped_column(JSON, server_default=text("'[]'"))`
  - `skills: Mapped[list['ProfileSkill']]` = `relationship(secondary=profile_project_skills)`

### `backend/models/settings.py`

- `class BotState(IdMixin, Base)`
  - `__tablename__` = `'bot_state'`
  - `__table_args__` = `набор из 1`
  - `mode: Mapped[BotMode]` = `mapped_column(enum_column(BotMode, 'bot_mode'), …`
- `KEYWORD_KIND` = `'keyword'`
- `HR_KIND` = `'hr'`
- `COMPANY_KIND` = `'company'`
- `CHANNEL_KIND` = `'channel'`
- `AGGREGATOR_KIND` = `'aggregator'`
- `BLACKLIST_KINDS: tuple[str, ...]` = `набор из 5`
- `class Blacklist(IdMixin, CreatedAtMixin, Base)`
  - `__tablename__` = `'blacklist'`
  - `kind: Mapped[str]`
  - `value: Mapped[str]`
  - `reason: Mapped[str | None]`
  - `active: Mapped[bool]` = `mapped_column(server_default=expression.true())`
- `class TgAccount(IdMixin, UpdatedAtMixin, Base)`
  - `__tablename__` = `'tg_account'`
  - `__table_args__` = `набор из 1`
  - `api_id: Mapped[int | None]`
  - `api_hash_encrypted: Mapped[str | None]`
  - `phone: Mapped[str | None]`
  - `password_encrypted: Mapped[str | None]`
  - `session_blob_encrypted: Mapped[bytes | None]` = `mapped_column(LargeBinary)`
- `class MailAccount(IdMixin, UpdatedAtMixin, Base)`
  - `__tablename__` = `'mail_account'`
  - `__table_args__` = `набор из 1`
  - `address: Mapped[str | None]`
  - `smtp_host: Mapped[str | None]`
  - `smtp_port: Mapped[int | None]`
  - `password_encrypted: Mapped[str | None]`
- `class LlmConfig(IdMixin, UpdatedAtMixin, Base)`
  - `__tablename__` = `'llm_config'`
  - `__table_args__` = `набор из 1`
  - `kind: Mapped[LlmConfigKind]` = `mapped_column(enum_column(LlmConfigKind, 'llm_co…`
  - `base_url: Mapped[str | None]`
  - `api_key_encrypted: Mapped[str | None]`
  - `model: Mapped[str | None]`
- `class AppSetting(UpdatedAtMixin, Base)`
  - `__tablename__` = `'app_settings'`
  - `key: Mapped[str]` = `mapped_column(primary_key=True)`
  - `value: Mapped[str | None]`

### `backend/models/vacancy.py`

- `class Vacancy(IdMixin, CreatedAtMixin, Base)`
  - `__tablename__` = `'vacancy'`
  - `__table_args__` = `набор из 4`
  - `hr_id: Mapped[int | None]` = `mapped_column(ForeignKey('hr.id'))`
  - `company_id: Mapped[int | None]` = `mapped_column(ForeignKey('company.id'))`
  - `source_channel_id: Mapped[int | None]` = `mapped_column(ForeignKey('telegram_channel.id'))`
  - `source_msg_id: Mapped[int | None]` = `mapped_column(BigInteger)`
  - `source_aggregator_id: Mapped[int | None]` = `mapped_column(ForeignKey('aggregator.id'))`
  - `source_key: Mapped[str | None]`
  - `raw_text: Mapped[str | None]`
  - `embedding: Mapped[list[float] | None]` = `mapped_column(JSON)`
  - `title: Mapped[str | None]`
  - `description: Mapped[str | None]`
  - `company_name: Mapped[str | None]`
  - `hr_contact: Mapped[str | None]`
  - `stack: Mapped[list[str] | None]` = `mapped_column(JSON)`
  - `grade: Mapped[str | None]`
  - `salary: Mapped[str | None]`
  - `salary_min: Mapped[int | None]`
  - `salary_max: Mapped[int | None]`
  - `salary_currency: Mapped[str | None]`
  - `remote: Mapped[str | None]`
  - `location: Mapped[str | None]`
  - `score: Mapped[int | None]`
  - `skip_reason: Mapped[str | None]`
  - `source_url: Mapped[str | None]`
  - `status: Mapped[VacancyStatus]` = `mapped_column(enum_column(VacancyStatus, 'vacanc…`
  - `is_parsed: Mapped[bool]` = `mapped_column(server_default=expression.false())`
  - `notes: Mapped[str | None]`
  - `posted_at: Mapped[datetime | None]` = `mapped_column(DateTime(timezone=True))`
  - `hr: Mapped[HR | None]` = `relationship()`
  - `company: Mapped[Company | None]` = `relationship()`
  - `channel: Mapped[TelegramChannel | None]` = `relationship()`
  - `aggregator: Mapped[Aggregator | None]` = `relationship()`
- `class VacancyEvent(IdMixin, CreatedAtMixin, Base)`
  - `__tablename__` = `'vacancy_event'`
  - `__table_args__` = `набор из 1`
  - `vacancy_id: Mapped[int]` = `mapped_column(ForeignKey('vacancy.id'))`
  - `kind: Mapped[str]`
  - `payload: Mapped[dict | None]` = `mapped_column(JSON)`
- `class TrashEvent(IdMixin, CreatedAtMixin, Base)`
  - `__tablename__` = `'trash_event'`
  - `__table_args__` = `набор из 2`
  - `source_channel_id: Mapped[int | None]` = `mapped_column(ForeignKey('telegram_channel.id', …`
  - `source_msg_id: Mapped[int | None]` = `mapped_column(BigInteger)`
  - `source_aggregator_id: Mapped[int | None]` = `mapped_column(ForeignKey('aggregator.id'))`
  - `source_key: Mapped[str | None]`
  - `reason: Mapped[str | None]`
- `class VacancyContact(IdMixin, Base)`
  - `__tablename__` = `'vacancy_contact'`
  - `__table_args__` = `набор из 2`
  - `vacancy_id: Mapped[int]` = `mapped_column(ForeignKey('vacancy.id'))`
  - `value: Mapped[str]`
  - `match_key: Mapped[str]`
  - `added_by: Mapped[ContactAddedBy]` = `mapped_column(enum_column(ContactAddedBy, 'conta…`
- `class VacancyStatusHistory(IdMixin, Base)`
  - `__tablename__` = `'vacancy_status_history'`
  - `__table_args__` = `набор из 2`
  - `vacancy_id: Mapped[int]` = `mapped_column(ForeignKey('vacancy.id'))`
  - `message_id: Mapped[int | None]` = `mapped_column(ForeignKey('message.id', ondelete=…`
  - `previous_status: Mapped[VacancyStatus | None]` = `mapped_column(enum_column(VacancyStatus, 'vacanc…`
  - `status: Mapped[VacancyStatus]` = `mapped_column(enum_column(VacancyStatus, 'vacanc…`
  - `explanation: Mapped[str | None]` = `mapped_column(String)`
  - `applied: Mapped[bool]` = `mapped_column(server_default=expression.true())`
  - `source: Mapped[StatusHistorySource]` = `mapped_column(enum_column(StatusHistorySource, '…`
  - `changed_at: Mapped[datetime]` = `mapped_column(DateTime(timezone=True), server_de…`

### `backend/notify.py`

- `logger` = `logging.getLogger(__name__)`

### `backend/payloads.py`

- `DIRECT_PARSED_FIELDS` = `набор из 8`
- `FitVerdict` = `Literal['fit', 'reject', 'trash']`
- `class ChannelPost`
  - `channel_id: int | None`
  - `channel_username: str`
  - `msg: Any`
  - `text: str`
- `class OutgoingMessage`
  - `hr_id: int`
  - `text: str`
  - `tg_message_id: int`
  - `sent_at: Any`
  - `vacancy_id: int | None` = `None`
  - `media_kind: str | None` = `None`
  - `media_path: str | None` = `None`
  - `media_name: str | None` = `None`
- `class IncomingMessage`
  - `hr_id: int`
  - `vacancy_id: int | None`
  - `text: str`
  - `tg_message_id: int`
  - `received_at: Any`
  - `media_kind: str | None` = `None`
  - `media_path: str | None` = `None`
  - `media_name: str | None` = `None`
- `class PendingReply`
  - `vacancy_id: int`
  - `message_id: int`
  - `tg_message_id: int`
  - `text: str`
- `REQUIRED_PROFILE_FIELDS: tuple[str, ...]` = `набор из 4`
- `class ParsedCvProfile`
  - `first_name: str`
  - `last_name: str`
  - `title: str`
  - `email: str`
  - `phone: str | None`
  - `location: str | None`
  - `telegram_username: str | None`
  - `github_url: str | None`
  - `education: str | None`
  - `work_format: list[str]`
  - `grades: list[str]`
  - `free_preferences: str | None`
  - `expected_salary: int | None`
  - `expected_salary_currency: str | None`
  - `expected_salary_period: SalaryPeriod | None`
  - `first_name_latin: str | None`
  - `last_name_latin: str | None`
  - `gender: Gender | None`
- `class ParsedCvLanguage`
  - `language: str`
  - `level: str`
- `class ParsedCvSkill`
  - `category: str`
  - `name: str`
  - `level: int`
  - `aliases: list[str]`
- `class ParsedCvExperience`
  - `company: str`
  - `company_url: str | None`
  - `role: str`
  - `start_date: date`
  - `end_date: date | None`
  - `achievements: list[str]`
  - `responsibilities: list[str]`
  - `stack: list[str]`
- `class ParsedCvProject`
  - `name: str`
  - `url: str | None`
  - `about: list[str]`
  - `stack: list[str]`
- `class ParsedCv`
  - `profile: ParsedCvProfile`
  - `languages: list[ParsedCvLanguage]`
  - `skills: list[ParsedCvSkill]`
  - `experience: list[ParsedCvExperience]`
  - `projects: list[ParsedCvProject]`
- `class Classification`
  - `status: VacancyStatus`
  - `explanation: str | None`
- `class ParsedVacancy`
  - `title: str`
  - `description: str | None`
  - `company_name: str | None`
  - `company_website: str | None`
  - `hr_contact: str | None`
  - `other_contacts: list[str]`
  - `stack_required: list[str]`
  - `stack_preferred: list[str]`
  - `grade: str | None`
  - `salary: str | None`
  - `remote: str | None`
  - `location: str | None`
- `class PostGenre`
  - `is_vacancy: bool`
  - `reason: str`
- `class FitValidation`
  - `verdict: FitVerdict`
  - `reason: str | None`
- `class VacancyDetail`
  - `vacancy: Vacancy`
  - `history: list[VacancyStatusHistory]`
  - `events: list[VacancyEvent]`
  - `contacts: list[VacancyContact]`
  - `has_screening: bool`
- `class HrWithCount`
  - `hr: HR`
  - `vacancy_count: int`
  - `last_company_name: str | None`
  - `unread_count: int` = `0`
  - `is_blacklisted: bool` = `False`
- `class HrDetail`
  - `hr: HR`
  - `last_company_id: int | None`
  - `last_company_name: str | None`
  - `unread_count: int`
  - `blacklist_value: str | None` = `None`
- `class CompanyDetail`
  - `company: Company`
  - `blacklist_value: str | None` = `None`
- `class CompanyWithCount`
  - `company: Company`
  - `vacancy_count: int`
  - `is_blacklisted: bool` = `False`
- `class ChannelWithCount`
  - `channel: TelegramChannel`
  - `vacancy_count: int`
  - `is_blacklisted: bool` = `False`
- `class SourceStats`
  - `status_counts: dict[str, int]`
  - `total: int`
  - `vacancies_per_day: float`
  - `fit_percent: int | None`
  - `apply_percent: int | None`
  - `response_percent: int | None`
- `class ChannelDetail`
  - `channel: TelegramChannel`
  - `stats: SourceStats`
  - `blacklist_value: str | None` = `None`
- `class VacancyFilter`
  - `sort: str` = `'newest'`
  - `search: str | None` = `None`
  - `statuses: list[str] | None` = `None`
  - `channels: list[str] | None` = `None`
  - `companies: list[str] | None` = `None`
  - `score_min: int | None` = `None`
  - `score_max: int | None` = `None`
  - `salary_min: float | None` = `None`
  - `salary_max: float | None` = `None`
  - `grade: str | None` = `None`
  - `remote: str | None` = `None`
  - `hr_contact: str | None` = `None`
  - `date_from: datetime | None` = `None`
  - `date_to: datetime | None` = `None`
  - `limit: int | None` = `None`
  - `offset: int` = `0`

### `backend/provider_config.py`

- `MODEL_FILE_SUFFIX` = `'.gguf'`
- `CLAUDE_HOST` = `'api.anthropic.com'`
- `CLAUDE_CODE_ADDRESS` = `'claude-code'`
- `class LlmProviderConfig`
  - `base_url: str`
  - `api_key: str` = `field(repr=False)`
  - `model: str`

### `backend/repository/agent_profile.py`

- `_GENDER` = `словарь из 2`
- `_PERIOD` = `словарь из 3`

### `backend/repository/aggregators.py`

- `WEB_SEARCH_NAME` = `'Поиск по сети'`
- `NOT_A_SITE` = `'Адрес не похож на сайт'`
- `_LISTED_ORDER` = `набор из 2`
- `AGGREGATOR_BLACKLIST` = `BlacklistMark(AGGREGATOR_KIND, aggregator_blackl…`
- `aggregator_blacklist_value` = `AGGREGATOR_BLACKLIST.value`

### `backend/repository/app_settings.py`

- `CV_PATH_KEY` = `'cv_path'`

### `backend/repository/applications.py`

- `_EXPLANATION` = `словарь из 4`
- `class ApplicationEntry`
  - `vacancy_id: int`
  - `aggregator_id: int | None`
  - `via: ApplicationVia`
  - `target: str`
  - `letter: str | None`
  - `letter_by: str | None`
  - `screening: list[tuple[bool, str]]`
  - `simulated: bool`
- `class ScreenedApplication`
  - `target: str`
  - `lines: list[tuple[bool, str]]`

### `backend/repository/blacklist.py`

- `logger` = `logging.getLogger(__name__)`
- `BlacklistOutcome` = `Literal['created', 'reactivated', 'already_activ…`
- `_SWITCH_OFF_MARKED` = `словарь из 2`
- `_BLACKLIST_FIELD_UNSET` = `object()`

### `backend/repository/blacklist_marks.py`

- `_ACCOUNT_MARK_PREFIX` = `'user_id:'`
- `class BlacklistMark`
  - `kind: str`
  - `candidates: Callable[[Any], list[str]]`

### `backend/repository/bot_mode.py`

- `logger` = `logging.getLogger(__name__)`

### `backend/repository/channels.py`

- `logger` = `logging.getLogger(__name__)`
- `CHANNEL_BLACKLIST` = `BlacklistMark(CHANNEL_KIND, channel_blacklist_ca…`

### `backend/repository/companies_card.py`

- `logger` = `logging.getLogger(__name__)`
- `COMPANY_BLACKLIST` = `BlacklistMark(COMPANY_KIND, company_blacklist_ca…`
- `class _AbsorbedCompany`
  - `name: str`
  - `aliases: list`
  - `website: str | None`
  - `notes: str | None`

### `backend/repository/companies_keys.py`

- `_CYR_TO_LAT` = `словарь из 33`
- `_LEGAL_FORMS` = `frozenset({'pao', 'oao', 'zao', 'ooo', 'jsc', 'l…`
- `_HEAD_LEGAL_FORMS` = `_LEGAL_FORMS | {'ao'}`
- `_TAIL_LEGAL_FORMS` = `_LEGAL_FORMS | {'ao', 'sa', 'ag', 'nv', 'bv'}`
- `_QUOTE_CHARS` = `set('«»"\'`“”„‚‘’')`

### `backend/repository/companies_matching.py`

- `logger` = `logging.getLogger(__name__)`
- `class _Parsed`
  - `raw_name: str`
  - `norm: str`
  - `host: str`
  - `website: str | None`

### `backend/repository/hr_card.py`

- `logger` = `logging.getLogger(__name__)`
- `LAST_VACANCY_ORDER` = `набор из 2`
- `HR_BLACKLIST` = `BlacklistMark(HR_KIND, hr_blacklist_candidates)`
- `hr_blacklist_value` = `HR_BLACKLIST.value`
- `class _AbsorbedHr`
  - `telegram_user_id: int | None`
  - `telegram_username: str | None`
  - `name: str | None`
  - `notes: str | None`

### `backend/repository/hr_identify.py`

- `logger` = `logging.getLogger(__name__)`
- `HAS_TELEGRAM_IDENTITY` = `or_(HR.telegram_user_id.is_not(None), HR.telegra…`
- `OUR_LETTER_ABOUT_A_VACANCY` = `and_(~Message.is_incoming, Message.vacancy_id.is…`

### `backend/repository/mail_account.py`

- `class MailSettings`
  - `address: str`
  - `password: str | None` = `field(repr=False)`
  - `host: str | None`
  - `port: int | None`

### `backend/repository/messages.py`

- `UNREAD_INCOMING` = `набор из 3`

### `backend/repository/profile.py`

- `logger` = `logging.getLogger(__name__)`

### `backend/repository/profile_cv.py`

- `logger` = `logging.getLogger(__name__)`
- `_SALARY` = `набор из 3`
- `_PERSON` = `набор из 3`
- `_KEPT_ACROSS_RESUMES` = `_SALARY + _PERSON`

### `backend/repository/profile_experience.py`

- `EXPERIENCE` = `RecordKind(ProfileExperience, profile_experience…`

### `backend/repository/profile_languages.py`

- `logger` = `logging.getLogger(__name__)`

### `backend/repository/profile_projects.py`

- `PROJECTS` = `RecordKind(ProfileProject, profile_project_skill…`

### `backend/repository/profile_records.py`

- `logger` = `logging.getLogger(__name__)`
- `class RecordKind(NamedTuple)`
  - `model: type`
  - `links: Table`
  - `fields_of: Callable[[dict], dict]`

### `backend/repository/profile_skills.py`

- `logger` = `logging.getLogger(__name__)`

### `backend/repository/source_stats.py`

- `_RATE_WINDOW_DAYS` = `30`

### `backend/repository/stats_pipeline.py`

- `_VACANCY_SOURCE` = `набор из 2`

### `backend/repository/stats_rows.py`

- `SourceKey` = `tuple[int | None, int | None]`

### `backend/repository/vacancies_card.py`

- `logger` = `logging.getLogger(__name__)`
- `VACANCY_NEIGHBOURS` = `набор из 4`
- `class _Link`
  - `column: str`
  - `model: type`
  - `kind: str`
  - `display: Callable[[Any], str | None]`
  - `operation: str`
- `_HR_LINK` = `_Link(column='hr_id', model=HR, kind='linked_hr'…`
- `_COMPANY_LINK` = `_Link(column='company_id', model=Company, kind='…`

### `backend/repository/vacancies_common.py`

- `SOURCE_LINKS` = `словарь из 2`
- `PARSED_ONLY` = `Vacancy.is_parsed.is_(True)`
- `VACANCY_APPEARED_AT` = `func.coalesce(Vacancy.posted_at, Vacancy.created…`

### `backend/repository/vacancies_ghosting.py`

- `logger` = `logging.getLogger(__name__)`

### `backend/repository/vacancies_life.py`

- `logger` = `logging.getLogger(__name__)`

### `backend/repository/vacancies_list.py`

- `logger` = `logging.getLogger(__name__)`
- `_STATUS_BY_CODE` = `{status_code(s): s for s in VacancyStatus}`
- `_STATUS_PRIORITY_ACTIVE_FIRST` = `словарь из 11`
- `_STATUS_PRIORITY_NEW_FIRST` = `словарь из 11`
- `_LIKE_ESCAPE` = `'\\'`
- `_LIKE_SPECIALS` = `набор из 3`

### `backend/repository/vacancies_mini.py`

- `_CHANNEL_VAC_STATUS_RANK: dict[str, int]` = `словарь из 11`

### `backend/repository/vacancies_new.py`

- `logger` = `logging.getLogger(__name__)`
- `HAND_MADE` = `'created_by_hand'`

### `backend/repository/vacancy_status.py`

- `logger` = `logging.getLogger(__name__)`
- `class _Signature`
  - `explanation: str | None` = `None`
  - `message_id: int | None` = `None`
  - `source: StatusHistorySource` = `StatusHistorySource.SYSTEM`
- `class _Move`
  - `allowed: frozenset[VacancyStatus]`
  - `to: VacancyStatus`
- `_APPLIED` = `_Move(APPLY_MOVES_FROM, VacancyStatus.APPLIED)`
- `_UNFIT` = `_Move(frozenset({VacancyStatus.NEW}), VacancySta…`

### `backend/runtime_settings.py`

- `logger` = `logging.getLogger(__name__)`
- `_APP_DEFAULTS: dict[str, str]` = `словарь из 15`
- `LETTER_WRITERS` = `набор из 2`

### `backend/single_instance.py`

- `logger` = `logging.getLogger(__name__)`
- `_held` = `None`
- `_BUSY` = `frozenset({errno.EACCES, errno.EAGAIN, errno.EWO…`

### `backend/telegram_login.py`

- `logger` = `logging.getLogger(__name__)`
- `class LoginStep`
  - `payload: dict | None` = `None`
  - `error: str | None` = `None`

### `backend/telegram_lookup.py`

- `logger` = `logging.getLogger(__name__)`

### `backend/tg_credentials.py`

- `logger` = `logging.getLogger(__name__)`
- `class TgAccountConfig`
  - `api_id: int`
  - `api_hash: str` = `field(repr=False)`
  - `phone: str`
  - `password: str` = `field(repr=False)`
  - `session_string: str | None` = `field(repr=False)`

### `backend/update_download.py`

- `logger` = `logging.getLogger(__name__)`
- `UpdateOutcome` = `Literal['ok', 'no_update', 'broken']`
- `_MB` = `1024 * 1024`

### `backend/updater.py`

- `logger` = `logging.getLogger(__name__)`
- `UPDATE_FLAG` = `'--update'`
- `_ATTEMPTS` = `30`
- `_PAUSE_SEC` = `1.0`
- `_WAIT_MS` = `60000`
- `_SYNCHRONIZE` = `1048576`
- `_DETACHED` = `8 | 512`

### `backend/wipe.py`

- `logger` = `logging.getLogger(__name__)`

## client

### `client/bridge/aggregators.py`

- `_DELETION_REFUSALS` = `словарь из 3`

### `client/bridge/answer.py`

- `logger` = `logging.getLogger(__name__)`
- `BAD_PAYLOAD` = `набор из 4`

### `client/bridge/app_update.py`

- `logger` = `logging.getLogger(__name__)`
- `GITHUB_SILENT` = `'GitHub не ответил — проверьте связь.'`

### `client/bridge/bot_stop.py`

- `logger` = `logging.getLogger(__name__)`
- `STOP_TIMEOUT_S` = `10.0`

### `client/bridge/cards.py`

- `logger` = `logging.getLogger(__name__)`
- `class CardSubject`
  - `picker: PickerSubject`
  - `id_key: str`
  - `missing: str`
  - `domain: str`
  - `page_limit: int | None`
  - `listing: dict`
  - `read_fields: Callable`
  - `update_fields: tuple[str, ...]`
  - `mini_vacancies: Callable`
  - `merge_row: Callable`
  - `delete_row: Callable`
  - `create_row: Callable`
  - `merge_action: str`
  - `delete_action: str`
  - `create_action: str`
  - `news: tuple[str, ...]`

### `client/bridge/companies.py`

- `COMPANY_CARD` = `CardSubject(picker=COMPANY_PICKER, id_key='compa…`

### `client/bridge/cv.py`

- `_RESUME_FILTER` = `file_filter('Резюме', (*READABLE_SUFFIXES, '.doc…`

### `client/bridge/desktop.py`

- `logger` = `logging.getLogger(__name__)`
- `_LINK_SCHEMES` = `frozenset({'http', 'https', 'tg', 'mailto', 'tel…`
- `_OPENABLE_SUFFIXES` = `frozenset({'.bmp', '.gif', '.jpeg', '.jpg', '.pn…`

### `client/bridge/events.py`

- `logger` = `logging.getLogger(__name__)`
- `LIST_CHANGED` = `'vacancies_list_changed'`
- `KEEP_EVENTS` = `500`
- `WAIT_SECONDS` = `25.0`

### `client/bridge/hr.py`

- `HR_CARD` = `CardSubject(picker=HR_PICKER, id_key='hr_id', mi…`

### `client/bridge/hr_chat.py`

- `logger` = `logging.getLogger(__name__)`

### `client/bridge/journal.py`

- `_LOGS_INTERVAL_S` = `1.0`

### `client/bridge/lifespan.py`

- `logger` = `logging.getLogger(__name__)`
- `_LOGIN_CLOSING_WAIT_S` = `3.0`
- `_CLOSING_WAIT_S` = `5.0`

### `client/bridge/llm.py`

- `logger` = `logging.getLogger(__name__)`
- `_MODEL_FILTER` = `file_filter('Модель GGUF', (MODEL_FILE_SUFFIX,))`
- `PROVIDER_KINDS` = `tuple((kind.value for kind in LlmConfigKind))`

### `client/bridge/mark.py`

- `class MarkSubject`
  - `blacklist: BlacklistMark`
  - `model: type`
  - `key: str`
  - `missing: str`
  - `unnamed: str`
- `HR_MARK` = `MarkSubject(blacklist=hr_card.HR_BLACKLIST, mode…`
- `COMPANY_MARK` = `MarkSubject(blacklist=companies_card.COMPANY_BLA…`
- `CHANNEL_MARK` = `MarkSubject(blacklist=channels_repo.CHANNEL_BLAC…`
- `AGGREGATOR_MARK` = `MarkSubject(blacklist=aggregators_repo.AGGREGATO…`

### `client/bridge/page.py`

- `_CEILING` = `200`
- `class Page`
  - `limit: int | None`
  - `offset: int`

### `client/bridge/payload.py`

- `logger` = `logging.getLogger(__name__)`

### `client/bridge/pickers.py`

- `class PickerSubject`
  - `key: str`
  - `rows: Callable`
  - `row_to_dict: Callable`
  - `id_of: Callable`
  - `short_row: Callable`
  - `current: str`
  - `linked_id: Callable`
- `HR_PICKER` = `PickerSubject(key='hrs', rows=hr_list.list_hr_wi…`
- `COMPANY_PICKER` = `PickerSubject(key='companies', rows=companies_li…`

### `client/bridge/refusals.py`

- `NO_BOT` = `'Бот ещё не готов.'`
- `NO_VACANCY` = `'Вакансия не найдена.'`
- `NO_HR` = `'HR не найден.'`
- `NO_COMPANY` = `'Компания не найдена.'`
- `NO_CHANNEL` = `'Канал не найден.'`
- `NO_ENTRY` = `'Запись не найдена.'`
- `BLACKLISTED_STAYS_OFF` = `'В чёрном списке — снимите запись, чтобы включит…`
- `HR_TELEGRAM_TAKEN` = `'Человек с такой учётной записью Telegram уже за…`
- `SEND_BROKE` = `'Telegram не принял письмо. Проверьте связь и за…`
- `SPELLINGS_SHAPE` = `'Написания шлют списком или строкой через запяту…`
- `MERGE_INTO_SELF` = `'Слить карточку саму с собой нельзя.'`
- `NOTHING_TO_UPDATE` = `'Нечего обновлять.'`
- `NAME_REQUIRED` = `'Название обязательно.'`
- `TEXT_REQUIRED` = `'Вставьте текст объявления.'`
- `IDENTITY_REQUIRED` = `'Укажите хотя бы имя или @username.'`
- `COMPANY_EXISTS` = `'Компания «{name}» уже существует.'`
- `CODE_FIRST` = `'Сначала запросите код подтверждения.'`
- `CODE_STEP_FIRST` = `'Сначала пройдите шаг с кодом подтверждения.'`
- `LLM_FIELDS_REQUIRED` = `'Заполните base_url и модель.'`
- `EMBED_ON_CLAUDE` = `'Claude не считает эмбеддинги: выберите для них …`
- `PROFILE_FIRST` = `'Сначала сохраните профайл (CV-таб).'`
- `BUSY_CYCLE` = `'Уже идёт другой цикл, попробуйте позже.'`
- `WIPE_FILES_BUSY` = `'Файлы открыты в другом процессе и не могут быть…`
- `LINK_SCHEME_UNKNOWN` = `'Такие ссылки приложение не открывает.'`
- `ATTACHMENT_MISSING` = `'Вложение не найдено.'`
- `ATTACHMENT_NOT_OPENED` = `'Не удалось открыть вложение.'`
- `LOGS_TOO_OFTEN` = `'Журнал спрашивают не чаще раза в секунду.'`
- `AGENT_STOPS` = `словарь из 2`
- `RUN_REFUSALS` = `словарь из 3 и раскрытых`
- `POLL_REFUSALS` = `словарь из 5 и раскрытых`
- `RERUN_REFUSALS` = `словарь из 6 и раскрытых`
- `PASTED_REFUSALS` = `словарь из 7 и раскрытых`
- `PARSE_CV_REFUSALS` = `словарь из 5`
- `NO_AGGREGATOR` = `'Агрегатор не найден.'`
- `WEB_SEARCH_KEPT` = `'Поиск по сети удалить нельзя'`
- `LOGIN_FIRST` = `'Сначала войдите на сайт'`
- `WEB_SEARCH_UNMARKED` = `'Поиск по сети в чёрный список не заносится'`
- `WAY_UNKNOWN` = `'Этим способом на вакансию не откликнуться.'`
- `AGGREGATOR_REFUSALS` = `словарь из 5 и раскрытых`
- `LOGIN_REFUSALS` = `словарь из 2 и раскрытых`
- `APPLY_VIA_REFUSALS` = `словарь из 6 и раскрытых`
- `APPLY_ALL_REFUSALS` = `словарь из 3 и раскрытых`
- `UPDATE_REFUSALS` = `словарь из 6`

### `client/bridge/runner.py`

- `logger` = `logging.getLogger(__name__)`

### `client/bridge/settings.py`

- `logger` = `logging.getLogger(__name__)`
- `_CONNECT_TRIES` = `15`
- `_CONNECT_STEP_S` = `0.2`
- `APP_KEYS` = `набор из 8`

### `client/bridge/source_page.py`

- `logger` = `logging.getLogger(__name__)`
- `class Source`
  - `key: str`
  - `kind: str`
  - `method: str`
- `CHANNEL` = `Source('channel_id', CHANNEL_KIND, 'channels.vac…`
- `AGGREGATOR` = `Source('aggregator_id', AGGREGATOR_KIND, 'aggreg…`

### `client/bridge/system.py`

- `logger` = `logging.getLogger(__name__)`
- `_MODEL_PROBE_INTERVAL_S` = `60.0`
- `MODEL_KINDS` = `набор из 2`

### `client/bridge/vacancies.py`

- `logger` = `logging.getLogger(__name__)`

### `client/bridge/vacancy_links.py`

- `logger` = `logging.getLogger(__name__)`
- `_CREATING` = `словарь из 2`
- `_PICKING` = `словарь из 2`
- `_LINKING` = `словарь из 2`

### `client/bridge/wipe.py`

- `logger` = `logging.getLogger(__name__)`
- `_LEAVE_AFTER_S` = `1.0`

### `client/raise_window.py`

- `logger` = `logging.getLogger(__name__)`
- `LOOPBACK` = `'127.0.0.1'`
- `CONNECT_TIMEOUT_S` = `1.0`
- `_PORT_FIRST` = `20000`
- `_PORT_COUNT` = `10000`
- `_ACK` = `b'1'`
- `_ASFW_ANY` = `-1`
- `class _RaiseHandler(socketserver.StreamRequestHandler)`
  - `timeout` = `CONNECT_TIMEOUT_S`
- `class _RaiseServer(socketserver.ThreadingTCPServer)`
  - `allow_reuse_address` = `sys.platform != 'win32'`

### `client/serving.py`

- `logger` = `logging.getLogger(__name__)`
- `_NOT_FOUND` = `b'not found'`
- `MEDIA_PREFIX` = `'/media/'`
- `_OWN_TYPES` = `словарь из 7`

### `client/trouble_box.py`

- `logger` = `logging.getLogger(__name__)`
- `_AS_TROUBLE` = `16`

### `client/window.py`

- `logger` = `logging.getLogger(__name__)`
- `CLIENT_DIR` = `Path(__file__).parent`
- `WEB_DIST` = `CLIENT_DIR / 'web' / 'dist'`
- `ICON_FILE` = `CLIENT_DIR / 'icon.ico'`
- `_ENGINE_CLOSING_WAIT_S` = `5.0`
- `_CLAUDE_CODE_CLOSING_WAIT_S` = `5.0`
- `WINDOW_BACKGROUND` = `'#2d2d2f'`

### `client/window_size.py`

- `WIZARD` = `набор из 2`
- `MAIN` = `набор из 2`

## tests

### `tests/adapters/test_app_tied_process.py`

- `pytestmark` = `pytest.mark.skipif(sys.platform != 'win32', reas…`
- `ROOT` = `Path(__file__).resolve().parents[2]`
- `_APP` = `'\nimport os, subprocess, sys\nfrom adapters imp…`
- `_PARENT` = `'\nimport subprocess, sys, time\ngrandchild = su…`

### `tests/adapters/test_browser_sending.py`

- `class _Page`
  - `url` = `'about:blank'`

### `tests/adapters/test_claude.py`

- `LOG` = `logging.getLogger('tests.claude')`
- `SONNET` = `'claude-sonnet-5-5'`

### `tests/adapters/test_claude_code.py`

- `LOG` = `logging.getLogger('tests.claude_code')`
- `SONNET` = `'sonnet'`

### `tests/adapters/test_claude_code_agent.py`

- `RUN` = `AgentRun(system_prompt='РАМКА', task='ЗАДАНИЕ', …`

### `tests/adapters/test_lm_models.py`

- `NATIVE_MODELS` = `набор из 2`

### `tests/adapters/test_smtp_mail.py`

- `class _FakeSmtp`
  - `sent: list` = `набор из 0`
  - `logins: list` = `набор из 0`
  - `events: list` = `набор из 0`

### `tests/backend/fixtures/applying.py`

- `PAGE` = `'https://site.test/vacancy/1'`
- `FORM` = `'https://company.test/apply'`
- `TG` = `Way('telegram', '@hr_name', None)`

### `tests/backend/test_agent_availability.py`

- `CHROME` = `InstalledBrowser('Chrome', 'chrome', None)`

### `tests/backend/test_agent_prompts.py`

- `ROLES` = `набор из 3`
- `SHARED_RULES` = `набор из 4`
- `_METHOD_NAMES` = `словарь из 2`

### `tests/backend/test_agent_sessions.py`

- `PLAN` = `SessionPlan(system_prompt='', task='', tools=[],…`

### `tests/backend/test_agent_tools_browser.py`

- `VACANCY` = `'https://site.test/vacancy/1'`

### `tests/backend/test_agent_tools_seeker.py`

- `pytestmark` = `pytest.mark.usefixtures('one_vector')`
- `PAGE` = `'https://site.test/vacancy/1?from=list'`
- `BARRED_PAGE` = `'https://jobs.barred.test/vacancy/1'`

### `tests/backend/test_applying_email.py`

- `MAIL` = `Way('email', 'hr@company.test', None)`

### `tests/backend/test_bootstrap_schema.py`

- `_ENV_PY` = `'\nfrom alembic import context\nfrom sqlalchemy …`
- `_REVISION_PY` = `'\nrevision = "{revision}"\ndown_revision = {par…`

### `tests/backend/test_domain_apply_order.py`

- `SITE` = `KnownSite(1, 'site.test')`
- `WEB` = `KnownSite(9, None)`

### `tests/backend/test_domain_dedup.py`

- `IDS` = `np.array([10, 20, 30])`
- `MATRIX` = `np.array([[1.0, 0.0], [0.0, 1.0], [0.9, 0.1]], d…`

### `tests/backend/test_domain_transitions.py`

- `TERMINAL` = `набор из 4`
- `LIVE` = `[status for status in VacancyStatus if status no…`

### `tests/backend/test_entry_point_log.py`

- `ROOT` = `Path(__file__).resolve().parents[2]`

### `tests/backend/test_flows_aggregator_name.py`

- `CHAT_MODEL` = `LlmProviderConfig(base_url='http://provider.test…`
- `_DECLARED` = `'<meta property="og:site_name" content="Пример Р…`
- `_ICON` = `b'\x89PNG\r\n\x1a\n-icon-'`

### `tests/backend/test_flows_aggregator_seek.py`

- `pytestmark` = `pytest.mark.usefixtures('one_vector')`
- `PAGE` = `'https://site.test/vacancy/1'`

### `tests/backend/test_flows_ghosting_timer.py`

- `_SILENT_DAYS` = `15`
- `_STILL_WAITING_DAYS` = `13`

### `tests/backend/test_flows_new_vacancy.py`

- `pytestmark` = `pytest.mark.usefixtures('one_vector')`
- `WITH_ARTICLE` = `'Senior QA https://telegra.ph/QA-08-21'`

### `tests/backend/test_llm_cv_response.py`

- `MINIMAL_CV` = `json.dumps({'profile': CV_REQUIRED_PROFILE}, ens…`

### `tests/backend/test_llm_fit_languages.py`

- `_asked` = `partial(asked, validate_language_fit)`
- `_check` = `partial(verdict, validate_language_fit)`

### `tests/backend/test_llm_fit_validation.py`

- `_asked` = `partial(asked, validate_role_fit)`
- `_check` = `partial(verdict, validate_role_fit)`

### `tests/backend/test_migration_apply_trail.py`

- `_BEFORE` = `'a9c3e1f07b42'`
- `_OLD_KINDS` = `набор из 6`

### `tests/backend/test_migration_engine.py`

- `_HOUSE_REVISION` = `'\nrevision = "дом_заведён"\ndown_revision = Non…`
- `_REBUILD_HEAD` = `'\nrevision = "дом_перестроен"\ndown_revision = …`
- `_QUENCHED` = `_REBUILD_HEAD.format(quench='    op.execute("PRA…`
- `_AS_IS` = `_REBUILD_HEAD.format(quench='')`

### `tests/backend/test_repository_channel_detail.py`

- `_FUNNEL_SET` = `[VacancyStatus.NOT_FIT] * 2 + [VacancyStatus.SCA…`

### `tests/backend/test_repository_hr_attribution.py`

- `REPLIED_AT` = `at(90)`

### `tests/backend/test_repository_vacancy_ghosting.py`

- `TIMEOUT` = `14`

### `tests/backend/test_repository_vacancy_mini_lists.py`

- `_HOTTEST_FIRST` = `набор из 11`

### `tests/backend/test_telegram_adapter.py`

- `_ALIEN_PEER` = `9999`

### `tests/backend/test_telegram_time.py`

- `_TS` = `1755500000.0`

### `tests/backend/test_update_download.py`

- `MB` = `1024 * 1024`

### `tests/backend/test_updater.py`

- `REAL_POPEN` = `subprocess.Popen`

### `tests/client/test_bot_contract.py`

- `BRIDGE` = `Path(__file__).resolve().parents[2] / 'client' /…`

### `tests/client/test_bridge_login.py`

- `CREDENTIALS` = `словарь из 3`

### `tests/client/test_bridge_model_speed.py`

- `SAVED_CHAT` = `словарь из 1`

### `tests/client/test_bridge_profile.py`

- `PERSON` = `словарь из 4`

### `tests/client/test_front_vocabulary.py`

- `STATE` = `Path(__file__).resolve().parents[2] / 'client' /…`

### `tests/client/test_page_contract.py`

- `WEB` = `Path(__file__).resolve().parents[2] / 'client' /…`
- `CALLING` = `re.compile('\\b(?:call|ask)\\(\\s*[\'"]([a-z_]+)…`
- `HANDED_OVER` = `re.compile('\\bmethod:\\s*[\'"]([a-z_]+)\\.([a-z…`
- `SOURCES` = `набор из 2`
- `LAYERS` = `набор из 4`

### `tests/client/test_window.py`

- `class StubHub`
  - `engine` = `None`

### `tests/conftest.py`

- `_REAL_APPDATA` = `os.environ.get('APPDATA')`
- `TMP_ROOT` = `Path(tempfile.mkdtemp(prefix='jobbot-tests-'))`
- `MEMORY_KEYRING` = `MemoryKeyring()`
- `INIT_REVISION` = `'e560edf8b958'`
- `_REAL_DATA_DIR` = `Path(_REAL_APPDATA) / APP_NAME if _REAL_APPDATA …`
- `_FALLBACK_DATA_DIR` = `_data_dir_without_appdata()`

### `tests/factories.py`

- `EPOCH` = `datetime(2026, 1, 1, 12, 0)`
- `_PHOTO_HEADS` = `словарь из 4`
- `CV_REQUIRED_PROFILE` = `person_fields()`
- `_MARKED_COMPANIES` = `набор из 3`

### `tests/fakes/agent.py`

- `TODAY` = `date(2026, 10, 9)`

### `tests/fakes/claude.py`

- `MESSAGES` = `набор из 2`
- `MODELS` = `набор из 2`

### `tests/fakes/claude_code.py`

- `CLI` = `'C:\\fake\\claude.exe'`
- `DIES` = `'процесс закрыл вывод'`
- `HANGS` = `'процесс молчит'`

### `tests/fakes/github_release.py`

- `APP` = `b'MZ' + b'\x00' * 2046`
- `NEWER` = `'v99.0.0'`
- `FROM_CONTENT` = `object()`

### `tests/fakes/ingestion.py`

- `class FakeIngestion`
  - `_OWN` = `object()`

### `tests/fakes/keyring.py`

- `class MemoryKeyring(keyring.backend.KeyringBackend)`
  - `priority` = `1`

### `tests/fakes/llm.py`

- `CHAT` = `набор из 2`
- `EMBEDDINGS` = `набор из 2`
- `MODELS` = `набор из 2`

### `tests/fakes/site_home.py`

- `HOME` = `набор из 2`

### `tests/fakes/telegram.py`

- `class FakeTelegramClient`
  - `executor` = `None`

### `tests/fakes/telegram_objects.py`

- `TG_EPOCH` = `EPOCH.replace(tzinfo=timezone.utc).astimezone().…`
- `OUR_USER_ID` = `1`
- `_UNSET` = `object()`

### `tests/fakes/ui_bot.py`

- `class Sent`
  - `id: int`
- `ANSWERS` = `словарь из 16`
- `class UiBot`
  - `is_running_round` = `False`
