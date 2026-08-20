# Карта модулей

Собирается из кода, а не ведётся руками.
Править руками нельзя — правки затрёт следующая сборка.
Число в скобках — сколько строк занимает объявление.

## . — 2 модулей

### `config.py` — 121 строк

Bootstrap config.

Зависит от: `adapters.telegram`, `backend.bot.media`

- `def _user_data_dir() -> Path` (12)
- `def get_data_dir() -> Path` (5)
- `def get_database_url() -> str` (4)
- `def get_lock_path() -> Path` (8)
- `def data_files() -> list[Path]` (19)
- `def _log_files() -> list[Path]` (4)
- `def data_dirs() -> list[Path]` (17)
- `def get_log_path() -> Path` (7)

### `main.py` — 165 строк

Job Bot — single CLI entry point.

Зависит от: `backend`, `backend.crypto`, `backend.log_file`, `backend.single_instance`, `client.raise_window`, `client.window`, `config`

- `def _use_utf8_stdout() -> None` (18)
- `def _log_handlers() -> list[logging.Handler]` (27)
- `def _log_uncaught(exc_type, exc, tb) -> None` (13)
- `def _log_uncaught_in_thread(args) -> None` (10)
- `def main() -> int` (40)

## adapters — 7 модулей

### `adapters/db.py` — 105 строк

Соединение с базой: как его завести и как спросить, живо ли оно.

Зависит от: —

- `def _dump_json(value: object) -> str` (9)
- `def make_engine(database_url: str) -> AsyncEngine` (28)
  - `def _prepare_connection(dbapi_conn, _record)` (10)
- `def _lower(value: object) -> object` (14)
- `def _trim(value: object) -> object` (14)
- `async def ping(session) -> bool` (16)

### `adapters/lm_chat.py` — 153 строк

Обращение к чат-модели провайдера и разбор её ответа.

Зависит от: —

- `class ChatRequest` (16)
- `class ChatAnswer` (10)
- `async def _post_chat(client: httpx.AsyncClient, model: str, request: ChatRequest, log: logging.Logger)` (35)
- `def _warn_if_truncated(finish_reason, purpose: str, log: logging.Logger) -> None` (17)
- `def _answer_or_empty(content, finish_reason, purpose: str, log: logging.Logger) -> ChatAnswer` (21)
- `async def chat(client: httpx.AsyncClient, model: str, request: ChatRequest, log: logging.Logger) -> ChatAnswer` (30)

### `adapters/lm_embed.py` — 25 строк

Числовой отпечаток текста у модели встраиваний.

Зависит от: —

- `async def embed(client: httpx.AsyncClient, model: str, text: str) -> list[float]` (16)

### `adapters/lm_models.py` — 148 строк

Перечень моделей у провайдера и проверка, что нужная отвечает.

Зависит от: —

- `def _ping_request(model: str, kind: str) -> tuple[str, dict]` (14)
- `async def check_model(client: httpx.AsyncClient, model: str, kind: str) -> tuple[bool, str]` (35)
- `def _looks_like_embed(name: str) -> bool` (9)
- `async def _loaded_models(client: httpx.AsyncClient, kind: str) -> list[str] | None` (37)
- `async def list_models(client: httpx.AsyncClient, *, kind: str | None=None) -> list[str]` (22)

### `adapters/lm_studio.py` — 32 строк

Соединение с OpenAI-совместимым провайдером моделей.

Зависит от: `backend.runtime_settings`

- `def make_client(config: LlmProviderConfig) -> httpx.AsyncClient` (9)

### `adapters/telegram.py` — 101 строк

Сборка клиента Telegram и отправка письма его руками.

Зависит от: `backend.runtime_settings`, `config`

- `def make_client(tg: TgAccountConfig) -> Client` (30)
- `async def send_dm(client: Client, user: str | int, text: str, attachment: str | Path | None=None) -> int | None` (24)

### `adapters/teletype.py` — 108 строк

Статья teletype: сходить по адресу и достать из страницы её текст.

Зависит от: —

- `def make_client() -> httpx.AsyncClient` (7)
- `def _article_text(html: str) -> str | None` (20)
- `async def fetch_article(client: httpx.AsyncClient, url: str) -> str | None` (24)

## alembic — 3 модулей

### `alembic/env.py` — 77 строк

Обвязка alembic: откуда берётся база и чьим движком идут миграции.

Зависит от: `adapters.db`, `alembic`, `backend.models`, `config`

- `def run_migrations_offline() -> None` (10)
- `def do_run_migrations(connection: Connection) -> None` (4)
- `async def run_async_migrations() -> None` (14)
- `def run_migrations_online() -> None` (2)

### `alembic/versions/8ba64b863cb1_init.py` — 272 строк

init

Зависит от: `alembic`

- `def upgrade() -> None` (221)
- `def downgrade() -> None` (28)

### `alembic/versions/aa4e0de05368_seed_initial_data.py` — 496 строк ⚠ подошёл к 300

seed initial data

Зависит от: `alembic`, `backend.crypto`

- `def _seed_profile() -> None` (60)
- `def _seed_channels() -> None` (11)
- `def _seed_secrets() -> None` (61)
- `def _seed_settings() -> None` (27)
- `def upgrade() -> None` (11)
- `def downgrade() -> None` (11)

## backend — 114 модулей

### `backend/bootstrap.py` — 41 строк

First-run bootstrap: ensure DB schema exists.

Зависит от: `alembic`

- `def alembic_config() -> Config` (10)
- `def ensure_schema() -> None` (9)

### `backend/bot/can_send.py` — 58 строк

Один ответ на вопрос «можно ли писать этому HR» — окну и конвейеру.

Зависит от: `adapters`, `backend.domain.telegram_identity`, `backend.models`, `backend.repository.hr_card`

- `class SendPermission` (8)
- `async def can_send_to_hr(bot, hr) -> SendPermission` (23)

### `backend/bot/channels.py` — 150 строк

Правка каналов из окна: заведение, удаление, чтение по требованию.

Зависит от: `backend.bot`, `backend.flows`, `backend.repository.channels`, `backend.telegram_lookup`

- `async def poll_channel_now(bot, channel_id: int) -> ChannelPollOutcome` (29)
- `async def delete_channel(bot, channel_id: int) -> int | None` (7)
- `async def _ask_telegram_about(bot, username: str)` (26)
- `async def add_channel(bot, username: str) -> tuple[int | None, ChannelAddOutcome]` (38)
- `async def force_poll_once(bot) -> slot.CycleOutcome` (11)

### `backend/bot/chat.py` — 221 строк

Переписка с HR из окна: отправка текста, файла и отметка о прочтении.

Зависит от: `backend.bot`, `backend.models`, `backend.payloads`, `backend.repository.messages`, `backend.telegram_time`

- `async def mark_hr_chat_read(bot, hr_id: int) -> int` (25)
- `async def _tell_telegram_it_is_read(bot, hr: HR, hr_id: int) -> None` (20)
- `async def _target_or_refuse(bot, hr_id: int) -> int | str` (18)
- `async def _persist_outgoing(bot, outgoing: OutgoingMessage) -> Message` (10)
- `async def send_to_hr_chat(bot, hr_id: int, text: str) -> Message` (32)
- `def _checked_kind(src: Path, file_path: str) -> bool` (28)
- `async def send_to_hr_media(bot, hr_id: int, file_path: str) -> Message` (38)

### `backend/bot/client.py` — 327 строк ⚠ подошёл к 300

Сборка бота: его состояние, соединения и поверхность, которой пользуется окно.

Зависит от: `adapters`, `backend.bot`, `backend.flows.pipeline`, `backend.models`, `backend.runtime_settings`

- `def _open_connections(bot, runtime_settings: RuntimeSettings) -> None` (18)
- `def _subscribe_to_updates(bot) -> None` (33)
- `def _declare_loop_controls(bot) -> None` (15)
- `def _declare_ui_hooks(bot) -> None` (37)
- `def _forward_pipeline_hooks(bot) -> None` (17)
- `class Bot` (161)
  - `def is_ready(self) -> bool` (7)
  - `def is_connected(self) -> bool` (13)
  - `def kick(self) -> None` (8)
  - `def request_stop(self) -> None` (8)
  - `async def poll_channel_now(self, channel_id) -> channels.ChannelPollOutcome` (4)
  - `async def delete_channel(self, channel_id) -> int | None` (2)
  - `async def add_channel(self, username) -> tuple[int | None, channels.ChannelAddOutcome]` (4)
  - `def cancel_current_poll(self) -> None` (2)
  - `async def force_poll_once(self) -> slot.CycleOutcome` (2)
  - `async def mark_hr_chat_read(self, hr_id) -> int` (2)
  - `async def send_to_hr_chat(self, hr_id, text) -> Message` (2)
  - `async def send_to_hr_media(self, hr_id, file_path) -> Message` (2)
  - `async def ui_send_vacancy_application(self, vacancy_id) -> tuple[bool, str]` (2)
  - `async def send(self, hr, text, attachment=None, vacancy_id=None, *, force=False) -> bool` (6)
  - `async def _on_raw_update(self, _client, update, _users, _chats) -> None` (2)
  - `async def _on_dm_edit(self, _client, msg) -> None` (2)
  - `async def _on_dm_delete(self, _client, messages) -> None` (2)
  - `async def _on_dm_outgoing(self, _client, msg) -> None` (2)
  - `async def _on_dm(self, _client, msg) -> None` (2)
  - `async def log_out_session(self) -> None` (2)
  - `async def current_mode(self) -> BotMode` (2)
  - `async def run(self, *, once=False) -> None` (2)
  - `async def ui_rerun_vacancy_pipeline(self, vacancy_id) -> rerun.RerunOutcome` (4)
  - `async def ui_forget_vacancy(self, vacancy_id) -> bool` (2)

### `backend/bot/loop.py` — 237 строк

Жизненный цикл соединения: режим работы, главный цикл, выход из сеанса.

Зависит от: `adapters`, `backend.bot`, `backend.flows.dm_backfill`, `backend.models`, `backend.repository.bot_mode`, `backend.runtime_settings`

- `async def log_out_session(bot) -> None` (17)
- `async def current_mode(bot) -> BotMode` (7)
- `async def _connect(bot) -> None` (24)
- `async def _on_mode_switch(bot, prev_mode: BotMode, mode: BotMode) -> None` (21)
- `async def _tick(bot, mode: BotMode) -> None` (21)
- `async def _sleep_until_wake(bot) -> None` (17)
- `async def _disconnect(bot) -> None` (33)
- `async def run(bot, *, once: bool=False) -> None` (41)
- `async def persist_session_if_changed(bot) -> None` (25)

### `backend/bot/media.py` — 167 строк

Вложения: распознание, кэш и скачивание.

Зависит от: `config`

- `def _has_photo_content(path: Path) -> bool` (15)
- `def looks_like_photo(path: Path) -> bool` (11)
- `def classify_media(msg) -> tuple[str | None, str | None]` (11)
- `def media_cache_path(hr_id: int, tg_message_id: int, ext: str) -> Path` (5)
- `def _cache_ext(as_photo: bool, name: str | None) -> str` (12)
- `def cache_sent_file(src: Path, hr_id: int, tg_message_id: int, *, as_photo: bool) -> str | None` (24)
- `def media_path_for_db(path) -> str` (11)
- `async def download_media(client, msg, hr_id: int) -> str | None` (25)

### `backend/bot/rerun.py` — 41 строк

Ручной перезапуск разбора вакансии из окна.

Зависит от: `backend.bot`, `backend.flows`

- `async def ui_rerun_vacancy_pipeline(bot, vacancy_id: int) -> RerunOutcome` (23)

### `backend/bot/send.py` — 321 строк ⚠ подошёл к 300

Доставка отклика в Telegram: вложение, ограничения сервиса, след в базе.

Зависит от: `adapters`, `backend.bot`, `backend.flows.events`, `backend.models`, `backend.notify`, `backend.payloads`, `backend.repository.messages`, `backend.repository.vacancy_status`, `backend.telegram_time`

- `def _applied_label(force: bool) -> str` (3)
- `def _shares_provider(a, b) -> bool` (12)
- `async def ui_send_vacancy_application(bot, vacancy_id: int) -> tuple[bool, str]` (6)
- `class Errand` (12)
- `class _Outcome` (15)
- `async def _note_flood_wait(bot, error) -> None` (15)
- `async def _clear_flood_wait(bot) -> None` (12)
- `async def _deliver_dm(bot, target, text: str, attachment, vacancy_id) -> tuple[int | None, bool]` (22)
- `async def _commit_send(bot, hr: HR, text: str, outcome: _Outcome) -> bool` (41)
- `def _log_refusal(permission, hr: HR, vacancy_id: int | None) -> None` (7)
- `async def _flip_applied_alone(bot, outcome: _Outcome) -> None` (29)
- `async def _hand_over(bot, permission, text: str, attachment, vacancy_id) -> tuple[int | None, bool]` (19)
- `async def _audit_sent(bot, hr_id: int, chars: int, outcome: _Outcome) -> None` (21)
- `async def _record_send(bot, hr: HR, text: str, outcome: _Outcome, permission) -> None` (22)
- `async def send(bot, hr: HR, text: str, attachment=None, errand: Errand=Errand()) -> bool` (36)

### `backend/bot/slot.py` — 115 строк

Единственное место прогона: пока оно занято, второй цикл получает отказ.

Зависит от: `backend.notify`

- `def on_runner_loop(bot, action: Callable[[], Any]) -> None` (14)
- `def cancel_current_poll(bot) -> None` (7)
- `async def _run_task(bot, work: Callable[[], Any], label: str)` (31)
- `async def run_in_slot(bot, work: Callable[[], Any], label: str, progress: tuple[str, str, int, int] | None=None) -> tuple[CycleOutcome, Any]` (32)

### `backend/bot/updates.py` — 113 строк

Обработчики оповещений Telegram: входящее, эхо, правка, удаление, отметка о прочтении.

Зависит от: `backend.flows`, `backend.flows.dm`, `backend.message_text`, `backend.models`, `backend.notify`

- `async def _muted(bot) -> bool` (8)
- `async def on_raw_update(bot, _client, update, _users, _chats) -> None` (18)
- `async def on_dm_edit(bot, _client, msg) -> None` (18)
- `async def on_dm_delete(bot, _client, messages) -> None` (9)
- `async def on_dm_outgoing(bot, _client, msg) -> None` (13)
- `async def on_dm(bot, _client, msg) -> None` (12)

### `backend/crypto.py` — 107 строк

Шифрование секретов мастер-ключом из связки ключей ОС.

Зависит от: —

- `def _check_keyring_backend() -> None` (22)
- `def _get_or_create_master_key() -> bytes` (11)
- `def forget_master_key() -> None` (17)
- `def _cipher() -> Fernet` (2)
- `def encrypt_str(plaintext: str) -> str` (3)
- `def decrypt_str(ciphertext: str) -> str` (2)
- `def encrypt_bytes(plaintext: bytes) -> bytes` (2)
- `def decrypt_bytes(ciphertext: bytes) -> bytes` (2)

### `backend/domain/blacklist.py` — 56 строк

Поиск запрещённого слова в тексте по границам слова.

Зависит от: —

- `def _is_word_char(ch: str) -> bool` (3)
- `def _compile_word_pattern(variant: str) -> re.Pattern[str]` (13)
- `def _word_match(text_lower: str, variant: str) -> bool` (4)
- `def check_blacklist(raw_text: str, patterns: list[str]) -> str | None` (18)

### `backend/domain/company_hosts.py` — 103 строк

Хосты, которые не бывают домашним сайтом компании.

Зависит от: —

- `def _is_brand_domain(host: str) -> bool` (15)
- `def is_aggregator_host(host: str) -> bool` (12)

### `backend/domain/dedup.py` — 126 строк

Отсев повторов: векторы заведённых вакансий и поиск ближайшего к новому.

Зависит от: —

- `def cosine_top_match(query: np.ndarray, ids: np.ndarray, matrix: np.ndarray, threshold: float) -> int | None` (43)
- `class EmbeddingCache` (71)
  - `def fill(self, pairs: Iterable[tuple[int, list[float]]], width: int) -> int` (19)
  - `def append(self, vacancy_id: int, vector: list[float]) -> None` (18)
  - `def drop(self, vacancy_id: int) -> None` (7)
  - `def match(self, vector: list[float], threshold: float) -> int | None` (5)

### `backend/domain/funnel.py` — 58 строк

Ступени воронки отбора, выраженные наборами статусов вакансии.

Зависит от: `backend.models`

- `def percent_or_none(numerator: int, denominator: int) -> int | None` (14)

### `backend/domain/salary.py` — 299 строк

Разбор свободной строки зарплаты: число, как записано, и валюта.

Зависит от: `backend.models`

- `def parse_salary(salary: str | None) -> tuple[int | None, int | None, Currency | None]` (19)
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
- `def _currency(s: str) -> Currency | None` (8)

### `backend/domain/scoring.py` — 107 строк

Оценка вакансии по навыкам анкеты.

Зависит от: `backend.domain.skill_names`, `backend.models`, `backend.payloads`

- `def _build_skill_level_lookup(skills: list[ProfileSkill]) -> dict[str, int]` (27)
- `def build_skill_lookup(skills: list[ProfileSkill]) -> set[str]` (10)
- `def _required_points(level_lookup: dict[str, int], item: object) -> int` (10)
- `def _preferred_points(level_lookup: dict[str, int], item: object) -> int` (10)
- `def score_parsed(parsed: ParsedVacancy, skills: list[ProfileSkill]) -> int` (31)

### `backend/domain/skill_names.py` — 57 строк

Сведение написаний названия навыка по общему ключу.

Зависит от: —

- `def skill_key(name: str) -> str` (14)
- `def index_by_key(lookup: dict[str, T], names: Iterable[object], value: T) -> list[tuple[str, str, T]]` (31)

### `backend/domain/spellings.py` — 50 строк

Отсев повторов среди написаний: первое встреченное выигрывает.

Зависит от: —

- `def dedupe_first_wins(items: Iterable[T], key: Callable[[T], str], seen: set[str] | None=None) -> list[T]` (38)

### `backend/domain/taxonomy.py` — 16 строк

Замкнутые перечни значений, которыми описывают вакансию и анкету.

Зависит от: —


### `backend/domain/telegram_identity.py` — 113 строк

Правила опознания собеседника в Telegram по написанному о нём.

Зависит от: —

- `def _strip_link_prefixes(s: str) -> str` (29)
- `def normalize_username(hr_contact: str | None, *, typed_by_a_person: bool=False) -> str | None` (22)
- `def typed_username(value) -> str | None` (24)
- `def telegram_peer(hr) -> int | str | None` (9)

### `backend/domain/transitions.py` — 142 строк

Граф разрешённых авто-переходов статуса вакансии, вместе с условиями

Зависит от: `backend.models`

- `def is_terminal_for_auto(status: VacancyStatus) -> bool` (9)
- `def should_apply_status(current: VacancyStatus, new: VacancyStatus, *, force: bool=False) -> bool` (28)

### `backend/domain/verdict.py` — 82 строк

Приговор разобранному объявлению до того, как оно войдёт в граф статусов.

Зависит от: `backend.models`, `backend.payloads`

- `def is_empty_vacancy(parsed: ParsedVacancy | None) -> bool` (24)
- `def decide_vacancy_status(parsed: ParsedVacancy, score: int, blacklist_match: str | None, *, threshold: int) -> tuple[VacancyStatus, str | None]` (17)

### `backend/flows/apply.py` — 374 строк ⚠ подошёл к 300

Решение отправить отклик: письмо, охраны от повтора и запись исхода.

Зависит от: `adapters`, `backend.llm.cover_letter`, `backend.models`, `backend.payloads`, `backend.repository.hr_identify`

- `def _format_channel_ref(channel_username: str | None) -> str | None` (10)
- `def _build_short_text(title: str, channel_ref: str | None, prior_count: int) -> str` (22)
- `def _send_refusal(v, *, force: bool, when: str) -> str | None` (18)
- `async def try_auto_send(pipeline, hr, parsed: ParsedVacancy, vacancy_id: int) -> tuple[bool, str]` (22)
- `class _Letter` (9)
- `class _Plan` (10)
- `async def _send_plan(pipeline, hr, vacancy_id: int, force: bool) -> tuple` (31)
- `async def _full_letter(pipeline, parsed: ParsedVacancy, channel_ref: str | None, vacancy_id: int)` (29)
- `async def _hand_letter_over(pipeline, hr, letter: _Letter, vacancy_id: int, force: bool) -> tuple` (30)
- `async def _still_sendable(pipeline, vacancy_id: int, force: bool) -> str | None` (15)
- `async def send_application(pipeline, hr, parsed: ParsedVacancy, vacancy_id: int, *, force: bool=False) -> tuple[bool, str]` (27)
- `async def _send_the_letter(pipeline, hr, parsed: ParsedVacancy, vacancy_id: int, force: bool) -> tuple[bool, str]` (31)
- `def _parsed_from_row(v: Vacancy) -> ParsedVacancy` (21)
- `async def send_application_for_vacancy(pipeline, vacancy_id: int) -> tuple[bool, str]` (39)

### `backend/flows/auto_gate.py` — 48 строк

Заслон автоматики: двигает ли она эту вакансию вообще.

Зависит от: `backend.domain.transitions`, `backend.models`

- `async def status_open_for_auto(session_factory, vacancy_id: int) -> tuple[bool, VacancyStatus | None]` (34)

### `backend/flows/batches.py` — 30 строк

Разбор исходов работы, пущенной по людям разом.

Зависит от: —

- `def report_failures(hr_ids: list[int], results: list, what: str, log: logging.Logger) -> None` (25)

### `backend/flows/channels.py` — 337 строк ⚠ подошёл к 300

Обход телеграм-каналов за свежими постами.

Зависит от: `backend.flows`, `backend.models`, `backend.notify`, `backend.repository.channels`, `backend.telegram_lookup`

- `async def poll_active_channels(pipeline) -> None` (40)
- `async def poll_one_channel(pipeline, channel_id: int) -> PollOutcome` (39)
- `async def refresh_channel_metadata_for_ids(pipeline, channel_ids: list[int]) -> None` (12)
- `async def _store_metadata(pipeline, title_updates: dict[int, str], avatar_updates: dict[int, bytes]) -> None` (19)
- `async def _collect_metadata(pipeline, channels) -> tuple[dict, dict]` (30)
- `async def refresh_channel_metadata(pipeline, channels) -> None` (27)
- `async def _unseen_posts(pipeline, channel_username: str, last_id: int | None)` (28)
- `async def _take_post(pipeline, channel_id: int, channel_username: str, msg) -> bool` (17)
- `def _silence_broke_the_walk(channel_username: str, msg_id: int, silence: int) -> bool` (19)
- `async def poll_channel(pipeline, channel_id: int, channel_username: str, last_id: int | None) -> bool` (42)
- `async def advance_cursor(pipeline, channel_id: int, msg_id: int) -> None` (10)

### `backend/flows/cleanup.py` — 93 строк

Удаление вакансии конвейером — вместе с её вектором в кэше.

Зависит от: `backend.models`, `backend.repository.vacancies_life`

- `async def _delete_and_forget(pipeline, vacancy_id: int, *, trash_reason=_NO_TRASH_EVENT) -> tuple[bool, int | None]` (41)
- `async def forget_vacancy(pipeline, vacancy_id: int) -> bool` (15)
- `async def delete_vacancy_as_trash(pipeline, vacancy_id: int, reason: str | None) -> None` (11)

### `backend/flows/dm.py` — 362 строк ⚠ подошёл к 300

Личная переписка с HR: запись сообщения в обе стороны, привязка, разбор.

Зависит от: `backend.bot.media`, `backend.flows.auto_gate`, `backend.flows.dm_classify`, `backend.message_text`, `backend.payloads`, `backend.repository.hr_card`, `backend.repository.hr_identify`, `backend.repository.messages`, `backend.telegram_lookup`, `backend.telegram_time`

- `class DmHelpers` (19)
- `class _Attachment` (14)
- `async def _attachment_of(client, msg, hr_id: int) -> _Attachment` (14)
- `async def _store_outgoing_row(session_factory, msg, hr_id: int, media: _Attachment) -> OutgoingDmOutcome` (38)
- `async def persist_outgoing_dm(session_factory, client, msg, hr_id: int) -> OutgoingDmOutcome` (19)
- `async def _sender_to_listen_to(session_factory, msg)` (30)
- `async def _attributed_vacancy(session, hr_id: int, msg) -> int | None` (17)
- `def _incoming_row(msg, hr_id: int, vacancy_id: int | None, attachment: _Attachment) -> IncomingMessage` (18)
- `async def _save_incoming(session_factory, msg, attachment: _Attachment)` (36)
- `async def _status_open_for_reply(session_factory, vacancy_id: int)` (14)
- `async def _catch_up_avatar(session_factory, client, msg) -> None` (32)
- `async def _receive(dm, msg, hr_lookup) -> tuple[int | None, int | None]` (9)
- `async def _hand_to_classification(dm, msg, hr_id: int, subject) -> None` (12)
- `async def process_dm(msg, dm: DmHelpers) -> int | None` (33)

### `backend/flows/dm_backfill.py` — 294 строк

Догон пропущенной переписки с HR.

Зависит от: `backend.domain.telegram_identity`, `backend.flows.batches`, `backend.flows.dm`, `backend.models`, `backend.notify`, `backend.repository.hr_list`, `backend.repository.messages`

- `class DmHooks` (9)
- `async def _fetch_history(client, hr, limit: int) -> list | None` (41)
  - `async def read(peer) -> list` (2)
- `async def _store_outgoing(hr_id: int, dm: DmHelpers, msg) -> bool` (23)
- `async def _store_incoming(hr_id: int, dm: DmHelpers, hooks: DmHooks, msg) -> bool` (27)
- `async def _walk_messages(messages: list, hr_id: int, dm: DmHelpers, hooks: DmHooks) -> bool` (18)
- `async def _reconcile_deletes(session_factory, hr_id: int, messages: list, newest_before: int) -> bool` (37)
- `async def backfill_hr_dm_history(hr, dm: DmHelpers, hooks: DmHooks, *, backfill_limit: int, newest_before: int=0) -> None` (26)
- `async def catch_up_missed_dms(dm: DmHelpers, hooks: DmHooks, *, backfill_limit: int) -> None` (35)
- `def spawn_hr_backfill(pipeline, hr) -> None` (31)
  - `async def _run() -> None` (15)

### `backend/flows/dm_classify.py` — 288 строк

Разбор переписки с HR языковой моделью.

Зависит от: `backend.flows.auto_gate`, `backend.flows.batches`, `backend.llm.hr_reply`, `backend.models`, `backend.notify`, `backend.payloads`, `backend.repository.hr_card`, `backend.repository.vacancy_status`

- `def schedule_dm_classification(pipeline, hr_id: int, reply: PendingReply) -> None` (27)
- `async def classify_and_apply(session_factory, lm_client, lm_chat_model, text: str, target: tuple[int, int, VacancyStatus]) -> bool` (39)
- `async def _run_debounced_classify(pipeline, hr_id: int) -> None` (22)
- `async def _blacklisted_now(pipeline, hr_id: int) -> str | None` (13)
- `async def _ask_and_apply(pipeline, hr_id: int, burst: list, target) -> None` (25)
- `def _burst_text(buf: list[dict]) -> str` (8)
- `async def classify_and_apply_for_hr(pipeline, hr_id: int) -> None` (37)
- `async def _wait_out(pipeline, tasks: list, *, drain: bool) -> None` (20)
- `async def _cancel_and_wait(pipeline, *, drain: bool) -> None` (12)
- `async def _drain_buffers(pipeline) -> None` (18)
- `async def cancel_pending_dm_classifications(pipeline, *, drain: bool=False) -> None` (31)

### `backend/flows/dm_debounce.py` — 139 строк

Копилка отложенного разбора: пачки писем, таймеры над ними и начавшие.

Зависит от: —

- `class DmDebounce` (134)
  - `def remember(self, hr_id: int, letter: dict) -> int` (15)
  - `def retext(self, hr_id: int, tg_msg_id: int, text: str) -> None` (11)
  - `def forget(self, hr_id: int, tg_msg_id: int) -> None` (14)
  - `def take(self, hr_id: int) -> list[dict]` (3)
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

### `backend/flows/dm_sync.py` — 198 строк

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

### `backend/flows/embeddings.py` — 104 строк

Отпечаток текста: как его считают у поставщика и как поднимают кэш.

Зависит от: `adapters`, `backend.models`

- `class ProviderIsSilent(Exception)` (7)
- `def _is_about_the_provider(trouble: Exception) -> bool` (14)
- `async def embed_text(pipeline, text: str, what: str) -> list[float] | None` (25)
- `async def ensure_embedding_cache(pipeline, width: int) -> None` (28)

### `backend/flows/events.py` — 33 строк

Запись события вакансии своей транзакцией.

Зависит от: `backend.repository.vacancies_life`

- `async def record_vacancy_event(session_factory, vacancy_id: int, kind: str, payload: dict) -> None` (24)

### `backend/flows/ghosting.py` — 37 строк

Гашение вакансий, по которым HR замолчал дольше срока.

Зависит от: `backend.domain.transitions`, `backend.notify`, `backend.repository.vacancies_ghosting`

- `async def check_ghosting_timeouts(pipeline) -> int` (26)

### `backend/flows/ingest.py` — 150 строк

Приём объявления из канала с отсевом перепостов.

Зависит от: `backend.flows`, `backend.message_text`, `backend.models`, `backend.payloads`, `backend.repository.vacancies_life`, `backend.telegram_time`

- `async def _post_embedding(pipeline, post: ChannelPost)` (15)
- `async def _resume_or_skip(pipeline, similar_id: int, post: ChannelPost) -> None` (23)
- `async def ingest_post(pipeline, channel_id: int, channel_username: str, msg) -> None` (31)
- `def _vacancy_row(post: ChannelPost, embedding: list[float]) -> Vacancy` (14)
- `async def save_new_vacancy(pipeline, post: ChannelPost, embedding: list[float]) -> int | None` (41)

### `backend/flows/linked_article.py` — 76 строк

Статья, на которую ссылается объявление, дописанная к его тексту.

Зависит от: `adapters`

- `def _article_urls(text: str) -> list[str]` (11)
- `async def with_linked_articles(text: str) -> tuple[str, bool]` (37)

### `backend/flows/parse.py` — 336 строк ⚠ подошёл к 300

Приговор объявлению: разбор моделью, вердикт по разобранному и что дальше.

Зависит от: `backend.domain.blacklist`, `backend.domain.scoring`, `backend.domain.verdict`, `backend.flows`, `backend.flows.events`, `backend.flows.parse_write`, `backend.llm.answers`, `backend.llm.fit`, `backend.llm.vacancy`, `backend.models`, `backend.payloads`

- `async def _dropped_as_trash(pipeline, vacancy_id: int, reason: str, *, allow_delete: bool) -> bool` (22)
- `async def _fit_refusal(pipeline, parsed, text: str, vacancy_id: int) -> tuple[str | None, bool]` (51)
- `async def _auto_send_if_allowed(pipeline, hr, parsed, vacancy_id: int, status: VacancyStatus) -> None` (18)
- `async def _parsed_or_dropped(pipeline, vacancy_id: int, text: str, channel_username: str, allow_delete: bool)` (44)
- `async def _verdict_for(pipeline, parsed, text: str, vacancy_id: int) -> tuple | None` (26)
- `async def _finish_parse(pipeline, vacancy_id: int, parsed, outcome: Outcome) -> bool` (18)
- `async def _thrown_out_by_the_verdict(pipeline, vacancy_id: int, skip_reason: str | None, allow_delete: bool) -> bool` (16)
- `async def parse_and_update_vacancy(pipeline, vacancy_id: int, text: str, channel_username: str, *, allow_delete: bool=True) -> bool` (42)
- `async def is_unparsed_vacancy(pipeline, vacancy_id: int) -> bool` (11)
- `async def save_empty_vacancy(pipeline, vacancy_id: int, parsed: ParsedVacancy | None, *, reason: str=EMPTY_SKIP_REASON) -> bool` (34)

### `backend/flows/parse_write.py` — 245 строк

Запись исхода разбора: строка вакансии, её компания и её собеседник.

Зависит от: `backend.domain.salary`, `backend.models`, `backend.payloads`, `backend.repository.companies_matching`, `backend.repository.hr_identify`, `backend.repository.vacancies_life`, `backend.repository.vacancy_status`, `backend.telegram_lookup`

- `class Outcome` (13)
- `async def _resolve_hr(pipeline, parsed: ParsedVacancy | None)` (12)
- `def _clear_parsed_fields(v: Vacancy, score: int) -> None` (14)
- `def _apply_parsed_fields(v: Vacancy, parsed: ParsedVacancy | None, outcome: Outcome) -> None` (28)
- `def _fields_filled(v: Vacancy) -> list[str]` (11)
- `async def _write_parsed_row(session, vacancy_id: int, parsed: ParsedVacancy | None, outcome: Outcome) -> Vacancy | None` (21)
- `async def _resolve_company(pipeline, parsed) -> tuple[int | None, dict | None]` (32)
- `async def _link_resolved_hr(session, v: Vacancy, resolved) -> tuple[HR | None, bool]` (12)
- `def _parsed_event_payload(v: Vacancy, outcome: Outcome, decision) -> dict` (15)
- `async def persist_parse_outcome(pipeline, vacancy_id: int, parsed: ParsedVacancy | None, outcome: Outcome) -> tuple[HR | None, bool] | None` (41)

### `backend/flows/pipeline.py` — 319 строк ⚠ подошёл к 300

Сборка конвейера: его состояние, общие ресурсы и поверхность для зовущих.

Зависит от: `backend.domain.dedup`, `backend.flows`, `backend.flows.dm`, `backend.flows.dm_backfill`, `backend.flows.dm_debounce`, `backend.llm`, `backend.llm.candidate`, `backend.models`, `backend.notify`, `backend.repository.blacklist_marks`, `backend.repository.profile`, `backend.repository.profile_block`, `backend.repository.profile_languages`, `backend.repository.profile_skills`

- `def _declare_caches(pipeline) -> None` (16)
- `def _declare_window_hooks(pipeline) -> None` (32)
- `def _declare_dm_debounce(pipeline) -> None` (19)
- `class LmProviders` (14)
- `class IngestionPipeline` (187)
  - `def mark_shutting_down(self) -> None` (5)
  - `def emit_progress(self, stage: str, label: str, current: int, total: int) -> None` (2)
  - `def fire_contacts_changed(self) -> None` (2)
  - `def fire_vacancies_changed(self) -> None` (2)
  - `async def reload_resources(self) -> None` (28)
  - `def cv_path(self)` (11)
  - `async def check_ghosting_timeouts(self) -> int` (2)
  - `async def rerun_pipeline_for_vacancy(self, vacancy_id) -> rerun.RerunPipelineOutcome` (4)
  - `async def recover_orphan_vacancies(self) -> int` (2)
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
  - `async def send_application_for_vacancy(self, vacancy_id) -> tuple[bool, str]` (2)

### `backend/flows/rerun.py` — 317 строк ⚠ подошёл к 300

Повторный разбор уже заведённой вакансии.

Зависит от: `backend.flows`, `backend.message_text`, `backend.models`, `backend.repository.channels`, `backend.repository.vacancy_status`

- `class _Origin` (14)
- `async def _vacancy_origin(pipeline, vacancy_id: int) -> _Origin | None` (23)
- `async def _post_text(msg, origin: _Origin, vacancy_id: int) -> tuple[str, str] | None` (26)
- `async def _fetch_fresh_text(pipeline, origin: _Origin, vacancy_id: int)` (33)
- `async def _store(pipeline, vacancy_id: int, **fields) -> bool` (17)
- `async def _refresh_embedding(pipeline, vacancy_id: int, text: str) -> None` (32)
- `async def _note_rerun(pipeline, vacancy_id: int, origin: '_Origin') -> None` (5)
- `async def _text_to_parse(pipeline, origin: '_Origin', vacancy_id: int)` (15)
- `async def rerun_pipeline_for_vacancy(pipeline, vacancy_id: int) -> RerunPipelineOutcome` (39)
- `async def _orphan_rows(pipeline) -> list` (25)
- `async def recover_orphan_vacancies(pipeline) -> int` (39)

### `backend/health.py` — 68 строк

Живо ли то, на чём держится работа: база, Telegram и модели.

Зависит от: `adapters`

- `async def database_alive(session_factory) -> bool` (14)
- `def telegram_alive(bot) -> bool` (7)
- `async def model_alive(cfg, kind: str) -> bool` (22)

### `backend/incoming.py` — 94 строк

Приведение внешнего ввода к значениям, годным для записи.

Зависит от: —

- `def text_or_none(value) -> str | None` (16)
- `def int_or_none(value) -> int | None` (3)
- `def float_or_none(value) -> float | None` (3)
- `def _number_or_none(value, kind)` (19)
- `def moment_or_none(value) -> datetime | None` (16)
- `def str_list(value) -> list[str]` (11)

### `backend/llm/answers.py` — 210 строк

Разбор того, что ответила модель, и жалоба, когда разбор не удался.

Зависит от: —

- `def _last_object_in(text: str) -> tuple[int, int, str] | None` (27)
- `def extract_last_json(answer: str) -> str | None` (37)
- `def json_object(answer: str, log: logging.Logger, purpose: str) -> dict | None` (23)
- `def log_unparseable(answer: str, log: logging.Logger, purpose: str) -> None` (18)
- `def truncation_trouble(finish_reason: str | None) -> str | None` (9)
- `def wants_more_room(parsed, finish_reason: str | None) -> bool` (18)
- `def str_or_none(value) -> str | None` (10)
- `def normalize_enum(value, allowed: tuple[str, ...]) -> str | None` (15)

### `backend/llm/candidate.py` — 149 строк

Сведения о кандидате в том виде, в каком они уходят в промпт.

Зависит от: `backend.incoming`, `backend.models`

- `class CandidateLanguage` (5)
- `class CandidateProfile` (20)
- `def _format_labels(values: list[str] | None, labels: dict[str, str]) -> str` (12)
- `def format_grades(grades: list[str] | None) -> str` (3)
- `def format_work_formats(formats: list[str] | None) -> str` (3)
- `def format_languages(languages: list[CandidateLanguage] | None) -> str` (16)
- `def format_text(text: str | None) -> str` (8)
- `def format_known_skills(skills) -> str` (17)
- `def build_candidate_profile(profile: Profile | None, languages: list[ProfileLanguage]) -> CandidateProfile` (22)

### `backend/llm/company.py` — 174 строк

Арбитр: та же это компания, что уже заведена, или новая.

Зависит от: `adapters.lm_chat`, `backend.incoming`, `backend.llm.answers`, `backend.llm.external`, `backend.llm.rules`

- `def _shown_candidates(parsed_name: str, parsed_website: str | None, candidates: list) -> str` (20)
- `def _dedupe_request(parsed_name: str, parsed_website: str | None, candidates: list) -> ChatRequest` (28)
- `def _matched_id(answer: str) -> tuple[int | None, str | None]` (22)
- `async def dedupe_company_with_llm(client: httpx.AsyncClient, model: str, *, parsed_name: str, parsed_website: str | None, candidates: list) -> tuple[int | None, str | None]` (41)

### `backend/llm/cover_letter.py` — 287 строк

Сочинение письма-отклика.

Зависит от: `adapters.lm_chat`, `backend.llm.external`, `backend.llm.factcheck`, `backend.payloads`

- `def _letter_request(profile_block: str, parsed: ParsedVacancy, channel_ref: str | None) -> ChatRequest` (39)
- `def _vacancy_ref(parsed: ParsedVacancy, channel_ref) -> str` (9)
- `def _with_vacancy_filled(raw_text: str, parsed: ParsedVacancy, channel_ref) -> str` (27)
- `def _letter_refusal(text: str, finish_reason) -> str | None` (24)
- `async def generate_cover_letter(profile_block: str, parsed: ParsedVacancy, client: httpx.AsyncClient, model: str, *, channel_ref: str | None=None) -> str | None` (41)

### `backend/llm/cv.py` — 387 строк ⚠ подошёл к 300

Разбор резюме моделью: из текста файла — заполненная анкета.

Зависит от: `adapters.lm_chat`, `backend.domain.skill_names`, `backend.domain.spellings`, `backend.domain.taxonomy`, `backend.incoming`, `backend.llm.answers`, `backend.llm.external`, `backend.payloads`

- `def _normalize_enum_list(raw: object, allowed: tuple[str, ...]) -> list[str]` (9)
- `def _normalize_lang_level(value: object) -> str | None` (11)
- `def _parse_language_item(item) -> ParsedCvLanguage | None` (10)
- `def _parse_languages(raw: object) -> list[ParsedCvLanguage]` (8)
- `def _parse_date(value) -> date | None` (21)
- `def _parse_profile(data: dict) -> ParsedCvProfile | None` (23)
- `def _parse_skill(item) -> ParsedCvSkill | None` (32)
- `def _parse_experience(item) -> ParsedCvExperience | None` (18)
- `def _parse_cv_json(answer: str) -> ParsedCv | None` (31)
- `async def parse_cv(text: str, client: httpx.AsyncClient, model: str) -> ParsedCv | None` (35)

### `backend/llm/external.py` — 47 строк

Внешний текст в виде, пригодном для вставки в промпт.

Зависит от: —

- `def external_block(text: str, what: str, then: str='') -> str` (14)
- `def wrap_external(text: str) -> str` (15)

### `backend/llm/factcheck.py` — 173 строк

Сверка письма-отклика с тем, что о кандидате известно.

Зависит от: `adapters.lm_chat`, `backend.incoming`, `backend.llm.answers`, `backend.llm.external`

- `def _factcheck_request(profile_block: str, letter: str, about: str) -> ChatRequest` (23)
- `def _verdict_of(obj: dict, elapsed: float) -> tuple[bool, list[str]]` (29)
- `async def factcheck_cover_letter(profile_block: str, letter: str, client: httpx.AsyncClient, model: str, *, about: str='') -> tuple[bool, list[str]]` (39)

### `backend/llm/fit.py` — 407 строк ⚠ подошёл к 300

Приговор о пригодности вакансии кандидату.

Зависит от: `adapters.lm_chat`, `backend.llm.answers`, `backend.llm.candidate`, `backend.llm.external`, `backend.llm.hallucination`, `backend.llm.rules`, `backend.payloads`

- `def _parse_fit_validation(answer: str) -> FitValidation | None` (10)
- `def _vacancy_block(parsed: ParsedVacancy, raw_text: str) -> str` (20)
- `def _fit_request(parsed: ParsedVacancy, raw_text: str, profile, max_tokens: int)` (26)
- `def _without_invented_reason(validation: FitValidation, raw_text: str, profile)` (37)
- `async def validate_vacancy_fit(parsed: ParsedVacancy, raw_text: str, client: httpx.AsyncClient, model: str, *, profile: CandidateProfile) -> tuple[FitValidation | None, str | None]` (40)

### `backend/llm/hallucination.py` — 280 строк

Чем негодно обоснование, которое дала модель.

Зависит от: `backend.domain.taxonomy`, `backend.llm.candidate`

- `def _language_root(name: str) -> str | None` (18)
- `def _language_marker(root: str, name: str, inference_verbs: str, cefr_text: str) -> tuple[re.Pattern[str], re.Pattern[str]]` (21)
- `def _build_profile_hallucination_markers(profile: CandidateProfile) -> tuple[tuple[re.Pattern[str], re.Pattern[str]], ...]` (30)
- `def looks_hallucinated(reason: str, raw_text: str, profile: CandidateProfile) -> str | None` (23)
- `def breaks_reason_style(reason: str) -> str | None` (15)

### `backend/llm/hr_reply.py` — 253 строк

Разбор ответа HR: на каком этапе теперь отклик.

Зависит от: `adapters.lm_chat`, `backend.domain.transitions`, `backend.llm.answers`, `backend.llm.external`, `backend.models`, `backend.payloads`

- `def _parse_classification(answer: str) -> Classification | None` (19)
- `def _allowed_next(current_status: VacancyStatus) -> set[VacancyStatus]` (21)
- `def _as_line(allowed: set[VacancyStatus]) -> str` (3)
- `def _classify_request(text: str, current_status: VacancyStatus, allowed_str: str) -> ChatRequest` (21)
- `async def classify_hr_reply(text: str, current_status: VacancyStatus, client: httpx.AsyncClient, model: str) -> Classification | None` (47)

### `backend/llm/rules.py` — 66 строк

Приметы предметной области, общие для наставлений модели.

Зависит от: `backend.domain.company_hosts`


### `backend/llm/skills.py` — 135 строк

Приведение названий технологий к виду, пригодному для стека вакансии.

Зависит от: `backend.domain.skill_names`, `backend.domain.spellings`

- `def _strip_version(s: str) -> str` (12)
- `def _capitalize_skill(s: str) -> str` (20)
- `def _as_items(raw: object) -> list` (16)
- `def clean_stack_items(raw: object, seen: set[str]) -> list[str]` (30)

### `backend/llm/vacancy.py` — 447 строк ⚠ подошёл к 300

Разбор объявления о вакансии в структурированные поля.

Зависит от: `adapters.lm_chat`, `backend.domain.taxonomy`, `backend.domain.telegram_identity`, `backend.llm.answers`, `backend.llm.candidate`, `backend.llm.external`, `backend.llm.rules`, `backend.llm.skills`, `backend.payloads`

- `def _split_stack(data: dict) -> tuple[list, list]` (19)
- `def _company_name_and_site(company_name: str | None, company_website: str | None) -> tuple[str | None, str | None]` (28)
- `def _address_after_label(value: str) -> str` (15)
- `def _hr_contact(hr_contact: str | None) -> str | None` (7)
- `def _way_to_apply(other_contact: str | None) -> str | None` (22)
- `def _parse_vacancy_json(answer: str) -> ParsedVacancy | None` (36)
  - `def _text_field(field: str) -> str | None` (2)
- `def _parse_request(text: str, known_skills, max_tokens: int) -> ChatRequest` (18)
- `def _without_channel_as_hr(parsed: ParsedVacancy, channel_username: str | None) -> ParsedVacancy` (16)
- `def _log_parsed(parsed: ParsedVacancy) -> None` (10)
- `async def parse_vacancy(text: str, client: httpx.AsyncClient, model: str, channel_username: str | None=None, *, known_skills=None) -> tuple[ParsedVacancy | None, str | None]` (50)

### `backend/log_buffer.py` — 168 строк

Журнал в памяти для экрана «Логи»: кольцо записей и снимок для окна.

Зависит от: `backend.log_secrets`

- `class LogBufferHandler(logging.Handler)` (107)
  - `def emit(self, record: logging.LogRecord) -> None` (33)
  - `def handleError(self, record: logging.LogRecord) -> None` (6)
  - `def snapshot(self) -> list[dict]` (3)
  - `def page(self) -> dict` (44)
  - `def clear(self) -> int` (5)
- `def install() -> LogBufferHandler` (23)
- `def get_handler() -> LogBufferHandler` (2)

### `backend/log_file.py` — 62 строк

Файл журнала, переживающий сорванный переход на новый файл.

Зависит от: `backend.log_secrets`

- `class LogFileHandler(RotatingFileHandler)` (53)
  - `def _complain_once(self, what: str, record: logging.LogRecord | None) -> None` (11)
  - `def doRollover(self) -> None` (16)
  - `def handleError(self, record: logging.LogRecord) -> None` (2)

### `backend/log_secrets.py` — 152 строк

Вымарывание секретов из журнала — включая тот случай, когда запись сломалась.

Зависит от: `config`

- `def report_own_failure(what: str, record: logging.LogRecord | None) -> None` (33)
- `def report_own_failure_once(what: str, record: logging.LogRecord) -> None` (13)
- `def _redact(text: str) -> str` (5)
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

### `backend/models/__init__.py` — 68 строк

Объявления таблиц базы, собранные из всех предметов.

Зависит от: `backend.models.base`, `backend.models.contacts`, `backend.models.enums`, `backend.models.message`, `backend.models.profile`, `backend.models.settings`, `backend.models.vacancy`

Отдаёт наружу: `HR`, `AppSetting`, `Base`, `BLACKLIST_KINDS`, `Blacklist`, `BotMode`, `BotState`, `Company`, `Currency`, `LlmConfig`, `LlmConfigKind`, `Message`, `Profile`, `ProfileExperience`, `ProfileLanguage`, `ProfileSkill`, `StatusHistorySource`, `status_code`, `TelegramChannel`, `TgAccount`, `TrashEvent`, `Vacancy`, `VacancyEvent`, `VacancyStatus`, `VacancyStatusHistory`, `profile_experience_skills`


### `backend/models/base.py` — 65 строк

Основание, от которого объявляются таблицы.

Зависит от: —

- `class Base(DeclarativeBase)` (2)
- `def enum_column(values: type[enum.Enum], name: str) -> SQLEnum` (12)
- `class IdMixin` (4)
- `class CreatedAtMixin` (8)
- `class UpdatedAtMixin` (14)

### `backend/models/contacts.py` — 51 строк

Таблицы сторон, с которыми связана вакансия.

Зависит от: `backend.models.base`

- `class TelegramChannel(IdMixin, Base)` (11)
- `class HR(IdMixin, Base)` (17)
- `class Company(IdMixin, Base)` (10)

### `backend/models/enums.py` — 70 строк

Перечисления, которыми колонки ограничивают набор значений.

Зависит от: —

- `class BotMode(enum.Enum)` (4)
- `class Currency(enum.Enum)` (10)
- `class VacancyStatus(enum.Enum)` (12)
- `def status_code(status: VacancyStatus) -> str` (15)
- `class StatusHistorySource(enum.Enum)` (11)
- `class LlmConfigKind(enum.Enum)` (3)

### `backend/models/message.py` — 64 строк

Таблица переписки с HR.

Зависит от: `backend.models.base`

- `class Message(IdMixin, Base)` (46)

### `backend/models/profile.py` — 98 строк

Таблицы анкеты кандидата.

Зависит от: `backend.models.base`

- `class Profile(IdMixin, UpdatedAtMixin, Base)` (21)
- `class ProfileLanguage(IdMixin, Base)` (19)
- `class ProfileSkill(IdMixin, Base)` (10)
- `class ProfileExperience(IdMixin, Base)` (18)

### `backend/models/settings.py` — 99 строк

Таблицы, которыми настраивают работу бота.

Зависит от: `backend.models.base`, `backend.models.enums`

- `class BotState(IdMixin, Base)` (16)
- `class Blacklist(IdMixin, CreatedAtMixin, Base)` (7)
- `class TgAccount(IdMixin, UpdatedAtMixin, Base)` (18)
- `class LlmConfig(IdMixin, UpdatedAtMixin, Base)` (14)
- `class AppSetting(UpdatedAtMixin, Base)` (7)

### `backend/models/vacancy.py` — 178 строк

Таблицы, в которых конвейер записывает судьбу разобранного поста.

Зависит от: `backend.models.base`, `backend.models.contacts`, `backend.models.enums`

- `class Vacancy(IdMixin, CreatedAtMixin, Base)` (61)
- `class VacancyEvent(IdMixin, CreatedAtMixin, Base)` (16)
- `class TrashEvent(IdMixin, CreatedAtMixin, Base)` (34)
- `class VacancyStatusHistory(IdMixin, Base)` (38)

### `backend/notify.py` — 20 строк

Оповещение окна: позвать подписчика, не дав его поломке уронить работу.

Зависит от: —

- `def fire(hook, name: str, *args) -> None` (13)

### `backend/payloads.py` — 398 строк ⚠ подошёл к 300

Свёртки значений, ходящих между слоями.

Зависит от: `backend.models`

- `class ChannelPost` (12)
- `class OutgoingMessage` (21)
- `class IncomingMessage` (19)
- `class PendingReply` (15)
- `class ParsedCvProfile` (13)
- `class ParsedCvLanguage` (3)
- `class ParsedCvSkill` (5)
- `class ParsedCvExperience` (9)
- `class ParsedCv` (5)
- `class Classification` (3)
- `class ParsedVacancy` (38)
  - `def stack(self) -> list[str]` (8)
- `class FitValidation` (3)
- `class VacancyDetail` (4)
- `class HrWithCount` (6)
- `class HrDetail` (15)
- `class CompanyDetail` (12)
- `class CompanyWithCount` (4)
- `class ChannelWithCount` (4)
- `class ChannelStats` (20)
- `class ChannelDetail` (4)
- `class VacancyFilter` (53)

### `backend/repository/blacklist.py` — 322 строк ⚠ подошёл к 300

Ведение чёрного списка.

Зависит от: `backend.incoming`, `backend.models`, `backend.repository`, `backend.repository.blacklist_marks`

- `async def _hold_the_channel_rule(session: AsyncSession, kind: str) -> None` (13)
- `async def set_blacklist_active(session: AsyncSession, blacklist_id: int, active: bool) -> bool` (23)
- `async def deactivate_blacklist_values(session: AsyncSession, kind: str, candidates: list[str]) -> int` (23)
- `async def rename_blacklist_marks(session: AsyncSession, kind: str, *, old_value: str, new_value: str) -> None` (41)
- `class BlacklistUpdateError(ValueError)` (2)
- `def _required_value(value) -> str` (11)
- `async def _free_value(session: AsyncSession, row: Blacklist, value: str) -> str` (10)
- `async def update_blacklist(session: AsyncSession, blacklist_id: int, *, value=_BLACKLIST_FIELD_UNSET, reason=_BLACKLIST_FIELD_UNSET) -> bool` (32)
- `async def _same_entry(session: AsyncSession, kind: str, value: str) -> Blacklist | None` (11)
- `def _reuse_existing(existing: Blacklist, reason: str | None) -> BlacklistOutcome` (20)
- `async def _insert_blacklist(session: AsyncSession, kind: str, value: str, reason: str | None) -> Blacklist` (15)
- `async def create_blacklist(session: AsyncSession, *, kind: str, value: str, reason: str | None=None) -> tuple[Blacklist, BlacklistOutcome]` (32)
- `async def delete_blacklist(session: AsyncSession, blacklist_id: int) -> bool` (18)
- `async def list_blacklist(session: AsyncSession) -> list[Blacklist]` (15)

### `backend/repository/blacklist_candidates.py` — 104 строк

Подсказки «кого предложить в чёрный список» для окна заведения.

Зависит от: `backend.models`, `backend.repository.blacklist_marks`, `backend.repository.channels`, `backend.repository.companies_card`, `backend.repository.hr_card`, `backend.repository.hr_identify`

- `def _by_label(rows: list[dict]) -> list[dict]` (9)
- `def _named_candidates(named: list[tuple[str | None, str | None]]) -> list[dict]` (14)
- `async def _company_candidates(session: AsyncSession) -> list[dict]` (13)
- `async def list_blacklist_candidates(session: AsyncSession, kind: str) -> list[dict]` (45)

### `backend/repository/blacklist_marks.py` — 167 строк

Активные строки чёрного списка, по которым предметы получают отметку.

Зависит от: `backend.models`

- `def account_mark(telegram_user_id: int) -> str` (9)
- `def nickname_mark(telegram_username: str) -> str` (3)
- `def _account_id_of(value: str) -> int | None` (9)
- `def active_mark_of(kind: str, candidates: list[str])` (14)
- `async def active_blacklist_value(session: AsyncSession, kind: str, candidates: list[str]) -> str | None` (21)
- `async def active_blacklist_values(session: AsyncSession, kind: str) -> set[str]` (14)
- `async def _nicknames_of_marked_people(session: AsyncSession) -> list[str]` (30)
- `async def load_active_blacklist_patterns(session: AsyncSession) -> list[str]` (20)
- `def marked_by(candidates: list[str], values: set[str]) -> bool` (9)
- `def preferred_blacklist_value(candidates: list[str]) -> str | None` (10)

### `backend/repository/bot_mode.py` — 50 строк

Режим бота, записанный в единственной строке состояния.

Зависит от: `backend.models`

- `async def _state_row(session: AsyncSession) -> BotState | None` (3)
- `async def read_mode(session: AsyncSession) -> BotMode` (8)
- `async def write_mode(session: AsyncSession, mode: BotMode) -> None` (17)

### `backend/repository/channels.py` — 411 строк ⚠ подошёл к 300

Ведение записей о телеграм-каналах.

Зависит от: `backend.domain.funnel`, `backend.models`, `backend.payloads`, `backend.repository.blacklist_marks`, `backend.repository.search`, `backend.repository.vacancies_common`, `backend.repository.vacancies_life`

- `async def list_named_channels(session: AsyncSession, *, ids: list[int] | None=None) -> list[TelegramChannel]` (23)
- `def channel_blacklist_candidates(ch: TelegramChannel) -> list[str]` (14)
- `def _is_blacklisted(ch: TelegramChannel, bl_values: set[str]) -> bool` (8)
- `async def _channel_blacklist_value(session: AsyncSession, ch: TelegramChannel) -> str | None` (9)
- `def _channels_with_counts_query()` (16)
- `async def list_telegram_channels(session: AsyncSession, search: str | None=None) -> list[ChannelWithCount]` (32)
- `async def _vacancies_per_day(session: AsyncSession, channel_id: int) -> float` (20)
- `async def _channel_stats(session: AsyncSession, channel_id: int, counts_by_enum: dict) -> ChannelStats` (32)
- `async def get_channel_detail(session: AsyncSession, channel_id: int) -> ChannelDetail | None` (21)
- `async def find_channel_by_username(session: AsyncSession, username: str) -> TelegramChannel | None` (17)
- `async def create_channel(session: AsyncSession, username: str, title: str | None, avatar: bytes | None) -> int` (20)
- `async def set_channel_active(session: AsyncSession, channel_id: int, is_active: bool) -> bool` (22)
- `async def deactivate_blacklisted_channels(session: AsyncSession) -> int` (24)
- `async def is_channel_blacklisted(session: AsyncSession, channel_id: int) -> bool` (14)
- `async def set_all_channels_active(session: AsyncSession, is_active: bool) -> int` (28)
- `async def reset_channel_cursor(session: AsyncSession, channel_id: int) -> bool` (9)
- `async def delete_channel(session: AsyncSession, channel_id: int) -> int | None` (39)

### `backend/repository/companies_card.py` — 298 строк

Ведение записей о компаниях.

Зависит от: `backend.domain.spellings`, `backend.incoming`, `backend.models`, `backend.payloads`, `backend.repository.blacklist`, `backend.repository.blacklist_marks`, `backend.repository.merging`, `backend.repository.vacancies_common`, `backend.repository.vacancies_life`

- `async def create_company(session: AsyncSession, *, name: str, website: str | None=None, aliases: list[str] | None=None, notes: str | None=None) -> Company` (37)
- `def company_blacklist_candidates(co: Company) -> list[str]` (11)
- `async def _company_blacklist_value(session: AsyncSession, co: Company) -> str | None` (6)
- `async def get_company_detail(session: AsyncSession, company_id: int) -> 'CompanyDetail | None'` (34)
- `def add_company_spellings(co: Company, incoming: list) -> None` (25)
- `def typed_spellings(aliases) -> list[str]` (14)
- `async def update_company_fields(session: AsyncSession, company_id: int, **fields) -> bool` (43)
- `async def delete_company(session: AsyncSession, company_id: int) -> bool` (22)
- `class _AbsorbedCompany` (7)
- `def _carry_company_to_survivor(survivor: Company, taken: _AbsorbedCompany) -> None` (19)
- `async def merge_company(session: AsyncSession, *, absorbed_id: int, survivor_id: int) -> None` (37)

### `backend/repository/companies_keys.py` — 150 строк

Приведение компании к ключам, по которым её сравнивают.

Зависит от: `backend.domain.company_hosts`, `backend.incoming`

- `def _translit_cyr_to_latin(s: str) -> str` (2)
- `def _without_edge_legal_forms(words: list[str]) -> list[str]` (17)
- `def normalize_company_name(s: str | None) -> str` (17)
- `def normalize_host(url: str | None) -> str` (23)
- `def signal_host(host: str) -> str` (11)
- `def real_corporate_website(url: str | None) -> str | None` (15)
- `def hosts_compatible(a: str, b: str) -> bool` (6)

### `backend/repository/companies_list.py` — 51 строк

Перечень компаний со счётчиками.

Зависит от: `backend.incoming`, `backend.models`, `backend.payloads`, `backend.repository.blacklist_marks`, `backend.repository.companies_card`, `backend.repository.paging`, `backend.repository.search`, `backend.repository.vacancies_common`

- `async def list_companies_with_counts(session: AsyncSession, search: str | None=None, *, limit: int | None=None, offset: int=0) -> tuple[list[CompanyWithCount], bool]` (36)

### `backend/repository/companies_matching.py` — 479 строк ⚠ подошёл к 300

Сведение разобранной из вакансии компании с уже заведённой.

Зависит от: `backend.incoming`, `backend.llm.company`, `backend.models`, `backend.repository.companies_card`, `backend.repository.companies_keys`

- `def _known_spellings(company: Company) -> tuple[str, list[str]]` (13)
- `def _enrich_company_with_parsed(company: Company, parsed_name: str, parsed_website: str | None) -> None` (23)
- `def _accept_company_match(company: Company, parsed_name: str, parsed_website: str | None, decision: dict, stage: str) -> tuple[Company, dict]` (24)
- `def _keep_pre_create_stage(decision: dict) -> None` (10)
- `async def _insert_company(session: AsyncSession, name: str, website: str | None, decision: dict) -> Company | None` (25)
- `async def _company_by_exact_name(session: AsyncSession, name: str) -> Company | None` (12)
- `async def _create_company_row(session: AsyncSession, name: str, website: str | None, decision: dict, seen_ids: set[int]) -> tuple[Company | None, dict]` (40)
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

### `backend/repository/hr_card.py` — 399 строк ⚠ подошёл к 300

Одна запись HR: чтение, правка, слияние, удаление.

Зависит от: `backend.domain.telegram_identity`, `backend.incoming`, `backend.models`, `backend.payloads`, `backend.repository.blacklist`, `backend.repository.blacklist_marks`, `backend.repository.merging`, `backend.repository.messages`, `backend.repository.vacancies_common`, `backend.repository.vacancies_life`

- `async def update_hr_fields(session: AsyncSession, hr_id: int, **fields) -> bool` (32)
- `async def _vacancy_count_of(session: AsyncSession, hr_id: int) -> int` (8)
- `async def _last_company_of(session: AsyncSession, hr_id: int) -> tuple[int | None, str | None]` (21)
- `async def _unread_count_of(session: AsyncSession, hr_id: int) -> int` (11)
- `async def get_hr_detail(session: AsyncSession, hr_id: int) -> HrDetail | None` (23)
- `def _marks_of(user_id: int | None, username: str | None) -> list[str]` (13)
- `def hr_blacklist_candidates(hr: HR) -> list[str]` (15)
- `async def hr_blacklist_value(session: AsyncSession, hr: HR) -> str | None` (2)
- `async def delete_hr(session: AsyncSession, hr_id: int) -> bool` (27)
- `class _AbsorbedHr` (14)
- `async def _drop_letters_the_survivor_already_has(session: AsyncSession, absorbed_id: int, survivor_id: int) -> int` (31)
- `async def _move_or_drop_chat(session: AsyncSession, absorbed_id: int, survivor_id: int, survivor_has_tg: bool) -> tuple[int, int]` (28)
- `def _carry_to_survivor(survivor: HR, taken: _AbsorbedHr, survivor_has_tg: bool) -> None` (19)
- `async def _carry_marks_to_survivor(session: AsyncSession, written_before: list[str], survivor: HR) -> None` (28)
- `async def merge_hr(session: AsyncSession, *, absorbed_id: int, survivor_id: int) -> None` (45)

### `backend/repository/hr_identify.py` — 266 строк

Соответствие записи HR данным Telegram.

Зависит от: `backend.models`, `backend.repository.vacancies_common`

- `async def find_known_hr(session: AsyncSession, telegram_user_id: int, telegram_username: str | None=None) -> HR | None` (40)
- `async def find_latest_vacancy_id_for_hr(session: AsyncSession, hr_id: int, *, as_of: datetime | None=None) -> int | None` (38)
- `async def count_recent_outgoing_with_vacancy_for_hr(session: AsyncSession, hr_id: int, *, window_days: int) -> int` (26)
- `async def resolve_reply_target_vacancy(session: AsyncSession, hr_id: int, reply_to_tg_msg_id: int) -> int | None` (24)
- `def telegram_full_name(user) -> str | None` (3)
- `def refresh_hr_from_telegram(hr: HR, user, *, avatar: bytes | None) -> None` (30)
- `async def create_hr(session: AsyncSession, *, name: str | None, telegram_username: str | None, telegram_user_id: int | None=None, notes: str | None=None) -> HR` (42)
- `async def find_or_create_hr(session: AsyncSession, user, *, avatar: bytes | None=None) -> tuple[HR, bool]` (23)

### `backend/repository/hr_list.py` — 218 строк

Перечни HR со счётчиками.

Зависит от: `backend.models`, `backend.payloads`, `backend.repository.blacklist_marks`, `backend.repository.hr_card`, `backend.repository.hr_identify`, `backend.repository.messages`, `backend.repository.paging`, `backend.repository.search`, `backend.repository.vacancies_common`

- `async def list_hrs_for_backfill(session: AsyncSession) -> list[HR]` (12)
- `def _hr_counts_query(sort_by: str)` (39)
- `async def _last_company_by_hr(session: AsyncSession) -> dict[int, str]` (26)
- `async def _unread_by_hr(session: AsyncSession) -> dict[int, int]` (17)
- `async def list_hr_with_counts(session: AsyncSession, search: str | None=None, *, limit: int | None=None, offset: int=0, sort_by: str='vacancy_count') -> tuple[list[HrWithCount], bool]` (45)
- `async def list_hrs_for_company(session: AsyncSession, company_id: int) -> list[tuple[HR, int]]` (16)
- `async def list_hrs_with_unread(session: AsyncSession) -> list[dict]` (30)

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

### `backend/repository/profile_block.py` — 110 строк

Сборка текстового блока анкеты для наставления модели.

Зависит от: `backend.repository.profile`, `backend.repository.profile_experience`, `backend.repository.profile_skills`

- `def _skills_lines(skills: list) -> list[str]` (12)
- `def _years_in_it(experiences: list) -> int` (14)
- `def _header_lines(profile, experiences: list) -> list[str]` (19)
- `def _experience_lines(experiences: list) -> list[str]` (13)
- `async def build_profile_block(session: AsyncSession) -> str` (28)

### `backend/repository/profile_cv.py` — 165 строк

Запись анкеты, разобранной моделью из резюме.

Зависит от: `backend.domain.skill_names`, `backend.models`, `backend.payloads`, `backend.repository.profile_experience`, `backend.repository.profile_languages`, `backend.repository.profile_skills`

- `async def _wipe_profile(session: AsyncSession) -> None` (11)
- `async def _add_parsed_skills(session: AsyncSession, profile_id: int, skills) -> dict[str, ProfileSkill]` (21)
- `async def _add_parsed_experience(session: AsyncSession, profile_id: int, experience, skill_lookup: dict[str, ProfileSkill]) -> None` (32)
- `async def _upsert_cv_path(session: AsyncSession, cv_path: str) -> None` (8)
- `def _new_profile(p) -> Profile` (20)
- `async def save_parsed_cv(session: AsyncSession, parsed: ParsedCv, *, cv_path: str | None=None) -> None` (40)

### `backend/repository/profile_experience.py` — 162 строк

Места работы, названные в анкете кандидата.

Зависит от: `backend.domain.skill_names`, `backend.domain.spellings`, `backend.incoming`, `backend.models`, `backend.repository.profile_skills`

- `async def wipe_experience(session: AsyncSession) -> None` (10)
- `def _skills_by_key(rows: list[ProfileSkill]) -> dict[str, ProfileSkill]` (11)
- `async def list_experience(session: AsyncSession) -> list[ProfileExperience]` (13)
- `class SaveExperienceError(ValueError)` (11)
- `def _checked_experience_rows(rows: list[dict]) -> list[tuple[dict, date, date | None]]` (33)
- `def _add_experience_rows(session: AsyncSession, checked: list, profile_id: int, skills_by_name: dict) -> None` (29)
- `async def save_experience(session: AsyncSession, rows: list[dict], profile_id: int) -> None` (22)

### `backend/repository/profile_languages.py` — 47 строк

Языки, названные в анкете кандидата.

Зависит от: `backend.models`

- `async def list_profile_languages(session: AsyncSession) -> list[ProfileLanguage]` (8)
- `async def replace_profile_languages(session: AsyncSession, profile_id: int, items: list[tuple[str, str]]) -> None` (25)

### `backend/repository/profile_skills.py` — 136 строк

Навыки, названные в анкете кандидата.

Зависит от: `backend.domain.skill_names`, `backend.incoming`, `backend.models`

- `def index_skill_keys(lookup: dict[str, ProfileSkill], names: tuple[str, ...], row: ProfileSkill, where: str) -> None` (19)
- `async def list_skills(session: AsyncSession) -> list[ProfileSkill]` (10)
- `def _skill_columns(row: dict) -> dict | None` (19)
- `def _upsert_skills(session: AsyncSession, rows: list[dict], existing: dict, profile_id: int) -> set[int]` (26)
- `async def _drop_skills(session: AsyncSession, existing: dict, drop_ids: set[int]) -> None` (15)
- `async def save_skills(session: AsyncSession, rows: list[dict], profile_id: int) -> None` (23)

### `backend/repository/search.py` — 26 строк

Отсев списка по строке поиска — тот, что идёт на стороне питона.

Зависит от: —

- `def matches_search(search: str | None, *values: object) -> bool` (12)

### `backend/repository/stats_common.py` — 83 строк

Кирпичи, из которых обе половины экрана статистики собирают свои числа.

Зависит от: `backend.models`, `backend.repository.vacancies_common`

- `def status_cond(statuses)` (9)
- `def first_transition_subq(statuses)` (13)
- `def parsed_in_window(since) -> list` (11)
- `def stats_period_since(period: str) -> datetime | None` (25)

### `backend/repository/stats_kpi.py` — 124 строк

Верхняя строка экрана статистики: пять счётчиков и дельта у каждого.

Зависит от: `backend.models`, `backend.repository.stats_common`, `backend.repository.vacancies_common`

- `async def _ever_in(session: AsyncSession, statuses) -> int` (12)
- `async def _first_in_period(session: AsyncSession, statuses, since: datetime) -> int` (10)
- `async def _kpi_totals(session: AsyncSession) -> dict` (16)
- `async def _kpi_deltas(session: AsyncSession, since: datetime | None) -> dict` (31)
- `async def get_stats_kpi(session: AsyncSession, *, period: str) -> dict` (22)

### `backend/repository/stats_pipeline.py` — 259 строк

Воронка по каналам для экрана статистики.

Зависит от: `backend.domain.funnel`, `backend.domain.verdict`, `backend.models`, `backend.repository.stats_common`, `backend.repository.vacancies_common`

- `def _channel_item(ch_id: int, title: str | None, username: str | None, counts: tuple[int, int, int]=(0, 0, 0)) -> dict` (25)
- `def _trash_predicates()` (26)
- `async def _ingest_by_channel(session: AsyncSession, since) -> list` (18)
- `async def _trash_events_by_channel(session: AsyncSession, since) -> dict[int, int]` (15)
- `async def _first_in_period_by_channel(session: AsyncSession, statuses, since) -> dict[int, set[int]]` (22)
- `async def _funnel_by_channel(session: AsyncSession, since) -> dict[str, dict[int, set[int]]]` (19)
- `async def _channels_without_ingest(session: AsyncSession, missing_ids: set[int]) -> dict[int, dict]` (21)
- `def _pipeline_row(ch_id: int, item: dict, trash_events: int, funnel) -> dict` (39)
  - `def share(stage: str) -> float | None` (4)
- `async def get_stats_channels_pipeline(session: AsyncSession, *, period: str) -> dict` (37)

### `backend/repository/stats_responses.py` — 147 строк

Скорость ответа HR: сколько ждали, кто не ответил и в какие дни пишут.

Зависит от: `backend.domain.funnel`, `backend.models`, `backend.repository.stats_common`, `backend.repository.vacancies_common`

- `async def _applied_in_period(session: AsyncSession, since: datetime | None) -> dict[int, datetime]` (23)
- `async def _first_response_at(session: AsyncSession, applied_map: dict[int, datetime]) -> dict[int, datetime]` (31)
- `def _local_weekday(stamp: datetime) -> int` (8)
- `def _weekdays_and_waits(applied_map: dict[int, datetime], first_resp_by_vid: dict[int, datetime]) -> tuple[list[int], list[float]]` (17)
- `def _median(values: list[float]) -> float | None` (9)
- `async def get_stats_hr_responses(session: AsyncSession, *, period: str) -> dict` (33)

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

### `backend/repository/vacancies_card.py` — 223 строк

Поля одной вакансии.

Зависит от: `backend.models`, `backend.payloads`, `backend.repository.vacancies_life`

- `async def _newest_first(session: AsyncSession, model, stamp, vacancy_id: int) -> list` (20)
- `async def get_vacancy_detail(session: AsyncSession, vacancy_id: int) -> VacancyDetail | None` (29)
- `async def update_vacancy_notes(session: AsyncSession, vacancy_id: int, notes: str | None) -> Vacancy | None` (30)
- `class _Link` (16)
- `async def _link_name(session: AsyncSession, link: _Link, row_id: int | None) -> str | None` (13)
- `async def _relink(session: AsyncSession, vacancy_id: int, new_id: int | None, link: _Link) -> bool` (40)
- `async def set_vacancy_hr(session: AsyncSession, vacancy_id: int, hr_id: int | None) -> bool` (5)
- `async def set_vacancy_company(session: AsyncSession, vacancy_id: int, company_id: int | None) -> bool` (5)

### `backend/repository/vacancies_common.py` — 97 строк

Чтение вакансий, общее для всех экранов.

Зависит от: `backend.models`

- `def by_vacancy_count(label)` (13)
- `def with_vacancy_counts(subject, link, label)` (17)
- `async def count_by_status(session: AsyncSession, *conditions) -> dict[VacancyStatus, int]` (21)

### `backend/repository/vacancies_ghosting.py` — 101 строк

Вакансии, о которых замолчали: срок тишины и гашение по нему.

Зависит от: `backend.domain.transitions`, `backend.models`, `backend.repository.vacancies_activity`, `backend.repository.vacancy_status`

- `async def _silence_candidates(session: AsyncSession)` (29)
- `def _last_activity(vacancy: Vacancy, last_msg_at, entered_at, touched_at)` (10)
- `async def mark_ghosted_vacancies(session: AsyncSession, *, timeout_days: int) -> list[int]` (30)

### `backend/repository/vacancies_life.py` — 150 строк

Что случается с вакансией после того, как её завели, кроме смены статуса.

Зависит от: `backend.models`

- `async def repoint_vacancies(session: AsyncSession, column, *, absorbed_id: int, survivor_id: int | None) -> int` (23)
- `async def record_trash_event(session: AsyncSession, *, source_channel_id: int | None, source_msg_id: int | None, reason: str | None) -> None` (25)
- `async def _trash_noted(session: AsyncSession, source_channel_id: int | None, source_msg_id: int) -> bool` (12)
- `async def delete_vacancy(session: AsyncSession, vacancy_id: int) -> bool` (32)
- `async def add_vacancy_event(session: AsyncSession, vacancy_id: int, kind: str, payload: dict | None=None) -> VacancyEvent` (19)

### `backend/repository/vacancies_list.py` — 451 строк ⚠ подошёл к 300

Отбор вакансий для списка на экране.

Зависит от: `backend.domain.spellings`, `backend.models`, `backend.payloads`, `backend.repository.paging`, `backend.repository.vacancies_activity`, `backend.repository.vacancies_card`, `backend.repository.vacancies_common`

- `def _order_for(sort: str, freshness)` (34)
- `def _like_anywhere(text: str) -> str` (18)
- `def _search_clauses(search: str | None) -> tuple[list, set[str]]` (24)
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

### `backend/repository/vacancies_mini.py` — 121 строк

Короткие списки вакансий для карточек других предметов.

Зависит от: `backend.models`, `backend.repository.hr_card`, `backend.repository.paging`, `backend.repository.vacancies_common`

- `async def _list_linked(session: AsyncSession, linked_to) -> list[Vacancy]` (21)
- `async def list_vacancies_for_hr(session: AsyncSession, hr_id: int) -> list[Vacancy]` (8)
- `async def list_vacancies_for_company(session: AsyncSession, company_id: int) -> list[Vacancy]` (5)
- `async def list_vacancies_for_channel(session: AsyncSession, channel_id: int, *, limit: int=50, offset: int=0) -> tuple[list[Vacancy], bool]` (36)

### `backend/repository/vacancy_status.py` — 371 строк ⚠ подошёл к 300

Смена статуса вакансии: решение, запись, история.

Зависит от: `backend.domain.transitions`, `backend.models`, `backend.payloads`

- `def _ensure_trailing_period(s: str | None) -> str | None` (9)
- `class _Signature` (13)
- `def _move_status(vacancy: Vacancy, new_status: VacancyStatus, sign: _Signature) -> VacancyStatusHistory` (34)
- `async def mark_vacancy_applied(session: AsyncSession, vacancy_id: int, explanation: str | None, *, force: bool) -> bool` (24)
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

### `backend/runtime_settings.py` — 492 строк ⚠ подошёл к 300

Runtime settings layer.

Зависит от: `adapters`, `backend.crypto`, `backend.models`

- `def mask_phone(phone: str | None) -> str` (10)
- `class TgAccountConfig` (7)
- `class LlmProviderConfig` (5)
- `def _log_tg_updated(api_id: int, phone: str, password: str, session_string: str | None) -> None` (16)
- `async def _tg_row(session: AsyncSession) -> TgAccount | None` (3)
- `async def _llm_row(session: AsyncSession, kind: LlmConfigKind) -> LlmConfig | None` (5)
- `class RuntimeSettings` (310)
  - `async def load(cls, session_factory: async_sessionmaker[AsyncSession]) -> 'RuntimeSettings'` (6)
  - `async def reload(self) -> None` (22)
  - `def tg(self) -> TgAccountConfig | None` (2)
  - `def has_tg_session(self) -> bool` (10)
  - `def chat(self) -> LlmProviderConfig | None` (2)
  - `def embed(self) -> LlmProviderConfig | None` (2)
  - `def scoring_threshold(self) -> int` (2)
  - `def poll_interval_sec(self) -> int` (2)
  - `def backfill_limit(self) -> int` (3)
  - `def dedup_cosine_threshold(self) -> float` (8)
  - `def dm_backfill_limit(self) -> int` (6)
  - `def cv_path(self) -> str` (2)
  - `def wizard_completed(self) -> bool` (2)
  - `def send_locked(self) -> bool` (7)
  - `def auto_apply(self) -> bool` (5)
  - `def flood_wait_until_ts(self) -> float` (2)
  - `def _app_bool(self, key: str) -> bool` (9)
  - `def _app_float(self, key: str) -> float` (17)
    - `def read(raw: str) -> float | None` (6)
  - `def _app_int(self, key: str, *, minimum: int | None=None) -> int` (15)
    - `def read(raw: str) -> int | None` (6)
  - `def _app_number(self, key: str, read: Callable, kind: type)` (17)
  - `def _app_value(self, key: str) -> str` (8)
  - `async def set_tg(self, creds: TgAccountConfig) -> None` (30)
  - `async def clear_tg(self) -> None` (12)
  - `async def set_chat(self, *, base_url: str, api_key: str, model: str) -> None` (4)
  - `async def set_embed(self, *, base_url: str, api_key: str, model: str) -> None` (4)
  - `async def _set_llm(self, kind: LlmConfigKind, base_url: str, api_key: str, model: str) -> None` (32)
  - `async def set_app(self, key: str, value: str) -> None` (22)
  - `async def mark_wizard_completed(self) -> None` (3)
- `def _from_tg_row(row: TgAccount) -> TgAccountConfig | None` (30)
- `def _from_llm_row(row: LlmConfig) -> LlmProviderConfig | None` (18)

### `backend/single_instance.py` — 99 строк

Замок, которым запущенная копия приложения не пускает вторую.

Зависит от: —

- `def release_the_lock() -> None` (15)
- `def _take_the_lock(fd: int) -> bool` (23)
- `def hold_the_only_copy(lock_path: Path | str)` (38)

### `backend/telegram_login.py` — 332 строк ⚠ подошёл к 300

Вход в Telegram по коду: четыре шага и состояние между ними.

Зависит от: `backend.runtime_settings`

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

### `backend/telegram_lookup.py` — 107 строк

Что берётся у Telegram по дороге, а не ради самого похода.

Зависит от: `backend.domain.telegram_identity`

- `async def read_channel_metadata(client, chat, *, current_avatar: bytes | None=None) -> tuple[str | None, bytes | None]` (20)
- `async def _quietly(what: str, asking)` (26)
- `async def fetch_telegram_avatar(client, entity) -> bytes | None` (21)
- `async def resolve_hr_telegram(client, hr_contact: str)` (12)

### `backend/telegram_time.py` — 31 строк

Время сообщения Telegram в той шкале, в какой приложение пишет всё остальное.

Зависит от: —

- `def tg_moment(dt: datetime | None) -> datetime | None` (15)

### `backend/wipe.py` — 103 строк

Снос всего, что приложение записало на диск.

Зависит от: `backend.single_instance`, `config`

- `def _close_log_files() -> list[str]` (20)
- `def _remove_the_data() -> list[str]` (27)
- `async def wipe_all(engine) -> list[str]` (28)

## client — 43 модулей

### `client/bridge/__init__.py` — 23 строк

Поверхность моста, доступная окну: дерево доменов и мотор под ним.

Зависит от: `client.bridge.api`, `client.bridge.runner`

Отдаёт наружу: `Api`, `AsyncRunner`


### `client/bridge/answer.py` — 171 строк

Единый конверт ответа окну — от исхода работы до ответа зовущему.

Зависит от: `client.bridge.events`, `client.bridge.payload`, `client.bridge.runner`

- `class Denied(Exception)` (12)
- `def denied(reason: str, **extra: Any) -> dict` (8)
- `def bad_fields(where: str, error: Exception, **extra: Any) -> dict` (20)
- `def reply(runner: AsyncRunner, coro: Coroutine[Any, Any, Any]) -> dict` (33)
- `def launched(hub, work: Callable[[], Coroutine[Any, Any, str]], refusals: dict[str, str], done: str, **started: Any) -> dict` (39)
  - `async def report() -> None` (10)
- `def finished(events: Events, status: str, refusals: dict[str, str], done: str) -> None` (19)

### `client/bridge/api.py` — 39 строк

Поверхность окна: домены, собранные в одно дерево.

Зависит от: `client.bridge.blacklist`, `client.bridge.channels`, `client.bridge.companies`, `client.bridge.hr`, `client.bridge.hub`, `client.bridge.profile`, `client.bridge.settings`, `client.bridge.stats`, `client.bridge.system`, `client.bridge.vacancies`, `client.bridge.wizard`

- `class Api` (14)

### `client/bridge/blacklist.py` — 171 строк

Экран «Контакты / Чёрный список»: чем окно правит отсев.

Зависит от: `backend.models`, `backend.repository`, `client.bridge.answer`, `client.bridge.form_payloads`, `client.bridge.hub`, `client.bridge.refusals`, `client.bridge.wire`

- `class Blacklist` (158)
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
  - `def set_active(self, payload: dict) -> dict` (33)
    - `async def run() -> dict` (12)

### `client/bridge/bot_stop.py` — 90 строк

Остановка бота: попросить и дождаться.

Зависит от: —

- `def detach_bot(hub) -> tuple[object | None, Future | None]` (10)
- `async def stop_bot(bot, bot_task: Future | None, asking: Callable[[], Awaitable[None]] | None=None, timeout: float=STOP_TIMEOUT_S) -> bool` (41)

### `client/bridge/channel_actions.py` — 251 строк

Что окно делает с каналом: опрос, курсор, чёрный список, состав.

Зависит от: `backend.domain.telegram_identity`, `backend.repository`, `client.bridge.answer`, `client.bridge.form_payloads`, `client.bridge.mark`, `client.bridge.refusals`

- `class ChannelActions` (239)
  - `def block(self, channel_id: int) -> dict` (16)
    - `async def run() -> dict` (5)
  - `def unblock(self, channel_id: int) -> dict` (14)
    - `async def run() -> dict` (5)
  - `def poll_now(self, channel_id: int) -> dict` (19)
  - `def reset_cursor(self, channel_id: int) -> dict` (22)
    - `async def run() -> dict` (9)
  - `def delete(self, channel_id: int) -> dict` (21)
    - `async def run() -> dict` (12)
  - `def create(self, payload: dict | None=None) -> dict` (46)
    - `async def run() -> dict` (23)
  - `def set_active(self, payload: dict) -> dict` (24)
  - `async def _switched(self, channel_id: int, is_active: bool) -> dict` (31)
  - `def set_all_active(self, payload: dict) -> dict` (26)
    - `async def run() -> dict` (11)

### `client/bridge/channels.py` — 140 строк

Экран «Контакты / Каналы»: список каналов и их карточка.

Зависит от: `backend.incoming`, `backend.models`, `backend.repository`, `client.bridge.answer`, `client.bridge.channel_actions`, `client.bridge.hub`, `client.bridge.media`, `client.bridge.page`, `client.bridge.refusals`, `client.bridge.wire`

- `class Channels(ChannelActions)` (117)
  - `def list(self, payload: dict | None=None) -> dict` (28)
    - `async def run() -> dict` (15)
  - `def detail(self, channel_id: int) -> dict` (33)
    - `async def run() -> dict` (23)
  - `def vacancies(self, payload: dict) -> dict` (13)
  - `async def _paged(self, channel_id: int, page: Page) -> dict` (27)

### `client/bridge/choices.py` — 46 строк

Просеивание значений, пришедших из окна, по известному набору.

Зависит от: `backend.domain.taxonomy`

- `def _filter_set(values, allowed: tuple[str, ...]) -> list[str]` (6)
- `def _filter_languages(items) -> list[tuple[str, str]]` (31)

### `client/bridge/companies.py` — 335 строк ⚠ подошёл к 300

Компания как запись в контактах: найти, показать, поправить, убрать.

Зависит от: `backend.incoming`, `backend.repository`, `client.bridge.answer`, `client.bridge.form_payloads`, `client.bridge.hub`, `client.bridge.mark`, `client.bridge.page`, `client.bridge.pickers`, `client.bridge.refusals`, `client.bridge.wire`

- `async def create_company_row(session, fields: dict, **echo) -> int` (25)
- `class Companies` (276)
  - `def list(self, payload: dict | None=None) -> dict` (23)
    - `async def run() -> dict` (10)
  - `def detail(self, company_id: int) -> dict` (24)
    - `async def run() -> dict` (15)
  - `def vacancies(self, payload: dict) -> dict` (21)
    - `async def run() -> dict` (9)
  - `def people(self, company_id: int) -> dict` (16)
    - `async def run() -> dict` (7)
  - `def merge_picker(self, payload: dict) -> dict` (17)
    - `async def run() -> dict` (3)
  - `def merge(self, payload: dict) -> dict` (31)
    - `async def run() -> dict` (16)
  - `def create(self, payload: dict) -> dict` (21)
    - `async def run() -> dict` (6)
  - `def update(self, payload: dict) -> dict` (26)
  - `async def _updated(self, company_id: int, kwargs: dict) -> dict` (29)
  - `def delete(self, company_id: int) -> dict` (13)
    - `async def run() -> dict` (8)
  - `def block(self, company_id: int) -> dict` (18)
    - `async def run() -> dict` (5)
  - `def unblock(self, company_id: int) -> dict` (15)
    - `async def run() -> dict` (5)

### `client/bridge/cv.py` — 75 строк

Файл резюме, на который смотрит окно: запомнить путь, открыть.

Зависит от: `client.bridge.answer`, `client.bridge.cv_file`, `client.bridge.desktop`

- `class Cv` (62)
  - `def pick(self) -> dict` (18)
  - `def replace(self, payload: dict) -> dict` (12)
    - `async def run() -> dict` (3)
  - `def open(self) -> dict` (15)

### `client/bridge/cv_file.py` — 16 строк

Что можно узнать о файле резюме с диска.

Зависит от: —

- `def _stat_cv(cv_path: str) -> dict | None` (9)

### `client/bridge/desktop.py` — 159 строк

Просьбы окна к рабочему столу: открыть названное тем, чем открывает система.

Зависит от: `client.bridge.answer`, `client.bridge.media`, `client.bridge.refusals`

- `def _scheme_of(url: str) -> str` (7)
- `def open_in_system(target: str) -> bool` (20)
- `class Desktop` (65)
  - `def open_url(self, url: str) -> dict` (28)
  - `def open_attachment(self, url: str) -> dict` (23)

### `client/bridge/events.py` — 149 строк

Живые события окна: копит случившееся с номерами и отдаёт всё новее названного.

Зависит от: —

- `class Events` (83)
  - `def add(self, kind: str, payload: dict | None=None) -> None` (10)
  - `async def take(self, after: int | None, timeout: float=WAIT_SECONDS) -> dict` (38)
  - `def close(self) -> None` (6)
  - `def _since(self, after: int) -> dict` (15)
- `def _wake(waiters: list[tuple[asyncio.AbstractEventLoop, asyncio.Future]]) -> None` (6)
- `def _finish(waiter: asyncio.Future) -> None` (3)

### `client/bridge/form_payloads.py` — 115 строк

Поля записи, прочитанные из нагрузки форм окна.

Зависит от: `backend.domain.telegram_identity`, `backend.incoming`

- `def read_toggle(payload: dict, id_key: str, flag_key: str) -> tuple[int | None, bool | None]` (18)
- `def read_company_spellings(raw) -> list[str]` (16)
- `def read_new_company_fields(payload: dict) -> dict` (16)
- `def hr_is_identified(fields: dict) -> bool` (11)
- `def read_new_hr_fields(payload: dict) -> dict` (31)

### `client/bridge/hr.py` — 299 строк

Экран «Контакты / HR»: список людей, их карточка и правки в ней.

Зависит от: `backend.incoming`, `backend.repository`, `client.bridge.answer`, `client.bridge.form_payloads`, `client.bridge.hr_chat`, `client.bridge.hub`, `client.bridge.mark`, `client.bridge.media`, `client.bridge.page`, `client.bridge.pickers`, `client.bridge.refusals`, `client.bridge.wire`

- `async def create_hr_row(session, fields: dict, **echo) -> int` (15)
- `class Hr(HrChat)` (259)
  - `def list(self, payload: dict | None=None) -> dict` (28)
    - `async def run() -> dict` (14)
  - `def detail(self, hr_id: int) -> dict` (27)
    - `async def run() -> dict` (18)
  - `def vacancies(self, payload: dict) -> dict` (19)
    - `async def run() -> dict` (7)
  - `def merge_picker(self, payload: dict) -> dict` (17)
    - `async def run() -> dict` (3)
  - `def merge(self, payload: dict) -> dict` (32)
    - `async def run() -> dict` (18)
  - `def delete(self, hr_id: int) -> dict` (13)
    - `async def run() -> dict` (8)
  - `def block(self, hr_id: int) -> dict` (21)
    - `async def run() -> dict` (5)
  - `def unblock(self, hr_id: int) -> dict` (15)
    - `async def run() -> dict` (5)
  - `def update(self, payload: dict) -> dict` (40)
    - `async def run() -> dict` (14)
  - `def create(self, payload: dict) -> dict` (20)
    - `async def run() -> dict` (4)

### `client/bridge/hr_chat.py` — 160 строк

Переписка с человеком: страница сообщений, отправка, прочтение.

Зависит от: `backend.bot.chat`, `backend.incoming`, `backend.repository`, `client.bridge.answer`, `client.bridge.refusals`, `client.bridge.wire`

- `class HrChat` (146)
  - `def messages(self, payload: dict) -> dict` (23)
  - `async def _paged(self, asked: dict, before_sent_at) -> dict` (17)
  - `def mark_read(self, hr_id: int) -> dict` (19)
    - `async def run() -> dict` (10)
  - `def send_message(self, payload: dict) -> dict` (28)
    - `async def run() -> dict` (9)
  - `def pick_media(self, hr_id: int) -> dict` (20)
  - `def _send_media(self, payload: dict) -> dict` (24)
    - `async def run() -> dict` (9)

### `client/bridge/hub.py` — 55 строк

Живое хозяйство окна: то, из чего собран каждый домен поверхности.

Зависит от: `client.bridge.events`

- `class Hub` (38)

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

### `client/bridge/lifespan.py` — 295 строк

Жизнь моста при окне: от подъёма хозяйства до его гашения.

Зависит от: `backend.bot.client`, `backend.telegram_login`, `client.bridge.bot_stop`, `client.bridge.hub`, `client.bridge.journal`

- `def start(runner, session_factory, rs, engine=None) -> Hub` (20)
- `def stop(hub: Hub) -> None` (35)
- `def start_bot(hub: Hub) -> None` (28)
- `def _ready_for_bot(rs) -> bool` (9)
- `def _forget_login(hub: Hub) -> None` (14)
- `def _start_bot(hub: Hub) -> None` (25)
  - `async def _build_and_run() -> None` (8)
- `def _tell_the_window(bot, hub: Hub) -> None` (36)
  - `def arrived(hr_id: int) -> None` (3)
- `def _restart_bot(hub: Hub) -> None` (36)
  - `async def _swap() -> None` (15)
- `def _remember_login(hub: Hub, username: str | None) -> None` (17)
- `def _log_if_crashed(hub: Hub, future: Future) -> None` (20)

### `client/bridge/llm.py` — 202 строк

Разговор с поставщиком модели: проба связи и опрос имён.

Зависит от: `adapters`, `adapters.lm_studio`, `backend.log_secrets`, `client.bridge.answer`, `client.bridge.refusals`

- `def _client_or_reason(cfg: LlmProviderConfig) -> tuple[httpx.AsyncClient | None, str]` (16)
- `async def _do_list_models_for_creds(base_url: str, api_key: str, *, kind: str | None=None) -> dict` (28)
- `async def _do_llm_probe(cfg: LlmProviderConfig, check_fn: Callable[[httpx.AsyncClient, str], Any]) -> tuple[bool, str, list[str], int]` (27)
- `def read_llm_creds(payload: dict) -> LlmProviderConfig` (20)
- `def read_models_ask(payload) -> tuple[str, str, str]` (4)
- `def _provider_address(payload: dict) -> tuple[str, str]` (14)
- `class Llm` (61)
  - `def probe_model(self, payload: dict) -> dict` (29)
    - `async def run() -> dict` (5)
  - `def list_models(self, payload: dict) -> dict` (23)
    - `async def run() -> dict` (7)

### `client/bridge/login.py` — 131 строк

Вход в Telegram: три шага, общие основному окну и мастеру.

Зависит от: `backend.telegram_login`, `client.bridge.answer`, `client.bridge.refusals`

- `def read_credentials(payload: dict) -> tuple[int, str, str]` (12)
- `def read_code(payload: dict) -> str` (3)
- `def read_password(payload: dict) -> str` (7)
- `async def code_step(login, code: str) -> LoginStep` (10)
- `async def password_step(login, password: str) -> LoginStep` (10)
- `async def step_payload(step_coro) -> dict` (11)
- `class Login` (57)
  - `def send_code(self, payload: dict) -> dict` (18)
  - `def confirm_code(self, payload: dict) -> dict` (10)
  - `def confirm_password(self, payload: dict) -> dict` (10)

### `client/bridge/mark.py` — 127 строк

Отметка предмета в чёрном списке, поставленная из его карточки.

Зависит от: `backend.models`, `backend.repository`, `backend.repository.blacklist_marks`, `client.bridge.answer`, `client.bridge.refusals`

- `class MarkSubject` (9)
- `async def mark(session, subject: MarkSubject, entity_id: int) -> dict` (27)
- `async def unmark(session, subject: MarkSubject, entity_id: int) -> dict` (24)

### `client/bridge/media.py` — 69 строк

Вложение письма, каким его видит окно: адрес разметки и файл за адресом.

Зависит от: `backend.bot.media`, `client.serving`

- `def _media_url(stored_path: str | None) -> str | None` (19)
- `def media_file(url: str) -> Path | None` (11)
- `def _under_media(stored_path: str) -> str | None` (14)
- `def _avatar_data_url(blob: bytes | None) -> str | None` (9)

### `client/bridge/page.py` — 77 строк

Страница списка, прочитанная из нагрузки окна.

Зависит от: `backend.incoming`

- `class Page` (5)
- `def read_page(payload: dict, *, default_limit: int | None=None) -> Page` (32)

### `client/bridge/payload.py` — 18 строк

Жалоба в журнал на негодную нагрузку, пришедшую из окна.

Зависит от: —

- `def _log_invalid_payload(slot: str, exc: Exception) -> None` (8)

### `client/bridge/pickers.py` — 103 строк

Списки кандидатов, которые окно показывает в модалке выбора.

Зависит от: `backend.repository`, `client.bridge.wire`

- `class PickerSubject` (15)
- `async def merge_picker(session, subject: PickerSubject, absorbed_id: int, search: str | None) -> dict` (21)
- `async def link_picker(session, subject: PickerSubject, vacancy, search: str | None) -> dict` (18)

### `client/bridge/profile.py` — 163 строк

Анкета соискателя: сведения о себе, навыки и места работы.

Зависит от: `backend.domain.taxonomy`, `backend.incoming`, `backend.repository`, `client.bridge.answer`, `client.bridge.choices`, `client.bridge.cv`, `client.bridge.cv_file`, `client.bridge.hub`, `client.bridge.refusals`, `client.bridge.wire`

- `class Profile(Cv)` (123)
  - `def get(self) -> dict` (19)
    - `async def run() -> dict` (14)
  - `def save(self, payload: dict) -> dict` (22)
    - `async def run() -> dict` (8)
  - `def skills(self) -> dict` (9)
    - `async def run() -> dict` (4)
  - `def save_skills(self, payload: dict) -> dict` (3)
  - `def experience(self) -> dict` (17)
    - `async def run() -> dict` (8)
  - `def save_experience(self, payload: dict) -> dict` (3)
  - `def _save_rows(self, payload: dict, key: str, saving) -> dict` (29)
    - `async def run() -> dict` (11)
- `def _read_profile_fields(payload: dict) -> dict` (16)

### `client/bridge/refusals.py` — 161 строк

Слова, которыми мост отказывает окну.

Зависит от: —


### `client/bridge/runner.py` — 92 строк

Цикл asyncio в своём потоке, куда поверхность окна отправляет работу.

Зависит от: —

- `class AsyncRunner` (77)
  - `def _run_loop(self) -> None` (38)
    - `def _quiet_pyrogram_shutdown(loop, context)` (26)
  - `def submit(self, coro: Coroutine[Any, Any, Any]) -> Future` (2)
  - `def stop(self) -> None` (24)
    - `async def _cancel_pending() -> None` (5)

### `client/bridge/settings.py` — 290 строк

Экран «Настройки»: всё, что окно спрашивает и правит на нём.

Зависит от: `adapters.lm_studio`, `backend.telegram_login`, `client.bridge.answer`, `client.bridge.bot_stop`, `client.bridge.hub`, `client.bridge.llm`, `client.bridge.login`, `client.bridge.wire`

- `class Settings(Login, Llm)` (192)
  - `def get(self) -> dict` (29)
    - `async def run() -> dict` (20)
  - `def save(self, payload: dict | None=None) -> dict` (34)
    - `async def run() -> dict` (12)
  - `def logout(self) -> dict` (36)
    - `async def run() -> dict` (17)
  - `def cancel_login(self) -> dict` (18)
    - `async def run() -> dict` (3)
  - `async def _username(self) -> str` (22)
  - `async def _apply_providers(self, creds: dict[str, LlmProviderConfig]) -> list[str]` (10)
  - `async def _apply_app(self, app: dict, applied: list[str]) -> None` (20)
- `def _check_logout_without_bot(has_session: bool) -> None` (19)
- `async def _wait_connected(client) -> None` (8)
- `def _read_providers(payload: dict) -> dict[str, LlmProviderConfig]` (21)

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

### `client/bridge/system.py` — 307 строк ⚠ подошёл к 300

Домен «система»: то, чем страница живёт на любом экране.

Зависит от: `backend`, `backend.incoming`, `backend.models`, `backend.repository`, `backend.repository.bot_mode`, `client.bridge.answer`, `client.bridge.desktop`, `client.bridge.hub`, `client.bridge.journal`, `client.bridge.refusals`, `client.bridge.wipe`

- `class System(Journal, Wipe, Desktop)` (219)
  - `def initial(self) -> dict` (16)
    - `async def run() -> dict` (6)
  - `async def _mode(self) -> BotMode` (5)
  - `def set_mode(self, mode: str) -> dict` (26)
    - `async def run() -> dict` (7)
  - `def run_now(self) -> dict` (19)
  - `def stop_run(self) -> dict` (15)
    - `async def run() -> dict` (6)
  - `def unread_chats(self) -> dict` (13)
    - `async def run() -> dict` (4)
  - `def events(self, after) -> dict` (15)
  - `def health(self) -> dict` (3)
  - `def unread(self) -> dict` (3)
  - `async def _health(self) -> dict` (18)
  - `async def _unread(self) -> dict` (4)
  - `async def _models_alive(self) -> tuple[bool, bool]` (34)
  - `async def _probe_models(self) -> None` (6)
  - `async def _ask_models(self) -> tuple[bool, bool]` (5)
- `def _probed(task: Future) -> None` (16)
- `def _after(asked) -> int | None` (21)

### `client/bridge/vacancies.py` — 237 строк

Экран «Вакансии»: список, карточка и правки в них.

Зависит от: `backend.domain.scoring`, `backend.models`, `backend.repository`, `client.bridge.answer`, `client.bridge.hub`, `client.bridge.page`, `client.bridge.refusals`, `client.bridge.vacancy_actions`, `client.bridge.vacancy_filter`, `client.bridge.vacancy_links`, `client.bridge.wire`

- `def _typed_text(raw) -> str | None` (8)
- `class Vacancies(VacancyActions, VacancyLinks)` (200)
  - `def list(self, payload: dict | None=None) -> dict` (15)
  - `def filter_options(self) -> dict` (19)
    - `async def run() -> dict` (4)
  - `async def _listed(self, filters) -> dict` (15)
  - `def detail(self, vacancy_id) -> dict` (31)
    - `async def run() -> dict` (13)
  - `def save_notes(self, payload: dict) -> dict` (25)
    - `async def run() -> dict` (10)
  - `def save_history_explanation(self, payload: dict) -> dict` (38)
    - `async def run() -> dict` (21)
  - `def change_status(self, payload: dict) -> dict` (35)
    - `async def run() -> dict` (16)

### `client/bridge/vacancy_actions.py` — 113 строк

Действия над вакансией: перезапуск разбора, отклик, удаление.

Зависит от: `backend.repository`, `client.bridge.answer`, `client.bridge.refusals`

- `def _asked_vacancy(payload: dict, slot: str) -> tuple[int | None, dict | None]` (12)
- `class VacancyActions` (80)
  - `def rerun(self, payload: dict) -> dict` (24)
  - `def send_application(self, payload: dict) -> dict` (26)
    - `async def sending() -> str` (3)
  - `def delete(self, payload: dict) -> dict` (22)
    - `async def run() -> dict` (14)

### `client/bridge/vacancy_filter.py` — 55 строк

Отбор списка вакансий, прочитанный из нагрузки окна.

Зависит от: `backend.incoming`, `backend.payloads`, `client.bridge.page`

- `def read_vacancy_filter(payload: dict, page: Page) -> VacancyFilter` (34)

### `client/bridge/vacancy_links.py` — 194 строк

Привязка вакансии к человеку и к компании: подборщики и их правки.

Зависит от: `backend.incoming`, `backend.models`, `backend.repository`, `client.bridge.answer`, `client.bridge.companies`, `client.bridge.form_payloads`, `client.bridge.hr`, `client.bridge.pickers`, `client.bridge.refusals`

- `class VacancyLinks` (140)
  - `def hr_picker(self, payload: dict) -> dict` (8)
  - `def company_picker(self, payload: dict) -> dict` (3)
  - `def _open_picker(self, slot: str, payload: dict) -> dict` (11)
  - `def link_hr(self, payload: dict) -> dict` (7)
  - `def link_company(self, payload: dict) -> dict` (3)
  - `def _link(self, slot: str, payload: dict) -> dict` (15)
    - `async def run() -> dict` (3)
  - `def create_hr(self, payload: dict) -> dict` (7)
  - `def create_company(self, payload: dict) -> dict` (3)
  - `def _created(self, slot: str, payload: dict) -> dict` (26)
    - `async def run() -> dict` (5)
  - `async def _picker(self, kind, vacancy_id: int, search: str | None) -> dict` (6)
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

### `client/bridge/wire.py` — 388 строк ⚠ подошёл к 300

Перевод внутренних значений в словари, которые читает окно.

Зависит от: `backend.domain.skill_names`, `backend.models`, `client.bridge.media`

- `def _iso(dt: datetime | None) -> str | None` (17)
- `def _vacancy_mini_row_to_dict(v) -> dict` (20)
- `def _tg_creds_to_dict(tg) -> dict` (20)
- `def _llm_provider_to_dict(cfg) -> dict` (19)
- `def _profile_to_dict(p, languages=None) -> dict | None` (22)
- `def _skill_to_dict(s) -> dict` (8)
- `def _exp_to_dict(e) -> dict` (12)
- `def _stack_items(stack, matched_set: set[str]) -> list[dict]` (8)
- `def _company_name(v) -> str | None` (12)
- `def _hr_face(hr) -> dict` (13)
- `def _status_change(row) -> dict` (15)
- `def _vacancy_event(row) -> dict` (8)
- `def _vacancy_detail_to_dict(detail, matched_set: set[str], score_threshold: int) -> dict` (39)
- `def _hr_picker_row_to_dict(item) -> dict` (18)
- `def _hr_mini_row_to_dict(hr, vacancy_count: int) -> dict` (11)
- `def _message_row_to_dict(m) -> dict` (19)
- `def _blacklist_row_to_dict(row: Blacklist) -> dict` (14)
- `def _channel_row_to_dict(item) -> dict` (15)
- `def _company_picker_row_to_dict(item) -> dict` (14)
- `def _vacancy_list_row_to_dict(v, matched_set: set[str], activity_by_id: dict[int, Any] | None=None) -> dict` (34)

### `client/bridge/wizard.py` — 124 строк

Порядок первого запуска: чем он продолжается и когда он кончен.

Зависит от: `client.bridge.answer`, `client.bridge.hub`, `client.bridge.lifespan`, `client.bridge.wire`, `client.window_size`

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

### `client/window.py` — 222 строк

Окно приложения: как оно открывается и чем гасится.

Зависит от: `adapters`, `adapters.telegram`, `backend.bot.media`, `backend.models`, `backend.repository.bot_mode`, `backend.runtime_settings`, `client`, `client.bridge`, `client.serving`, `config`

- `def run_ui() -> int` (32)
- `def _open_window(hub, *, settled: bool)` (19)
- `def _put_out(hub, runner, listening) -> None` (20)
- `async def prepare(session_factory) -> RuntimeSettings` (12)
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

## tests — 235 модулей

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


### `tests/adapters/test_lm_studio.py` — 26 строк

Следствия соединения с провайдером моделей.

Зависит от: `adapters.lm_studio`, `backend.runtime_settings`

Тестов: 3


### `tests/backend/conftest.py` — 51 строк

Фикстуры слоя `backend`, собранные из модулей по предметам.

Зависит от: `tests.backend.fixtures.backfill`, `tests.backend.fixtures.bot`, `tests.backend.fixtures.flows`, `tests.backend.fixtures.listing`, `tests.backend.fixtures.logs`, `tests.backend.fixtures.rerun`, `tests.backend.fixtures.stats`

Отдаёт наружу: `applied`, `busy_slot`, `channel_titles`, `chatting`, `clean_root_logger`, `deliver`, `dm_pipeline`, `empty_media_dir`, `hr_names`, `known_hr`, `make_bot`, `make_pipeline`, `outbox`, `parsing`, `ready_to_send`, `rerunning`, `sending_unlocked`, `titles`, `unparsed_vacancy`


### `tests/backend/fixtures/__init__.py` — 1 строк

Обстановка для проверок слоя `backend`, разложенная по предметам.

Зависит от: —


### `tests/backend/fixtures/backfill.py` — 72 строк

Обстановка для проверок догона переписки: собеседник и прогон догона.

Зависит от: `backend.flows.dm`, `backend.flows.dm_backfill`, `backend.models`, `tests.dbio`, `tests.factories`, `tests.fakes.telegram`

- `def theirs(msg_id, text)` (3)
- `def ours(msg_id, text, *, photo=None)` (3)
- `def _helpers(client, session_factory, **extra) -> DmHelpers` (14)
- `async def catch_up(client, hr, session_factory, *, hooks=None, **kwargs)` (9)
- `async def catch_up_everyone(client, session_factory, *, hooks=None, **kwargs)` (12)
- `async def known_hr(session_factory)` (4)

### `tests/backend/fixtures/bot.py` — 237 строк

Обстановка для проверок бота: всё собрано на подделках, до сети не доходит.

Зависит от: `adapters.telegram`, `backend.bot.client`, `backend.bot.media`, `backend.crypto`, `backend.models`, `backend.repository.bot_mode`, `backend.runtime_settings`, `tests.dbio`, `tests.factories`, `tests.fakes.lm_studio`, `tests.fakes.telegram`

- `class Outbox` (18)
  - `async def send_dm(self, _client, target, text, attachment=None)` (5)
- `def row_saved_mid_send(session_factory, hr_id)` (20)
  - `async def save(answer) -> None` (10)
- `async def _switch_to(session_factory, mode: BotMode) -> None` (5)
- `def make_bot(session_factory, monkeypatch)` (40)
  - `async def build(client=None, *, embed_url='http://provider.test') -> Bot` (17)
- `def empty_media_dir()` (13)
- `def chatting(session_factory, make_bot)` (17)
  - `async def build(*, mode=BotMode.FULL, client=None, **hr_fields)` (6)
- `async def busy_slot()` (20)
  - `def occupy(bot) -> None` (4)
- `def sending_unlocked(monkeypatch)` (10)
- `def outbox(monkeypatch, sending_unlocked)` (11)
- `def ready_to_send(session_factory, make_bot)` (24)
  - `async def build(*, status=VacancyStatus.NEW, mode=BotMode.FULL, hr=None)` (13)

### `tests/backend/fixtures/flows.py` — 223 строк

Обстановка для проверок конвейера: он собран на подделках, модель молчит.

Зависит от: `backend.flows`, `backend.flows.dm`, `backend.flows.pipeline`, `backend.models`, `backend.payloads`, `backend.runtime_settings`, `tests.dbio`, `tests.factories`, `tests.fakes.lm_studio`, `tests.fakes.telegram`

- `def known_hr_client() -> FakeTelegramClient` (13)
- `def _pipeline_on_fakes(session_factory, client, settings) -> IngestionPipeline` (22)
  - `async def send(hr, text, attachment=None, vacancy_id=None, *, force=False)` (3)
- `async def _put_out_backfills(pipelines) -> None` (12)
- `def _answer_instead_of_the_model(pipeline, monkeypatch) -> None` (17)
  - `async def parse_vacancy(text, client_, model, **kwargs)` (2)
  - `async def validate_vacancy_fit(parsed, text, client_, model, **kwargs)` (3)
  - `async def try_auto_send(pipeline, hr, parsed, vacancy_id)` (3)
- `async def make_pipeline(session_factory)` (24)
  - `async def build(client=None)` (7)
- `def deliver(session_factory)` (20)
  - `async def run(msg, *, client=None, schedule=None)` (10)
- `async def unparsed_vacancy(session_factory)` (17)
- `async def parsing(make_pipeline, monkeypatch, unparsed_vacancy, session_factory)` (31)
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

### `tests/backend/fixtures/logs.py` — 28 строк

Возврат корневого логгера в состояние, в котором его застали.

Зависит от: —

- `def clean_root_logger()` (20)

### `tests/backend/fixtures/rerun.py` — 75 строк

Обстановка для проверок повторного прогона вакансии.

Зависит от: `backend.flows`, `backend.models`, `tests.dbio`, `tests.factories`, `tests.fakes.telegram`

- `class WithMessages(FakeTelegramClient)` (14)
  - `async def get_messages(self, chat_id, message_ids=None)` (5)
- `async def rerunning(make_pipeline, session_factory)` (15)
- `async def prepare(monkeypatch, make_pipeline, client)` (24)
  - `async def parse(pipeline, vacancy_id, text, username, allow_delete=False)` (3)
  - `async def reload()` (2)
  - `async def embed(pipeline, text, what)` (3)

### `tests/backend/fixtures/stats.py` — 52 строк

Обстановка для проверок сводки: отклик и ответ на него.

Зависит от: `backend.models`, `tests.dbio`, `tests.factories`

- `def applied(session_factory)` (42)
  - `async def build(applied_at, *, hr=None, answered_after=None, **overrides)` (19)

### `tests/backend/test_adapters_teletype.py` — 173 строк

Следствия, которые наблюдают тесты `adapters/teletype.py`.

Зависит от: `adapters`

Тестов: 8

- `def _page(*, headline: str='Senior Manual QA', body: str='<p>Ищем QA</p>') -> str` (8)
- `def _client(handler) -> httpx.AsyncClient` (3)

### `tests/backend/test_bootstrap_schema.py` — 133 строк

Следствия подготовки схемы базы при запуске.

Зависит от: `alembic`, `backend.bootstrap`, `tests.conftest`

Тестов: 2

- `def _tables(db_file) -> set[str]` (9)
- `def _revision_reached(db_file) -> str` (6)
- `def _project_of_two_revisions(root, db_file) -> None` (20)

### `tests/backend/test_bot_channel_writes.py` — 48 строк

Следствия удаления канала кнопкой окна.

Зависит от: `backend.models`, `tests.dbio`, `tests.factories`

Тестов: 2


### `tests/backend/test_bot_channels.py` — 183 строк

Следствия добавления канала из окна настроек.

Зависит от: `backend.models`, `tests.dbio`, `tests.factories`, `tests.fakes.telegram`

Тестов: 10


### `tests/backend/test_bot_chat_media.py` — 272 строк

Следствия отправки файла HR из вкладки «Контакты».

Зависит от: `backend.bot.media`, `backend.models`, `tests.backend.fixtures.bot`, `tests.dbio`, `tests.factories`

Тестов: 14

- `def _file(tmp_path, name: str, size: int=4)` (10)

### `tests/backend/test_bot_chat_send.py` — 187 строк

Следствия отправки сообщения HR из вкладки «Контакты».

Зависит от: `backend.models`, `tests.backend.fixtures.bot`, `tests.dbio`, `tests.factories`

Тестов: 11


### `tests/backend/test_bot_dm_deletes.py` — 414 строк ⚠ подошёл к 300

Следствия удаления сообщения на стороне Telegram.

Зависит от: `backend.models`, `tests.dbio`, `tests.factories`, `tests.fakes.ingestion`, `tests.fakes.telegram`

Тестов: 20

- `def _tombstone(msg_id: int, *, chat_id=777, username=None)` (6)
- `def _deletion_filter(client)` (7)

### `tests/backend/test_bot_dm_edits.py` — 263 строк

Следствия правки сообщения, пришедшей из Telegram.

Зависит от: `backend.models`, `tests.dbio`, `tests.factories`, `tests.fakes.ingestion`, `tests.fakes.telegram`

Тестов: 13

- `def _edit(*, chat_id=777, username=None, msg_id=10, text='новая редакция', mine=False)` (14)

### `tests/backend/test_bot_dm_incoming.py` — 120 строк

Следствия входящего сообщения от HR.

Зависит от: `backend.models`, `tests.fakes.telegram`

Тестов: 6

- `def dm_reader(monkeypatch)` (18)
  - `class Reader(list)` (6)
    - `async def __call__(self, msg, *_args, **_kwargs)` (3)

### `tests/backend/test_bot_dm_outgoing.py` — 318 строк ⚠ подошёл к 300

Следствия сообщения, отправленного HR с телефона или другого клиента.

Зависит от: `backend.models`, `tests.dbio`, `tests.factories`, `tests.fakes.ingestion`, `tests.fakes.telegram`

Тестов: 14

- `def _echo(*, chat_id=777, username=None, msg_id=10, text='ответ с телефона', photo=None)` (9)

### `tests/backend/test_bot_logout.py` — 39 строк

Следствия выхода из учётной записи Telegram.

Зависит от: `tests.fakes.telegram`

Тестов: 2


### `tests/backend/test_bot_media_download.py` — 120 строк

Следствия скачивания вложения из входящего сообщения.

Зависит от: `backend.bot.media`, `tests.fakes.telegram`

Тестов: 8


### `tests/backend/test_bot_media_paths.py` — 147 строк

Следствия выбора способа отправки файла и места для скачанного.

Зависит от: `backend.bot.media`, `tests.factories`, `tests.fakes.telegram`

Тестов: 10


### `tests/backend/test_bot_menu_actions.py` — 160 строк

Следствия команд из меню карточки вакансии.

Зависит от: `tests.fakes.ingestion`

Тестов: 11


### `tests/backend/test_bot_mode_reading.py` — 40 строк

Откуда бот берёт свой режим.

Зависит от: `backend.bot`, `backend.models`, `backend.repository.bot_mode`

Тестов: 2


### `tests/backend/test_bot_poll_slot.py` — 186 строк

Следствия ручного прогона, запущенного кнопкой окна.

Зависит от: `tests.fakes.ingestion`

Тестов: 14


### `tests/backend/test_bot_read_receipts.py` — 391 строк ⚠ подошёл к 300

Следствия отметок о прочтении — своих и чужих.

Зависит от: `backend.models`, `tests.dbio`, `tests.factories`, `tests.fakes.telegram`

Тестов: 22

- `def _outbox_read(user_id: int, max_id: int)` (5)

### `tests/backend/test_bot_run_loop.py` — 408 строк ⚠ подошёл к 300

Следствия одного оборота главного цикла бота.

Зависит от: `backend.bot`, `backend.models`, `tests.fakes.ingestion`, `tests.fakes.telegram`

Тестов: 24

- `def caught_up(monkeypatch)` (9)
  - `async def catch_up_missed_dms(client, *args, **kwargs)` (2)
- `async def _one_turn(chatting, mode, ingestion=None)` (9)

### `tests/backend/test_bot_send_effects.py` — 308 строк ⚠ подошёл к 300

Следы, которые оставляет ушедший отклик.

Зависит от: `backend.models`, `tests.dbio`, `tests.factories`

Тестов: 17


### `tests/backend/test_bot_send_mishaps.py` — 242 строк

Что остаётся после отправки, пошедшей не так.

Зависит от: `backend.models`, `tests.dbio`, `tests.factories`

Тестов: 9

- `class _BrokenCommits` (9)
  - `def __call__(self)` (2)
- `class _BrokenScope` (12)
  - `async def __aenter__(self)` (2)
  - `async def __aexit__(self, *exc)` (2)
- `class _BrokenSession` (15)
  - `def __getattr__(self, name)` (2)
  - `async def commit(self)` (5)

### `tests/backend/test_bot_send_refusals.py` — 124 строк

Случаи, когда отклик не отправляется и не засчитывается.

Зависит от: `backend.bot`, `backend.models`, `tests.dbio`, `tests.factories`

Тестов: 5


### `tests/backend/test_bot_session_string.py` — 84 строк

Следствия сверки строки сессии при запуске.

Зависит от: `backend.bot`, `tests.factories`, `tests.fakes.telegram`

Тестов: 4


### `tests/backend/test_bot_shared_provider.py` — 47 строк

Когда чат и векторы делят одно соединение с языковой моделью.

Зависит от: `backend.bot.send`, `backend.runtime_settings`

Тестов: 1

- `def _provider(base_url='http://a', api_key='ключ', model='qwen')` (3)

### `tests/backend/test_bot_signals.py` — 153 строк

Следствия сигналов, приходящих боту из чужого потока.

Зависит от: —

Тестов: 9

- `def closed_loop()` (5)

### `tests/backend/test_crypto.py` — 117 строк

Следствия шифрования секретов в `backend/crypto.py`.

Зависит от: `backend.crypto`

Тестов: 11


### `tests/backend/test_db_engine.py` — 93 строк

Следствия настроек, которые ставятся на каждое соединение с базой.

Зависит от: `adapters.db`

Тестов: 5

- `async def engine_on_disk(tmp_path)` (5)
- `async def _pragma(engine, name)` (4)

### `tests/backend/test_domain_blacklist.py` — 39 строк

Следствия, которые наблюдают тесты `backend/domain/blacklist.py`.

Зависит от: `backend.domain.blacklist`

Тестов: 6


### `tests/backend/test_domain_dedup.py` — 68 строк

Следствия, которые наблюдают тесты поиска похожего вектора.

Зависит от: `backend.domain.dedup`

Тестов: 8


### `tests/backend/test_domain_embedding_cache.py` — 122 строк

Следствия кэша отпечатков, по которым отсеиваются повторы вакансий.

Зависит от: `backend.domain.dedup`

Тестов: 10


### `tests/backend/test_domain_salary.py` — 419 строк ⚠ подошёл к 300

Следствия, которые наблюдают тесты `backend/domain/salary.py`.

Зависит от: `backend.domain.salary`, `backend.models`

Тестов: 32


### `tests/backend/test_domain_salary_numbers.py` — 177 строк

Следствия чтения самого числа в строке зарплаты.

Зависит от: `backend.domain.salary`, `backend.models`

Тестов: 16


### `tests/backend/test_domain_scoring.py` — 166 строк

Следствия, которые наблюдают тесты `backend/domain/scoring.py`.

Зависит от: `backend.domain.scoring`, `tests.factories`

Тестов: 17


### `tests/backend/test_domain_transitions.py` — 175 строк

Следствия, которые наблюдают тесты `backend/domain/transitions.py`.

Зависит от: `backend.domain.transitions`, `backend.models`

Тестов: 14

- `def ways_out(status: VacancyStatus) -> list[VacancyStatus]` (3)

### `tests/backend/test_domain_verdict.py` — 66 строк

Следствия, которые наблюдают тесты `backend/domain/verdict.py`.

Зависит от: `backend.domain.verdict`, `backend.models`, `tests.factories`

Тестов: 9


### `tests/backend/test_entry_point.py` — 488 строк ⚠ подошёл к 300

Следствия запуска приложения из единственной точки входа.

Зависит от: `backend.single_instance`, `config`, `main`

Тестов: 18

- `def lock_of_its_own(monkeypatch, tmp_path)` (12)
- `def entry(clean_root_logger, lock_of_its_own, monkeypatch)` (41)
  - `def check_keyring()` (2)
  - `def ensure_schema()` (2)
  - `def run_ui()` (3)
- `def _write_through(module, text: str) -> str` (22)

### `tests/backend/test_flows_application_choice.py` — 395 строк ⚠ подошёл к 300

Что именно уходит HR при отклике на вакансию.

Зависит от: `backend.flows`, `backend.models`, `tests.dbio`, `tests.factories`

Тестов: 18

- `async def applying(make_pipeline, session_factory, tmp_path, monkeypatch)` (33)
  - `async def generate_cover_letter(block, parsed, client, model, *, channel_ref=None)` (3)

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


### `tests/backend/test_flows_catch_up.py` — 232 строк

Следствия догона переписок по всем HR разом.

Зависит от: `backend.flows.dm_backfill`, `backend.models`, `tests.backend.fixtures.backfill`, `tests.dbio`, `tests.factories`, `tests.fakes.telegram`

Тестов: 8

- `async def _catch_up(session_factory, **kwargs)` (3)
- `async def _hrs(session_factory, count)` (10)

### `tests/backend/test_flows_channel_cursor.py` — 117 строк

Следствия отметки о разобранном и признака недоразобранной вакансии.

Зависит от: `backend.flows`, `backend.models`, `tests.dbio`, `tests.factories`

Тестов: 7


### `tests/backend/test_flows_channel_metadata.py` — 291 строк

Следствия обновления названий и картинок каналов.

Зависит от: `backend.flows`, `backend.models`, `tests.dbio`, `tests.factories`, `tests.fakes.telegram`

Тестов: 14

- `async def _channels(session_factory, *rows)` (4)

### `tests/backend/test_flows_channel_reading.py` — 329 строк ⚠ подошёл к 300

Следствия чтения новых сообщений одного канала.

Зависит от: `backend.flows`, `backend.models`, `tests.dbio`, `tests.factories`, `tests.fakes.telegram`

Тестов: 15

- `async def reading(monkeypatch, make_pipeline, session_factory)` (13)
  - `async def take(pipeline, channel_id, username, msg)` (2)

### `tests/backend/test_flows_channel_walk.py` — 305 строк ⚠ подошёл к 300

Следствия обхода каналов за один цикл.

Зависит от: `backend.flows`, `backend.models`, `tests.dbio`, `tests.factories`, `tests.fakes.telegram`

Тестов: 16

- `async def walking(monkeypatch, make_pipeline)` (22)
  - `async def reload()` (2)
  - `async def poll(pipeline, channel_id, username, last_id)` (3)

### `tests/backend/test_flows_dm_buffer.py` — 273 строк

Следствия накопления входящих перед разбором ответа HR.

Зависит от: `backend.payloads`

Тестов: 15

- `def _texts(pipeline, hr_id)` (3)

### `tests/backend/test_flows_dm_debounce.py` — 202 строк

Договор копилки отложенного разбора: пачки, таймеры и начавшие.

Зависит от: `backend.flows.dm_debounce`

Тестов: 15

- `def _letter(tg_msg_id: int, text: str) -> dict` (3)

### `tests/backend/test_flows_dm_drain.py` — 250 строк

Следствия гашения отложенных разборов при остановке и выключении.

Зависит от: `backend.flows`, `backend.payloads`

Тестов: 12

- `def _outlasts_the_wait(started: asyncio.Event)` (13)
  - `async def reading(pipeline, hr_id)` (4)

### `tests/backend/test_flows_embedding_cache.py` — 117 строк

Подъём кэша векторов из базы — то, чем занят сам конвейер.

Зависит от: `backend.flows`, `backend.models`, `tests.dbio`, `tests.factories`

Тестов: 5


### `tests/backend/test_flows_embedding_text.py` — 124 строк

Отпечаток текста: что бывает, когда поставщик отпечатков не отвечает.

Зависит от: `backend.flows`

Тестов: 4

- `class _Provider` (8)
  - `async def post(self, *_args, **_kwargs)` (2)
- `class _Pipeline` (6)

### `tests/backend/test_flows_empty_vacancy.py` — 373 строк ⚠ подошёл к 300

Следствия сохранения объявления, из которого нечего было взять.

Зависит от: `backend.domain.verdict`, `backend.flows`, `backend.models`, `tests.backend.fixtures.flows`, `tests.dbio`, `tests.factories`, `tests.fakes.telegram`

Тестов: 16

- `async def emptied(make_pipeline, session_factory)` (20)
- `def caught_backfills(monkeypatch)` (9)
  - `async def backfill(hr_row_, *args, **kwargs)` (2)

### `tests/backend/test_flows_follow_up_text.py` — 84 строк

Следствия составления короткого письма про очередную вакансию.

Зависит от: `backend.flows.apply`

Тестов: 6


### `tests/backend/test_flows_ghosting_timer.py` — 181 строк

Следствия проверки на молчание HR.

Зависит от: `backend.models`, `tests.dbio`, `tests.factories`

Тестов: 8

- `def _long_ago()` (3)
- `def _recently()` (3)

### `tests/backend/test_flows_history_backfill.py` — 371 строк ⚠ подошёл к 300

Следствия догона переписки с одним HR.

Зависит от: `backend.flows.dm`, `backend.flows.dm_backfill`, `backend.models`, `tests.backend.fixtures.backfill`, `tests.dbio`, `tests.factories`, `tests.fakes.telegram`

Тестов: 16


### `tests/backend/test_flows_hr_backfill_spawn.py` — 138 строк

Следствия фонового догона переписки со свежезаведённым HR.

Зависит от: `backend.flows`, `backend.models`, `tests.dbio`, `tests.factories`

Тестов: 6

- `async def spawning(make_pipeline, session_factory, monkeypatch)` (17)
  - `async def backfill(hr_row_, dm, hooks, **kwargs)` (5)

### `tests/backend/test_flows_incoming_attribution.py` — 397 строк ⚠ подошёл к 300

К какой вакансии бот относит письмо HR и что делает дальше.

Зависит от: `backend.models`, `backend.payloads`, `backend.repository.messages`, `backend.repository.vacancies_life`, `tests.dbio`, `tests.factories`, `tests.fakes.telegram`

Тестов: 12

- `async def _two_vacancies(session_factory)` (26)
- `def _ignore(*args)` (6)

### `tests/backend/test_flows_incoming_gate.py` — 340 строк ⚠ подошёл к 300

Кого бот слушает во входящих личных сообщениях, а кого нет.

Зависит от: `backend.bot.media`, `backend.models`, `tests.dbio`, `tests.factories`, `tests.fakes.telegram`

Тестов: 18


### `tests/backend/test_flows_linked_article.py` — 141 строк

Следствия, которые наблюдает тест `backend/flows/linked_article.py`.

Зависит от: `adapters`, `backend.flows`

Тестов: 7

- `def fetched(monkeypatch)` (11)
  - `async def fetch_article(_client, url)` (3)

### `tests/backend/test_flows_manual_application.py` — 191 строк

Следствия отправки отклика кнопкой из карточки вакансии.

Зависит от: `backend.flows`, `backend.models`, `tests.dbio`, `tests.factories`

Тестов: 9

- `async def carded(monkeypatch, make_pipeline, session_factory)` (25)
  - `async def send_application(pipeline, hr_row_, parsed, vacancy_id, *, force=False)` (3)

### `tests/backend/test_flows_new_vacancy.py` — 233 строк

Следствия заведения строки под новое объявление.

Зависит от: `backend.flows`, `backend.models`, `backend.payloads`, `tests.dbio`, `tests.factories`, `tests.fakes.telegram`

Тестов: 12


### `tests/backend/test_flows_parse_persist.py` — 385 строк ⚠ подошёл к 300

Что остаётся в базе после разбора объявления.

Зависит от: `backend.flows`, `backend.models`, `backend.payloads`, `tests.dbio`, `tests.factories`

Тестов: 17


### `tests/backend/test_flows_parse_verdict.py` — 277 строк

Какой приговор получает объявление после разбора.

Зависит от: `backend.domain.verdict`, `backend.flows`, `backend.llm.answers`, `backend.models`, `backend.payloads`, `tests.dbio`

Тестов: 15


### `tests/backend/test_flows_post_intake.py` — 327 строк ⚠ подошёл к 300

Что бот делает с очередным объявлением из канала.

Зависит от: `adapters`, `backend.flows`, `tests.fakes.telegram`

Тестов: 14

- `async def intake(make_pipeline, monkeypatch)` (35)
  - `async def embed(client, model, text)` (3)
  - `async def save(pipeline, post, embedding)` (3)
  - `async def parse(pipeline, vacancy_id, text, username, allow_delete=True)` (3)
  - `async def unparsed(pipeline, vacancy_id)` (2)

### `tests/backend/test_flows_reply_reading.py` — 302 строк ⚠ подошёл к 300

Следствия разбора накопленного ответа HR.

Зависит от: `backend.flows`, `backend.models`, `backend.payloads`, `backend.repository.vacancies_life`, `tests.dbio`, `tests.factories`

Тестов: 12

- `async def reading(make_pipeline, session_factory, monkeypatch)` (33)
  - `async def classify_hr_reply(text, status, client, model)` (5)
- `def _buffer(pipeline, hr, vacancy, message, *texts)` (11)

### `tests/backend/test_flows_rerun_fingerprint.py` — 168 строк

Отпечаток вакансии при повторном прогоне и кэш отсева повторов.

Зависит от: `adapters`, `backend.flows`, `backend.models`, `tests.backend.fixtures.rerun`, `tests.dbio`, `tests.fakes.telegram`

Тестов: 7


### `tests/backend/test_flows_resources.py` — 154 строк

Следствия перезагрузки настроек перед обходом каналов.

Зависит от: `backend.models`, `tests.dbio`, `tests.factories`

Тестов: 9


### `tests/backend/test_flows_vacancy_removal.py` — 167 строк

Следствия удаления вакансии конвейером.

Зависит от: `backend.flows`, `backend.models`, `tests.dbio`, `tests.factories`

Тестов: 8

- `async def with_a_vacancy(make_pipeline, session_factory)` (22)

### `tests/backend/test_flows_vacancy_rerun.py` — 301 строк ⚠ подошёл к 300

Следствия повторного прогона вакансии кнопкой из карточки.

Зависит от: `adapters`, `backend.flows`, `backend.models`, `backend.repository.vacancy_status`, `tests.backend.fixtures.rerun`, `tests.dbio`, `tests.factories`, `tests.fakes.telegram`

Тестов: 15


### `tests/backend/test_flows_window_hooks.py` — 43 строк

Следствия оповещений окна из конвейера.

Зависит от: —

Тестов: 2


### `tests/backend/test_health.py` — 42 строк

Следствия вопроса «живо ли то, на чём держится работа».

Зависит от: `backend.health`

Тестов: 2

- `class Stopped` (5)
  - `def __call__(self)` (2)
- `class Bot` (3)

### `tests/backend/test_llm_classify_reply.py` — 239 строк

Следствия разбора ответа HR в новый статус вакансии.

Зависит от: `backend.llm.hr_reply`, `backend.models`, `tests.fakes.llm`

Тестов: 15

- `def _allowed_line(client) -> str` (9)
- `def _verdict(status: str, explanation: str | None=None) -> httpx.Response` (3)

### `tests/backend/test_llm_company_arbiter.py` — 303 строк ⚠ подошёл к 300

Следствия обращения к модели как к арбитру при сведении компаний.

Зависит от: `backend.llm.company`, `backend.llm.rules`, `tests.fakes.llm`

Тестов: 17

- `class _Candidate` (8)
- `def _answer(matched_id=None, reasoning=None) -> httpx.Response` (3)
- `async def _ask(client, candidates, name='Сбербанк Тех')` (9)

### `tests/backend/test_llm_cover_letter.py` — 361 строк ⚠ подошёл к 300

Следствия составления письма-отклика.

Зависит от: `backend.llm.cover_letter`, `tests.factories`, `tests.fakes.llm`

Тестов: 22

- `def _client(letter: str, *, finish_reason: str='stop', factcheck: str=PASSES)` (10)

### `tests/backend/test_llm_cv_items.py` — 190 строк

Следствия разбора навыков и опыта работы в `backend/llm/cv.py`.

Зависит от: `backend.llm.cv`, `tests.factories`, `tests.fakes.llm`

Тестов: 20

- `async def parse_sections(**sections)` (4)
- `async def one_skill(**fields)` (6)
- `async def one_job(**fields)` (7)

### `tests/backend/test_llm_cv_profile.py` — 188 строк

Следствия разбора профиля и языков в `backend/llm/cv.py`.

Зависит от: `backend.llm.cv`, `tests.factories`, `tests.fakes.llm`

Тестов: 19

- `async def parse_answer(answer: str)` (4)
- `async def parse_profile(**fields)` (3)

### `tests/backend/test_llm_cv_response.py` — 166 строк

Следствия, которые наблюдает внешний слой `parse_cv`.

Зависит от: `backend.llm.cv`, `tests.factories`, `tests.fakes.llm`

Тестов: 15


### `tests/backend/test_llm_enum_values.py` — 31 строк

Следствия сверки значения со списком допустимых.

Зависит от: `backend.llm.answers`

Тестов: 1


### `tests/backend/test_llm_external.py` — 26 строк

Следствия подготовки чужого текста к вставке в промпт.

Зависит от: `backend.llm.external`

Тестов: 2


### `tests/backend/test_llm_factcheck.py` — 189 строк

Следствия второй проверки письма — сверки фактов с профилем.

Зависит от: `backend.llm.factcheck`, `tests.fakes.llm`

Тестов: 11

- `def _verdict(verdict, issues=None) -> httpx.Response` (3)

### `tests/backend/test_llm_fit_validation.py` — 406 строк ⚠ подошёл к 300

Следствия проверки вакансии на пригодность кандидату.

Зависит от: `backend.llm.candidate`, `backend.llm.fit`, `tests.factories`, `tests.fakes.llm`

Тестов: 21

- `def _answer(verdict, reason=None) -> httpx.Response` (3)
- `async def _check(client, *, raw_text='обычный текст вакансии', profile=None, parsed=None)` (11)
- `async def _asked(client, *, raw_text='обычный текст вакансии', profile=None, parsed=None)` (9)

### `tests/backend/test_llm_json_extraction.py` — 210 строк

Следствия вырезания ответа-объекта из того, что вернула модель.

Зависит от: `backend.llm.answers`

Тестов: 13


### `tests/backend/test_llm_profile_formatting.py` — 160 строк

Следствия подготовки сведений о кандидате для запроса к модели.

Зависит от: `backend.llm.candidate`

Тестов: 9

- `class _Skill` (6)

### `tests/backend/test_llm_stack_cleanup.py` — 187 строк

Следствия приведения названий технологий к единому виду.

Зависит от: `backend.llm.skills`

Тестов: 11


### `tests/backend/test_llm_vacancy_answer.py` — 309 строк ⚠ подошёл к 300

Следствия разбора ответа модели в разобранную вакансию.

Зависит от: `backend.llm.vacancy`, `tests.fakes.llm`

Тестов: 23

- `def _answer(**fields) -> str` (3)

### `tests/backend/test_llm_vacancy_request.py` — 290 строк

Следствия обращения к модели за разбором поста с вакансией.

Зависит от: `backend.llm.rules`, `backend.llm.vacancy`, `tests.fakes.llm`

Тестов: 16

- `def _parsed(**fields) -> httpx.Response` (3)

### `tests/backend/test_log_buffer.py` — 501 строк ⚠ за пределом 500

Следствия, которые наблюдают тесты журналирования.

Зависит от: `backend.log_buffer`, `backend.log_file`, `backend.log_secrets`, `config`

Тестов: 29

- `def clean_log_file()` (11)
- `def record(msg: str, *, name: str='проверка', level: int=logging.INFO)` (6)
- `def _busy(source, dest)` (3)
- `def _unbuildable()` (6)

### `tests/backend/test_message_text.py` — 151 строк

Следствия, которые наблюдают тесты `backend/message_text.py`.

Зависит от: `backend.message_text`, `tests.fakes.telegram`

Тестов: 19


### `tests/backend/test_migration_engine.py` — 178 строк

Следствия того, каким движком alembic открывает базу и как его закрывает.

Зависит от: `alembic`, `backend.bootstrap`, `tests.conftest`

Тестов: 4

- `def _learning_project(tmp_path, rebuild: str)` (14)
- `def _tenants(db_file) -> list[tuple]` (6)

### `tests/backend/test_notify.py` — 61 строк

Следствия, которые наблюдает оповещение окна `backend/notify.py`.

Зависит от: `backend.notify`

Тестов: 3


### `tests/backend/test_payloads_stack.py` — 53 строк

Следствия объединённого стека разобранной вакансии.

Зависит от: `tests.factories`

Тестов: 4


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


### `tests/backend/test_repository_blacklist_matcher_values.py` — 60 строк

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


### `tests/backend/test_repository_channel_list_filter.py` — 32 строк

Следствия отбора по строке в списке каналов.

Зависит от: `tests.dbio`, `tests.factories`

Тестов: 2


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


### `tests/backend/test_repository_channel_switching.py` — 142 строк

Следствия управления включённостью канала.

Зависит от: `backend.models`, `backend.repository.channels`, `tests.dbio`, `tests.factories`

Тестов: 9

- `async def _listed_and_clean(session_factory, *, is_active: bool)` (13)

### `tests/backend/test_repository_company_autolink_llm.py` — 240 строк

Следствия обращения к языковой модели при сведении компаний.

Зависит от: `backend.repository.companies_matching`, `tests.dbio`, `tests.factories`

Тестов: 9

- `class Arbiter` (21)
  - `async def __call__(self, client, model, *, parsed_name, parsed_website, candidates)` (13)
- `def arbiter(monkeypatch)` (14)
  - `def install(**kwargs) -> Arbiter` (4)
- `async def resolve(session, name, arbiter_fake=None, **kwargs)` (9)

### `tests/backend/test_repository_company_autolink_rules.py` — 406 строк ⚠ подошёл к 300

Следствия автоматического сведения разобранной компании к существующей.

Зависит от: `backend.models`, `backend.repository.companies_matching`, `tests.dbio`, `tests.factories`

Тестов: 20


### `tests/backend/test_repository_company_blacklist_marks.py` — 132 строк

Следствия переезда отметки чёрного списка вслед за именем компании.

Зависит от: `backend.models`, `backend.repository.companies_card`, `tests.dbio`, `tests.factories`

Тестов: 5


### `tests/backend/test_repository_company_card.py` — 196 строк

Следствия сборки карточки компании для боковой панели контактов.

Зависит от: `backend.repository.blacklist_marks`, `backend.repository.companies_card`, `backend.repository.hr_list`, `tests.dbio`, `tests.factories`

Тестов: 10


### `tests/backend/test_repository_company_creation.py` — 58 строк

Следствия заведения компании вручную.

Зависит от: `backend.repository.companies_card`

Тестов: 4


### `tests/backend/test_repository_company_edits.py` — 94 строк

Следствия правки полей компании.

Зависит от: `backend.repository.companies_card`, `tests.dbio`, `tests.factories`

Тестов: 6


### `tests/backend/test_repository_company_keys.py` — 225 строк

Следствия приведения имени и сайта компании к сравнимому виду.

Зависит от: `backend.domain.company_hosts`, `backend.repository.companies_keys`

Тестов: 11


### `tests/backend/test_repository_company_list.py` — 166 строк

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


### `tests/backend/test_repository_hr_attribution.py` — 134 строк

Следствия привязки ответа HR к вакансии, о которой он пишет.

Зависит от: `backend.repository.hr_identify`, `tests.dbio`, `tests.factories`

Тестов: 7


### `tests/backend/test_repository_hr_blacklist_marks.py` — 221 строк

Следствия сопоставления HR со строками чёрного списка.

Зависит от: `backend.models`, `backend.repository.blacklist_marks`, `backend.repository.hr_card`, `tests.dbio`, `tests.factories`

Тестов: 12


### `tests/backend/test_repository_hr_card.py` — 140 строк

Следствия сборки карточки HR для боковой панели контактов.

Зависит от: `backend.repository.hr_card`, `tests.dbio`, `tests.factories`

Тестов: 7


### `tests/backend/test_repository_hr_creation.py` — 39 строк

Следствия заведения HR вручную с экрана контактов.

Зависит от: `backend.repository.hr_card`, `backend.repository.hr_identify`

Тестов: 2


### `tests/backend/test_repository_hr_edits.py` — 147 строк

Следствия правки полей HR.

Зависит от: `backend.repository.hr_card`, `tests.dbio`, `tests.factories`

Тестов: 9


### `tests/backend/test_repository_hr_identity.py` — 133 строк

Следствия опознания отправителя входящего сообщения.

Зависит от: `backend.repository.hr_identify`, `tests.dbio`, `tests.factories`, `tests.fakes.telegram`

Тестов: 7


### `tests/backend/test_repository_hr_letter_history.py` — 104 строк

Следствия подсчёта писем, отправленных HR за последнее время.

Зависит от: `backend.repository.hr_identify`, `tests.dbio`, `tests.factories`

Тестов: 4


### `tests/backend/test_repository_hr_list_catchup.py` — 25 строк

Следствия перечней, с которых бот догоняет пропущенное после простоя.

Зависит от: `backend.repository.hr_list`, `tests.dbio`, `tests.factories`

Тестов: 1


### `tests/backend/test_repository_hr_list_filter.py` — 64 строк

Следствия отбора по строке и постраничности в списке HR.

Зависит от: `tests.dbio`, `tests.factories`

Тестов: 4


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

Зависит от: `backend.repository.hr_identify`, `tests.dbio`, `tests.factories`, `tests.fakes.telegram`

Тестов: 9


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


### `tests/backend/test_repository_message_unread.py` — 136 строк

Следствия подсчёта непрочитанных входящих сообщений.

Зависит от: `backend.repository.hr_list`, `backend.repository.messages`, `tests.dbio`, `tests.factories`

Тестов: 7


### `tests/backend/test_repository_profile_block.py` — 196 строк

Следствия сборки блока «Информация о кандидате» для письма-отклика.

Зависит от: `backend.repository.profile_block`, `tests.dbio`, `tests.factories`

Тестов: 11


### `tests/backend/test_repository_profile_cv_saving.py` — 293 строк

Следствия записи разобранного резюме в профиль.

Зависит от: `backend.models`, `backend.payloads`, `backend.repository.profile`, `backend.repository.profile_cv`, `backend.repository.profile_experience`, `backend.repository.profile_skills`, `tests.dbio`, `tests.factories`

Тестов: 10

- `def _profile(**overrides) -> ParsedCvProfile` (18)
- `def _skill(name: str, **overrides) -> ParsedCvSkill` (3)
- `def _place(**overrides) -> ParsedCvExperience` (9)
- `def _cv(**overrides) -> ParsedCv` (10)

### `tests/backend/test_repository_profile_experience.py` — 260 строк

Следствия сохранения мест работы профиля.

Зависит от: `backend.models`, `backend.repository.profile_experience`, `tests.dbio`, `tests.factories`

Тестов: 12

- `def _row(**overrides) -> dict` (5)

### `tests/backend/test_repository_profile_fields.py` — 62 строк

Следствия чтения и записи основных полей профиля.

Зависит от: `backend.repository.profile`, `backend.repository.profile_skills`, `tests.dbio`, `tests.factories`

Тестов: 5


### `tests/backend/test_repository_profile_languages.py` — 67 строк

Следствия замены списка языков профиля.

Зависит от: `backend.repository.profile_languages`, `tests.dbio`, `tests.factories`

Тестов: 4


### `tests/backend/test_repository_profile_skills.py` — 281 строк

Следствия сохранения списка навыков профиля.

Зависит от: `backend.models`, `backend.repository.profile_skills`, `tests.dbio`, `tests.factories`

Тестов: 12

- `async def names_and_levels(session) -> list[tuple[str, int]]` (3)

### `tests/backend/test_repository_stats_breakdown.py` — 196 строк

Следствия разбивки вакансий по статусам за период.

Зависит от: `backend.models`, `backend.repository.stats_statuses`, `tests.dbio`, `tests.factories`

Тестов: 9


### `tests/backend/test_repository_stats_kpi.py` — 254 строк

Следствия сводных счётчиков в шапке экрана статистики.

Зависит от: `backend.models`, `backend.repository.stats_kpi`, `tests.dbio`, `tests.factories`

Тестов: 11

- `def _four_steps(vacancy_id: int, when)` (11)

### `tests/backend/test_repository_stats_period.py` — 68 строк

Следствия перевода кода периода в границу отсчёта.

Зависит от: `backend.repository.stats_common`

Тестов: 3


### `tests/backend/test_repository_stats_pipeline.py` — 511 строк ⚠ за пределом 500

Следствия таблицы «каналы» на экране статистики.

Зависит от: `backend.domain.verdict`, `backend.models`, `backend.repository.stats_pipeline`, `tests.dbio`, `tests.factories`

Тестов: 19

- `async def rows_by_label(session, **kwargs) -> dict[str, dict]` (4)

### `tests/backend/test_repository_stats_response_time.py` — 260 строк

Следствия подсчёта срока ответа на отклик.

Зависит от: `backend.models`, `backend.repository.stats_responses`, `tests.dbio`, `tests.factories`

Тестов: 12


### `tests/backend/test_repository_stats_response_weekday.py` — 69 строк

Следствия распределения ответов HR по дням недели.

Зависит от: `backend.repository.stats_responses`, `tests.dbio`, `tests.factories`

Тестов: 2

- `def _monday(hour: int=12) -> datetime` (7)
- `def _local_monday_after_midnight() -> datetime` (12)

### `tests/backend/test_repository_stats_skills.py` — 184 строк

Следствия подсчёта технологий, встречающихся в вакансиях.

Зависит от: `backend.repository.stats_skills`, `tests.dbio`, `tests.factories`

Тестов: 11

- `async def labels(session, **kwargs) -> list[str]` (4)

### `tests/backend/test_repository_trash_marks.py` — 44 строк

Отметки о мусоре: по одной на пост, сколько бы раз его ни разбирали.

Зависит от: `backend.models`, `backend.repository.vacancies_life`, `tests.dbio`, `tests.factories`

Тестов: 2

- `async def _noted(session, channel_id: int, msg_id: int, reason: str) -> None` (8)

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


### `tests/backend/test_repository_vacancy_joins.py` — 364 строк ⚠ подошёл к 300

Следствия отбора в `list_vacancies` по тому, что лежит в соседних таблицах.

Зависит от: `backend.repository.vacancies_list`, `tests.dbio`, `tests.factories`

Тестов: 18


### `tests/backend/test_repository_vacancy_links.py` — 237 строк

Следствия привязки вакансии к HR и компании и её удаления.

Зависит от: `backend.models`, `backend.repository.vacancies_card`, `backend.repository.vacancies_life`, `tests.dbio`, `tests.factories`

Тестов: 13


### `tests/backend/test_repository_vacancy_mini_lists.py` — 260 строк

Следствия трёх коротких списков вакансий, привязанных к одному владельцу.

Зависит от: `backend.models`, `backend.repository.vacancies_mini`, `tests.dbio`, `tests.factories`

Тестов: 9


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


### `tests/backend/test_repository_vacancy_status.py` — 267 строк

Следствия смены статуса вакансии — руками и автоматически.

Зависит от: `backend.models`, `backend.payloads`, `backend.repository.vacancies_card`, `backend.repository.vacancy_status`, `tests.dbio`, `tests.factories`

Тестов: 14


### `tests/backend/test_runtime_settings_load.py` — 204 строк

Следствия чтения настроек из базы в память.

Зависит от: `backend.crypto`, `backend.models`, `backend.runtime_settings`, `tests.dbio`, `tests.factories`

Тестов: 18


### `tests/backend/test_runtime_settings_masking.py` — 78 строк

Следствия сокрытия секретов от журнала в `backend/runtime_settings.py`.

Зависит от: `backend.runtime_settings`, `tests.factories`

Тестов: 4


### `tests/backend/test_runtime_settings_values.py` — 233 строк

Следствия типизированных свойств `RuntimeSettings`.

Зависит от: `backend.runtime_settings`

Тестов: 25

- `def settings(**app) -> RuntimeSettings` (16)

### `tests/backend/test_runtime_settings_writes.py` — 210 строк

Следствия записи настроек: у одних методов их два, у других — одно.

Зависит от: `adapters`, `backend.crypto`, `backend.models`, `backend.runtime_settings`, `tests.dbio`, `tests.factories`

Тестов: 16


### `tests/backend/test_schema_and_models.py` — 42 строк

Схема базы и объявления моделей не разошлись.

Зависит от: `backend.models`

Тестов: 1


### `tests/backend/test_single_instance.py` — 124 строк

Следствия сторожа единственности приложения.

Зависит от: `backend.single_instance`

Тестов: 5

- `def _lock_once_it_is_free(lock_path: Path, seconds: float=5.0)` (14)

### `tests/backend/test_telegram_adapter.py` — 140 строк

Следствия сборки клиента Telegram и отправки личного сообщения.

Зависит от: `adapters.telegram`, `config`, `tests.factories`, `tests.fakes.telegram`

Тестов: 9


### `tests/backend/test_telegram_identity.py` — 77 строк

Следствия, которые наблюдают тесты `backend/domain/telegram_identity.py`.

Зависит от: `backend.domain.telegram_identity`

Тестов: 4


### `tests/backend/test_telegram_login.py` — 363 строк ⚠ подошёл к 300

Следствия входа в Telegram по коду.

Зависит от: `backend.runtime_settings`, `backend.telegram_login`, `tests.fakes.telegram`

Тестов: 22

- `def clients(monkeypatch)` (16)
  - `def build(**kwargs)` (5)
- `async def login(session_factory, clients)` (4)
- `async def sent(login, *, phone='+79991234567')` (3)

### `tests/backend/test_telegram_lookup.py` — 146 строк

Следствия, которые наблюдают тесты `backend/telegram_lookup.py`.

Зависит от: `backend.telegram_lookup`, `tests.fakes.telegram`

Тестов: 14


### `tests/backend/test_telegram_time.py` — 47 строк

Следствия, которые наблюдает тест `backend/telegram_time.py`.

Зависит от: `backend.telegram_time`

Тестов: 3


### `tests/backend/test_wipe.py` — 220 строк

Следствия сноса данных: что остаётся в каталоге после «удалить всё».

Зависит от: `backend.single_instance`, `backend.wipe`, `config`

Тестов: 8

- `def lock_let_go()` (9)
- `def data_dir(tmp_path, monkeypatch)` (7)

### `tests/client/conftest.py` — 210 строк

Стенд моста: поверхность окна поверх настоящей базы, без окна и без канала.

Зависит от: `backend.log_buffer`, `backend.runtime_settings`, `client`, `client.bridge`, `tests.fakes.ui_bot`

- `class LoopRunner` (37)
  - `def submit(self, coro) -> Future` (4)
  - `async def drain(self) -> None` (12)
- `async def runner() -> LoopRunner` (3)
- `async def runtime_settings(session_factory) -> RuntimeSettings` (7)
- `async def hub(runtime_settings, session_factory, runner)` (24)
- `async def api(hub) -> Api` (3)
- `def ask()` (12)
  - `async def _ask(method, *args)` (2)
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

### `tests/client/test_bot_contract.py` — 80 строк

Шов имён между мостом и ботом.

Зависит от: `backend.bot`, `backend.bot.client`, `client.bridge`, `tests.fakes.ui_bot`

Тестов: 3

- `def _asked_of_the_bot() -> list[str]` (7)
- `def _hooks_the_window_fills() -> list[str]` (14)
- `def _hooks_the_bot_declares() -> set[str]` (8)

### `tests/client/test_bridge_answer.py` — 132 строк

Следствия общей части моста: чем окну отвечают на любой запрос.

Зависит от: `client.bridge.answer`

Тестов: 6


### `tests/client/test_bridge_blacklist.py` — 216 строк

Следствия слотов чёрного списка: записи заслона и весь их перечень.

Зависит от: `backend.models`, `tests.dbio`, `tests.factories`

Тестов: 13


### `tests/client/test_bridge_blacklist_hints.py` — 57 строк

Следствия подсказок к форме заслона: кого окно предлагает выбрать.

Зависит от: `tests.dbio`, `tests.factories`

Тестов: 3


### `tests/client/test_bridge_bot_stop.py` — 59 строк

Следствия остановки бота: чем кончается ожидание, которого не дождались.

Зависит от: `client.bridge.bot_stop`

Тестов: 2

- `class HangingBot` (11)
  - `def cancel_current_poll(self) -> None` (2)
  - `def request_stop(self) -> None` (2)

### `tests/client/test_bridge_channel_actions.py` — 206 строк

Следствия действий над каналом, которым нужен поднятый бот.

Зависит от: `backend.models`, `tests.dbio`, `tests.factories`

Тестов: 12


### `tests/client/test_bridge_channels.py` — 189 строк

Следствия домена канала, которым хватает одной базы.

Зависит от: `backend.models`, `tests.dbio`, `tests.factories`

Тестов: 9


### `tests/client/test_bridge_choice_sets.py` — 35 строк

Следствия отбора значений из закрытых наборов при чтении форм окна.

Зависит от: `backend.domain.taxonomy`, `client.bridge.choices`

Тестов: 2


### `tests/client/test_bridge_companies.py` — 278 строк

Следствия домена компании: перечень, карточка, написания, слияние, заслон.

Зависит от: `tests.dbio`, `tests.factories`

Тестов: 15


### `tests/client/test_bridge_cv.py` — 133 строк

Следствия резюме — файла, путь к которому помнит окно.

Зависит от: `tests.client.conftest`

Тестов: 8


### `tests/client/test_bridge_events.py` — 218 строк

Следствия очереди живых событий: что узнаёт окно, спросившее «что нового».

Зависит от: `client.bridge.events`

Тестов: 12


### `tests/client/test_bridge_hr.py` — 268 строк

Следствия карточки HR: перечень, правка, слияние, чёрный список.

Зависит от: `tests.dbio`, `tests.factories`

Тестов: 16


### `tests/client/test_bridge_hr_chat.py` — 191 строк

Следствия переписки: что окно показывает и чем отвечают на отправку.

Зависит от: `tests.client.conftest`, `tests.dbio`, `tests.factories`

Тестов: 10


### `tests/client/test_bridge_journal.py` — 124 строк

Следствия домена журнала: что человек видит на экране записей.

Зависит от: `backend.log_buffer`

Тестов: 5

- `def journal()` (20)

### `tests/client/test_bridge_lifespan.py` — 249 строк

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


### `tests/client/test_bridge_llm.py` — 390 строк ⚠ подошёл к 300

Следствия проверки языковой модели: что окно узнаёт, нажав «проверить».

Зависит от: `tests.fakes.llm`

Тестов: 16

- `def _busy_provider(free: asyncio.Event)` (23)
  - `def make(_cfg)` (13)
    - `async def answer(request)` (8)
- `def provider_says(monkeypatch)` (15)
  - `def _answer(routes) -> None` (6)

### `tests/client/test_bridge_login.py` — 196 строк

Следствия входа в Telegram: три шага, о которых окно спрашивает по одному.

Зависит от: `backend.crypto`, `backend.telegram_login`, `tests.dbio`, `tests.factories`, `tests.fakes.ui_login`

Тестов: 10


### `tests/client/test_bridge_paging.py` — 74 строк

Следствия признака продолжения — того, по которому окно решает, просить ли ещё.

Зависит от: `tests.dbio`, `tests.factories`

Тестов: 4


### `tests/client/test_bridge_profile.py` — 212 строк

Следствия слотов анкеты — того, что человек рассказывает о себе.

Зависит от: —

Тестов: 11

- `async def _saved_person(api, ask, **extra) -> None` (4)

### `tests/client/test_bridge_runner.py` — 105 строк

Следствия мотора, в котором окно исполняет свою работу.

Зависит от: `client.bridge.runner`

Тестов: 5

- `def runner()` (11)

### `tests/client/test_bridge_settings.py` — 87 строк

Следствия экрана настроек: что записано и что показано на экране.

Зависит от: `backend.models`

Тестов: 4


### `tests/client/test_bridge_shell.py` — 197 строк

Следствия обращения к оболочке: что окно отдаёт системе, а что нет.

Зависит от: `client.bridge.desktop`, `client.serving`

Тестов: 10

- `def opened(monkeypatch) -> list` (8)
- `def media(monkeypatch, tmp_path)` (10)

### `tests/client/test_bridge_stats.py` — 89 строк

Следствия домена статистики: чей ответ и за какой срок приходит в окно.

Зависит от: `tests.dbio`, `tests.factories`

Тестов: 7


### `tests/client/test_bridge_system.py` — 140 строк

Следствия домена «система»: чем занят бот и что показывает нижняя полоса.

Зависит от: —

Тестов: 8


### `tests/client/test_bridge_vacancies.py` — 316 строк ⚠ подошёл к 300

Следствия слотов вакансий, которым хватает одной базы.

Зависит от: `backend.models`, `tests.dbio`, `tests.factories`

Тестов: 16


### `tests/client/test_bridge_vacancy_actions.py` — 262 строк

Следствия действий над вакансией, которым нужен поднятый бот.

Зависит от: `tests.dbio`, `tests.factories`

Тестов: 13

- `def broken_vacancy(session_factory, with_bot)` (13)
  - `async def _put()` (8)
    - `async def broken(vacancy_id)` (2)

### `tests/client/test_bridge_vacancy_links.py` — 228 строк

Следствия связывания вакансии с HR и компанией — вместе с подборщиками.

Зависит от: `tests.dbio`, `tests.factories`

Тестов: 11


### `tests/client/test_bridge_wipe.py` — 149 строк

Следствие удаления всех данных: в каком порядке это происходит.

Зависит от: `tests.fakes.ui_bot`

Тестов: 4

- `def wipe_steps(monkeypatch, hub)` (19)
  - `async def _wipe_all(engine) -> list[str]` (3)

### `tests/client/test_bridge_wire.py` — 28 строк

Следствия перевода внутренних значений в словари для окна.

Зависит от: `client.bridge.wire`

Тестов: 2


### `tests/client/test_bridge_wizard.py` — 226 строк

Следствия первого запуска: с какого шага он продолжается и чем кончается.

Зависит от: `backend.crypto`, `backend.models`, `backend.runtime_settings`, `tests.dbio`, `tests.factories`

Тестов: 11


### `tests/client/test_form_payloads.py` — 237 строк

Следствия чтения нагрузок форм «добавить HR» и «добавить компанию».

Зависит от: `backend.repository.companies_card`, `backend.repository.hr_identify`, `client.bridge.form_payloads`

Тестов: 18


### `tests/client/test_front_vocabulary.py` — 83 строк

Согласие перечней окна с перечнями бэкенда.

Зависит от: `backend.domain.taxonomy`, `backend.models.enums`, `backend.models.settings`

Тестов: 6

- `def _array(module: str, name: str) -> str` (10)
- `def _strings(module: str, name: str) -> list[str]` (3)
- `def _values(module: str, name: str) -> list[str]` (3)

### `tests/client/test_page_contract.py` — 125 строк

Шов имён: сходятся ли имена, которыми страница зовёт мост, с самим мостом.

Зависит от: —

Тестов: 5

- `def _sources() -> list[Path]` (7)
- `def _called(text: str) -> set[tuple[str, str]]` (2)

### `tests/client/test_raise_window.py` — 161 строк

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

### `tests/client/test_window.py` — 210 строк

Следствия открытия и закрытия окна: что приложение делает вокруг него.

Зависит от: `backend.models`, `backend.repository.bot_mode`, `client`

Тестов: 7

- `class FakeWebview` (12)
  - `def create_window(self, title: str, url=None, **options)` (3)
  - `def start(self, **options) -> None` (2)
- `class StubRunner` (19)
  - `def submit(self, coro) -> Future` (5)
  - `def stop(self) -> None` (2)
- `class StubHub` (4)
- `def opened(monkeypatch, runtime_settings, session_factory)` (24)
  - `class StubListener` (3)
    - `def close(self) -> None` (2)

### `tests/client/test_window_size.py` — 35 строк

Рост окна в тот миг, когда мастер закончен.

Зависит от: `client`

Тестов: 2


### `tests/conftest.py` — 343 строк ⚠ подошёл к 300

Стенд: подмена каталога данных, хранилища ключей и базы.

Зависит от: `adapters.db`, `adapters.telegram`, `alembic`, `backend.bootstrap`, `config`, `tests.fakes.keyring`

- `def _data_dir_without_appdata() -> Path` (15)
- `def _temporary_data_dir()` (3)
- `def memory_keyring() -> MemoryKeyring` (3)
- `def _appdata_guard()` (27)
- `def database_url() -> str` (9)
- `def migrations_target(tmp_path, monkeypatch) -> Path` (13)
- `def _schema(database_url)` (8)
- `class TelegramReached(BaseException)` (10)
- `def _telegram_is_unreachable(monkeypatch)` (32)
  - `async def _refuse(*_args, **_kwargs)` (6)
- `def _sending_locked(monkeypatch)` (10)
- `async def _clear_all_tables(engine: AsyncEngine) -> None` (37)
- `async def _clean_database(_schema, database_url)` (25)
- `async def engine(_schema, database_url)` (14)
- `def session_factory(engine) -> async_sessionmaker[AsyncSession]` (8)
- `async def session(session_factory)` (16)

### `tests/dbio.py` — 36 строк

Короткие обращения к базе из теста.

Зависит от: —

- `async def put(session_factory, *rows) -> None` (6)
- `async def only_row(session_factory, model)` (4)
- `async def all_rows(session_factory, model) -> list` (8)

### `tests/factories.py` — 399 строк ⚠ подошёл к 300

Построение объектов, которые тесты подают на вход коду.

Зависит от: `backend.models`, `backend.payloads`, `backend.runtime_settings`

- `def at(minutes: int) -> datetime` (3)
- `def days_ago(days: float) -> datetime` (8)
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
- `def blacklist_row(kind: str, value: str, **overrides) -> Blacklist` (5)
- `def message_row(**overrides) -> Message` (11)
- `def unread_probe(hr_id: int) -> list[Message]` (26)
- `def unread_probe_with_a_neighbour(hr_id: int, other_hr_id: int) -> list[Message]` (13)
- `def channel_marks() -> list[Blacklist]` (13)
- `def marked_channels() -> list[TelegramChannel]` (15)
- `def vacancy_event_row(vacancy_id: int, **overrides) -> VacancyEvent` (5)
- `def status_history_row(vacancy_id: int, **overrides) -> VacancyStatusHistory` (10)
- `def tg_creds(**overrides) -> TgAccountConfig` (16)

### `tests/fakes/ingestion.py` — 149 строк

Подделка конвейера сбора и оповещений окна о ходе цикла.

Зависит от: `backend.flows.dm`, `backend.flows.dm_backfill`

- `class FakeIngestion` (100)
  - `async def recover_orphan_vacancies(self)` (4)
  - `async def check_ghosting_timeouts(self)` (4)
  - `async def cancel_pending_dm_classifications(self, drain: bool=False)` (4)
  - `def mark_shutting_down(self)` (2)
  - `def schedule_dm_classification(self, hr_id, *rest)` (3)
  - `def dm_helpers(self) -> DmHelpers` (7)
  - `def dm_hooks(self) -> DmHooks` (3)
  - `def update_dm_buffer_text(self, hr_id: int, tg_message_id: int, text: str) -> None` (2)
  - `def remove_dm_buffer_msg(self, hr_id: int, tg_message_id: int) -> None` (2)
  - `async def poll_one_channel(self, channel_id: int)` (3)
  - `async def poll_active_channels(self)` (4)
  - `async def rerun_pipeline_for_vacancy(self, vacancy_id: int)` (3)
  - `async def forget_vacancy(self, vacancy_id: int)` (3)
  - `async def send_application_for_vacancy(self, vacancy_id: int)` (3)
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

### `tests/fakes/llm.py` — 217 строк

Подделка провайдера LLM: настоящий клиент поверх подставного транспорта.

Зависит от: —

- `def _troubles() -> list[tuple[str, object, str]]` (22)
- `def provider_trouble(*extra)` (9)
- `def provider_trouble_named(*extra)` (7)
- `def _picker(routes: dict)` (16)
  - `def pick(key: tuple[str, str])` (8)
- `def provider(routes: dict[tuple[str, str], httpx.Response | BaseException | list], *, api_key: str='') -> httpx.AsyncClient` (38)
  - `def handle(request: httpx.Request) -> httpx.Response` (15)
- `def models_response(*ids: str) -> httpx.Response` (3)
- `def parsed_vacancy_answer(**fields) -> dict` (8)
- `def chat_json(payload: dict, *, finish_reason: str='stop') -> httpx.Response` (9)
- `def messages_of(request: httpx.Request) -> dict[str, str]` (9)
- `def data_block(request: httpx.Request) -> str` (9)
- `def warning_before_the_block(request: httpx.Request) -> str` (9)
- `def chat_response(content: str | None, *, finish_reason: str='stop') -> httpx.Response` (14)

### `tests/fakes/lm_studio.py` — 18 строк

Пустое соединение с языковой моделью — для сборок, что до неё не ходят.

Зависит от: —

- `class LmClient` (9)
  - `async def aclose(self) -> None` (2)

### `tests/fakes/telegram.py` — 346 строк ⚠ подошёл к 300

Подделка клиента Pyrogram и построители его объектов.

Зависит от: `tests.factories`

- `def message(*, text=None, caption=None, **extra) -> SimpleNamespace` (9)
- `def link_entity(*, offset: int, length: int, url: str) -> SimpleNamespace` (14)
- `def url_entity(*, offset: int, length: int) -> SimpleNamespace` (9)
- `def incoming(*, user_id=777, username=None, text='здравствуйте', **extra)` (26)
- `def outgoing(*, peer_id=777, peer_username=None, **extra)` (16)
- `def post(msg_id: int, *, text=_UNSET, **extra)` (14)
- `def photo(*, small_file_id=None, big_file_id=None) -> SimpleNamespace` (3)
- `def document(name: str | None) -> SimpleNamespace` (3)
- `def chat(*, title=None, photo=None, **extra) -> SimpleNamespace` (3)
- `def user(*, username=None, photo=None, **extra) -> SimpleNamespace` (15)
- `class FakeTelegramClient` (175)
  - `def loop(self)` (4)
  - `def add_handler(self, handler) -> None` (2)
  - `def _fail_if_asked(self, method: str) -> None` (6)
  - `async def get_chat(self, chat_id)` (4)
  - `async def get_chat_history(self, target, limit=100)` (5)
  - `async def get_users(self, username)` (4)
  - `async def download_media(self, target, file_name=None, in_memory=False)` (21)
  - `async def _accept(self, kind: str, target, payload, caption=None)` (15)
  - `async def send_message(self, target, text)` (2)
  - `async def send_photo(self, target, path)` (2)
  - `async def send_document(self, target, path, caption=None)` (4)
  - `async def read_chat_history(self, target)` (3)
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

### `tests/fakes/ui_bot.py` — 104 строк

Бот, каким его видит окно: обращения, которые делает мост.

Зависит от: —

- `class Sent` (4)
- `class UiBot` (71)
  - `def _refuse_if_asked(self) -> None` (3)
  - `async def force_poll_once(self) -> str` (3)
  - `def cancel_current_poll(self) -> None` (2)
  - `def request_stop(self) -> None` (2)
  - `async def ui_rerun_vacancy_pipeline(self, vacancy_id: int) -> str` (3)
  - `async def ui_send_vacancy_application(self, vacancy_id: int) -> tuple[bool, str]` (3)
  - `async def ui_forget_vacancy(self, vacancy_id: int) -> bool` (3)
  - `async def mark_hr_chat_read(self, hr_id: int) -> int` (3)
  - `async def send_to_hr_chat(self, hr_id: int, text: str) -> Sent` (4)
  - `async def send_to_hr_media(self, hr_id: int, file_path: str) -> Sent` (4)
  - `async def log_out_session(self) -> None` (4)
  - `async def poll_channel_now(self, channel_id: int) -> str` (3)
  - `async def delete_channel(self, channel_id: int) -> int | None` (3)
  - `async def add_channel(self, username: str) -> tuple[int | None, str]` (3)

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


### `tests/test_harness_safety.py` — 118 строк

Сторож стенда: падает, если подмена не сработала.

Зависит от: `adapters.telegram`, `backend.models`, `config`, `tests.conftest`

Тестов: 9


## tools — 26 модулей

### `tools/mutate.py` — 250 строк

Точечные мутации: сломать одну строку, прогнать тесты, откатить.

Зависит от: —

- `def _child_env() -> dict[str, str]` (18)
- `def run_tests(test_path: str) -> tuple[bool, str]` (15)
- `def drop_bytecode_cache(names: list[str]) -> None` (9)
- `def restore_command(names: list[str]) -> str` (3)
- `def dirty_files(names: list[str]) -> list[str] | None` (11)
- `def restore(path: Path, snapshot: bytes, context: str) -> None` (7)
- `def preflight(targets: list[str]) -> bool` (24)
- `def load_mutations(set_name: str) -> list[tuple[str, str, str]]` (17)
- `def run_mutations(mutations, snapshots: dict[str, bytes], test_path: str)` (32)
- `def files_match_snapshots(snapshots: dict[str, bytes]) -> bool` (13)
- `def main() -> int` (39)

### `tools/mutations/blacklist.py` — 184 строк

Поломки для ведения чёрного списка и для отметки, которую он ставит.

Зависит от: —


### `tools/mutations/blacklist_marks.py` — 39 строк

Поломки для `backend/repository/blacklist_marks.py`.

Зависит от: —


### `tools/mutations/bot_lifecycle.py` — 166 строк

Поломки для жизни бота: сигналы, каналы, место прогона, оборот цикла.

Зависит от: —


### `tools/mutations/bot_media.py` — 148 строк

Поломки для вложений в `backend/bot/`: способ отправки, пути, скачивание.

Зависит от: —


### `tools/mutations/bot_messages.py` — 332 строк ⚠ подошёл к 300

Поломки для всего, что бот пишет и читает в личных переписках.

Зависит от: —


### `tools/mutations/companies.py` — 278 строк

Поломки для `backend/repository/companies_keys.py`, `companies_matching.py`,

Зависит от: —


### `tools/mutations/entry_points.py` — 208 строк

Поломки для входных точек: соединение с базой, клиент Telegram, запуск.

Зависит от: —


### `tools/mutations/flows_channels.py` — 208 строк

Поломки для обхода каналов в `backend/flows/channels.py`.

Зависит от: —


### `tools/mutations/flows_dm.py` — 256 строк

Поломки для разбора личных сообщений в `backend/flows/dm.py`.

Зависит от: —


### `tools/mutations/flows_vacancy.py` — 317 строк ⚠ подошёл к 300

Поломки для работы с вакансией — в разборе и в записи его исхода.

Зависит от: —


### `tools/mutations/form_payloads.py` — 64 строк

Поломки для чтения нагрузок форм окна — `client/bridge/form_payloads.py`.

Зависит от: —


### `tools/mutations/hr.py` — 234 строк

Поломки для `backend/repository/hr_identify.py`, `hr_list.py`, `hr_card.py`

Зависит от: —


### `tools/mutations/llm.py` — 461 строк ⚠ подошёл к 300

Поломки для пакета `backend/llm/`.

Зависит от: —


### `tools/mutations/lm_studio.py` — 80 строк

Поломки для клиента провайдера моделей `adapters/lm_studio.py`.

Зависит от: —


### `tools/mutations/log_buffer.py` — 74 строк

Поломки для буфера логов, которым живёт экран «Логи».

Зависит от: —


### `tools/mutations/message_text.py` — 64 строк

Поломки для текста сообщения `backend/message_text.py`.

Зависит от: —


### `tools/mutations/messages_channels.py` — 252 строк

Поломки для `backend/repository/messages.py` и `channels.py`.

Зависит от: —


### `tools/mutations/profile.py` — 249 строк

Поломки для `backend/repository/profile.py`.

Зависит от: —


### `tools/mutations/runtime_settings.py` — 64 строк

Поломки для `backend/runtime_settings.py`.

Зависит от: —


### `tools/mutations/salary.py` — 130 строк

Поломки для разбора строки зарплаты.

Зависит от: —


### `tools/mutations/stats.py` — 281 строк

Поломки для `backend/repository/stats_summary.py` и `stats_pipeline.py`.

Зависит от: —


### `tools/mutations/telegram_identity.py` — 65 строк

Поломки для правил ника `backend/domain/telegram_identity.py`.

Зависит от: —


### `tools/mutations/telegram_login.py` — 84 строк

Поломки для `backend/telegram_login.py`.

Зависит от: —


### `tools/mutations/telegram_lookup.py` — 22 строк

Поломки для походов в Telegram `backend/telegram_lookup.py`.

Зависит от: —


### `tools/mutations/vacancies.py` — 247 строк

Поломки для четырёх модулей `backend/repository/vacancies_*.py`.

Зависит от: —


## Абстракции с одной реализацией

- `ChannelActions` — наследник один: `Channels`
- `Cv` — наследник один: `Profile`
- `Desktop` — наследник один: `System`
- `HrChat` — наследник один: `Hr`
- `Journal` — наследник один: `System`
- `Llm` — наследник один: `Settings`
- `Login` — наследник один: `Settings`
- `Silent` — наследник один: `Stoppable`
- `VacancyActions` — наследник один: `Vacancies`
- `VacancyLinks` — наследник один: `Vacancies`
- `Wipe` — наследник один: `System`
