"""QWebChannel bridge between the wizard UI (JS) and Python.

Pyrogram and httpx are async, Qt's event loop is not — so we run a single
asyncio loop in a background thread and schedule coroutines onto it from
the @Slot methods. Results come back to JS via Qt signals.

Slots return immediately; JS connects to the matching signal to receive
the JSON result.

SECURITY — cleartext secrets through QWebChannel:
Несколько slot'ов сознательно отдают plaintext-секреты во фронт (это
single-user app, JS живёт в embedded WebView, не по сети):
- ``initial_state`` / ``request_system_settings`` — chat/embed api_key,
  Telegram api_id+api_hash, расшифрованный CV-path.
- ``request_profile`` — PII профиля (email, phone, telegram_username,
  github_url, location, education) + абсолютный путь к CV.
Прежде чем добавлять новые slot'ы, отдающие секреты, подумайте:
заслуживает ли поле статус «можно вернуть как есть», или его лучше
скрыть/подменить (eye-toggle паттерн на UI). Audit-trail см. git blame
по соответствующим slot'ам.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import sqlite3
import threading
import time
from concurrent.futures import CancelledError, Future
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Coroutine

import httpx
from PySide6.QtCore import QObject, QTimer, QUrl, Signal, Slot
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QMainWindow,
    QWidget,
)
from sqlalchemy import func, select, text as sa_text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from adapters import lm_studio
from adapters.lm_studio import LlmProviderConfig
from backend.repository import blacklist, blacklist_candidates, channels as channels_repo, companies_card, companies_list, hr_card, hr_identify, hr_list, messages as messages_repo, profile as profile_repo, stats_pipeline, stats_summary, vacancies_card, vacancies_life, vacancies_list, vacancies_mini  # три псевдонима: имена заняты локальными переменными
from backend.payloads import text_or_none as _none_if_empty
from client.form_payloads import hr_is_identified, read_company_spellings, read_new_company_fields, read_new_hr_fields
from backend.llm.cv import parse_cv
from backend.domain.scoring import build_skill_lookup, skill_key
from backend.domain.taxonomy import GRADES, LANGUAGE_LEVELS, WORK_FORMATS
from backend.domain.telegram_identity import normalize_username
from backend.payloads import VacancyFilter
from backend.models import (
    BLACKLIST_KINDS,
    Blacklist,
    BotMode,
    Company,
    HR,
    TelegramChannel,
    Vacancy,
    VacancyStatus,
    VacancyStatusHistory,
)
from backend.telegram_login import TelegramLogin, username_of
from backend.runtime_settings import RuntimeSettings


logger = logging.getLogger(__name__)


# === Async runner =========================================================


class AsyncRunner:
    """Owns an asyncio loop running in a background thread."""

    def __init__(self) -> None:
        self.loop = asyncio.new_event_loop()
        self._thread = threading.Thread(
            target=self._run_loop, daemon=True, name="WizardAsyncLoop"
        )
        self._thread.start()
        logger.info("AsyncRunner started (thread=%s)", self._thread.name)

    def _run_loop(self) -> None:
        asyncio.set_event_loop(self.loop)
        # Pyrogram'ский race во время shutdown / log_out: внутренний таск
        # Client.handle_updates догоняет с update'ом для уже закрытой
        # SQLite-storage / стопнутого loop'а / частично-разобранного
        # клиента. Делать тут нечего — apply'нуть уже не во что,
        # фильтруем шум, чтобы он не прыгал в stderr и не пугал юзера.
        # Список расширен по review-concurrency.md M4: помимо
        # ProgrammingError("closed database") теперь глушатся и
        # RuntimeError("Event loop is closed"), и AttributeError на
        # частично-разобранных Pyrogram-объектах при teardown'е.
        def _quiet_pyrogram_shutdown(loop, context):
            exc = context.get("exception")
            msg = str(exc) if exc else ""
            # WARNING (а не DEBUG): если эти исключения всплывают вне
            # shutdown'а — это значит мы где-то закрыли DB-pool / loop
            # рано, и тихий DEBUG это спрячет. WARNING шумит ровно один
            # раз на teardown — приемлемо. Если ловите эти warning'и не
            # при выходе из приложения / log_out / delete_all_data —
            # значит появился реальный bug.
            if isinstance(exc, sqlite3.ProgrammingError) and \
               "closed database" in msg:
                logger.warning("Pyrogram shutdown race swallowed: %s", exc)
                return
            if isinstance(exc, RuntimeError) and \
               "Event loop is closed" in msg:
                logger.warning("Pyrogram shutdown race swallowed: %s", exc)
                return
            if isinstance(exc, AttributeError):
                # AttributeError при teardown'е остаётся DEBUG — самый шумный
                # из трёх (pyrogram дёргает self.<attr> на уже-обнулённом
                # объекте по нескольку раз за teardown). WARNING'и от sqlite3/
                # RuntimeError выше — точечный сигнал «бд/loop закрыты вне
                # shutdown'а», AttributeError диагностически слабее.
                logger.debug("AttributeError during teardown swallowed: %s", exc)
                return
            loop.default_exception_handler(context)
        self.loop.set_exception_handler(_quiet_pyrogram_shutdown)
        self.loop.run_forever()

    def submit(self, coro: Coroutine[Any, Any, Any]) -> Future:
        return asyncio.run_coroutine_threadsafe(coro, self.loop)

    def stop(self) -> None:
        if not self.loop.is_running():
            return
        logger.info("AsyncRunner stopping")
        # Cancel pending tasks so aclose / disconnect handlers в finally
        # блоках Bot.run / IngestionPipeline получают шанс отработать
        # до смерти loop'а. Таймаут расширен с 3с до 15с — Bot.run
        # finally делает `await client.stop()` Pyrogram'а + два
        # `await lm_*.aclose()`, на flaky-сети это легко 5-10с.
        # Раньше cancel_pending уезжал по таймауту и тут же loop.stop()
        # рубил cleanup'ы посередине.
        async def _cancel_pending() -> None:
            tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
            for t in tasks:
                t.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
        try:
            asyncio.run_coroutine_threadsafe(_cancel_pending(), self.loop).result(timeout=15)
        except Exception:
            logger.exception("AsyncRunner: cancel_pending failed during stop")
        self.loop.call_soon_threadsafe(self.loop.stop)
        self._thread.join(timeout=15)
        if self._thread.is_alive():
            logger.warning("AsyncRunner thread did not exit within 15s join timeout")


# === Bridge ===============================================================


def _ok(data: dict | None = None) -> str:
    return json.dumps({"ok": True, **(data or {})})


def _err(message: str, **extra: Any) -> str:
    return json.dumps({"ok": False, "error": message, **extra})


def _iso(dt: datetime | None) -> str | None:
    """ISO-8601 с обязательным TZ-суффиксом, под JS `Date.parse`.

    SQLite + ``DateTime(timezone=True)`` хранит как text. Строки, записанные
    через ``server_default=func.now()`` (vacancy_status_history.changed_at,
    vacancy_event.created_at и т.п.) приходят обратно naive — без offset'а.
    Голый ``.isoformat()`` шлёт `"2026-05-07T12:34:56"` без `Z`/`+00:00`,
    а `Date.parse` без TZ интерпретирует строку как ЛОКАЛЬНОЕ время —
    свежий эвент превращается в «N часов назад» на величину TZ-оффсета.
    Naive значения трактуем как UTC (потому что вся запись идёт в UTC),
    aware — отдаём как есть.
    """
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


async def _do_list_models_for_creds(
    base_url: str, api_key: str, *, kind: str | None = None
) -> dict:
    """Best-effort fetch списка моделей. Никогда не raise — на ошибку
    отдаём {ok: False, error: ...}, на успех — {ok: True, models: [...]}.
    Если ``kind`` задан, передаём в адаптер для type-фильтра (LM Studio
    API v0 различает llm / embeddings).
    """
    cfg = LlmProviderConfig(base_url=base_url, api_key=api_key, model="x")
    client = lm_studio.make_client(cfg)
    try:
        models = await lm_studio.list_models(client, kind=kind)
        return {"ok": True, "models": models}
    except Exception as e:
        # httpx иногда сериализует request включая Authorization-header
        # в repr exception'а. Прогоняем через root-logger SecretRedaction-
        # Filter руками — он висит на root, но мы тут просто текст
        # формируем без logger.* вызова.
        from backend.log_buffer import _redact
        return {"ok": False, "error": _redact(f"{type(e).__name__}: {e}")}
    finally:
        await client.aclose()


async def _do_llm_probe(
    cfg: LlmProviderConfig,
    check_fn: Callable[[httpx.AsyncClient, str], Any],
) -> tuple[bool, str, list[str], int]:
    """Запускает chat/embed-проверку и возвращает кортеж (ok, detail, models, latency_ms).

    Используется и WizardApi._make_llm_check, и MainApi.request_llm_probe.
    `client.aclose()` гарантирован через finally — иначе при cancellation
    httpx-сокет утекает.
    """
    client = lm_studio.make_client(cfg)
    t0 = time.monotonic()
    try:
        ok, detail = await check_fn(client, cfg.model)
        latency_ms = int((time.monotonic() - t0) * 1000)
        models: list[str] = []
        if ok:
            try:
                models = await lm_studio.list_models(client)
            except Exception as e:
                logger.debug("post-check list_models failed: %s", e)
        return ok, detail, models, latency_ms
    finally:
        await client.aclose()


def _dispatch_json(api, signal: Signal, coro: Coroutine[Any, Any, Any]) -> None:
    """Отправить корутину на runner и отдать её ответ окну сигналом.

    Объявлено один раз на оба класса: общие чтения нагрузки зовут отправку,
    не зная, у какого из них они в руках, — а разойдись эти отправки, у
    мастера и настроек разошлось бы и поведение при закрытии окна.

    Отмену при остановке не показываем: обработчик в окне к этому мигу уже
    отвалился, и «CancelledError» уходило бы в умирающую страницу. Обе
    породы отмены ловятся вместе — runner отдаёт свою, корутина свою.
    """
    future = api._runner.submit(coro)

    def on_done(f: Future) -> None:
        try:
            payload = f.result()
        except (CancelledError, asyncio.CancelledError):
            return
        except Exception as e:
            logger.exception(
                "bridge: unexpected error in coroutine %s",
                getattr(coro, "__qualname__", "?"),
            )
            payload = _err(f"{type(e).__name__}: {e}")
        signal.emit(payload)

    future.add_done_callback(on_done)


async def _login_json(step_coro) -> str:
    """Дождаться шага входа в Telegram и перевести его исход в ответ окну."""
    step = await step_coro
    return _err(step.error) if step.error is not None else _ok(step.payload)


def _login_send_code(api, payload_json: str) -> None:
    """Запросить код входа по нагрузке формы.

    Три чтения нагрузки живут здесь, а не в классах: слоты нужны обоим —
    мастеру и настройкам, — а тела у них одни и те же, и разойтись им нельзя.
    """
    try:
        payload = json.loads(payload_json)
        api_id = int(payload["api_id"])
        api_hash = str(payload["api_hash"]).strip()
        phone = str(payload["phone"]).strip()
    except (KeyError, ValueError, TypeError) as e:
        _log_invalid_payload("telegram_send_code", e)
        api.telegram_send_code_done.emit(_err(f"Неверные поля: {e}"))
        return
    api._dispatch(
        api.telegram_send_code_done,
        _login_json(api._login.send_code(api_id, api_hash, phone)),
    )


def _login_confirm_code(api, payload_json: str) -> None:
    """Подтвердить код входа по нагрузке формы."""
    try:
        code = str(json.loads(payload_json)["code"]).strip()
    except (KeyError, ValueError, TypeError) as e:
        _log_invalid_payload("telegram_confirm_code", e)
        api.telegram_confirm_code_done.emit(_err(f"Неверные поля: {e}"))
        return
    if not api._login.awaiting_code:
        api.telegram_confirm_code_done.emit(
            _err("Сначала запросите код подтверждения.")
        )
        return
    api._dispatch(
        api.telegram_confirm_code_done,
        _login_json(api._login.confirm_code(code)),
    )


def _login_confirm_password(api, payload_json: str) -> None:
    """Подтвердить облачный пароль по нагрузке формы."""
    try:
        password = str(json.loads(payload_json)["password"])
    except (KeyError, ValueError, TypeError) as e:
        _log_invalid_payload("telegram_confirm_password", e)
        api.telegram_confirm_password_done.emit(_err(f"Неверные поля: {e}"))
        return
    if not api._login.awaiting_password:
        api.telegram_confirm_password_done.emit(
            _err("Сначала пройдите шаг с кодом подтверждения.")
        )
        return
    api._dispatch(
        api.telegram_confirm_password_done,
        _login_json(api._login.confirm_password(password)),
    )


def _log_invalid_payload(slot: str, exc: Exception) -> None:
    """Стандартный WARNING для всех `_err(f"Неверные поля: {e}")` ветвей.

    Логируем только класс и текст исключения — payload может содержать
    api_key, текст сообщения, пароль; никогда не выводим его целиком.
    """
    logger.warning(
        "%s: invalid payload: %s: %s", slot, type(exc).__name__, exc
    )


def _media_url(stored_path: str | None) -> str | None:
    """Convert the ``message.media_path`` column into a ``file://`` URL the
    SPA can render. New rows hold a posix path relative to ``MEDIA_DIR``
    (e.g. ``"1/42.jpg"``); legacy rows from earlier sessions may hold an
    absolute path or a project-relative one — `is_absolute` + the bot's
    `MEDIA_DIR` cover both.
    """
    if not stored_path:
        return None
    from backend.bot.media import MEDIA_DIR
    p = Path(stored_path)
    if not p.is_absolute():
        p = (MEDIA_DIR / p).resolve()
    return p.as_uri()


class WizardApi(QObject):
    """Exposed to JS as `window.api`. All long-running ops are non-blocking;
    JS must connect to the matching `*_done` signal to get the result."""

    telegram_send_code_done = Signal(str)
    telegram_confirm_code_done = Signal(str)
    telegram_confirm_password_done = Signal(str)
    chat_check_done = Signal(str)
    chat_save_done = Signal(str)
    embed_check_done = Signal(str)
    embed_save_done = Signal(str)
    cv_save_done = Signal(str)
    finish_done = Signal(str)
    models_listed = Signal(str)

    def __init__(
        self,
        rs: RuntimeSettings,
        session_factory: async_sessionmaker,
        runner: AsyncRunner,
        parent_widget: QWidget | None = None,
        window: QMainWindow | None = None,
        on_enter_main: Callable[[], None] | None = None,
    ) -> None:
        super().__init__()
        self._rs = rs
        self._session_factory = session_factory
        self._runner = runner
        self._parent_widget = parent_widget
        self._window = window
        self._on_enter_main = on_enter_main
        self._login = TelegramLogin("job_bot_wizard", rs)

    @Slot(result=str)
    def initial_state(self) -> str:
        """Snapshot what the wizard already has in the DB so the UI can resume
        at the first incomplete step instead of starting over.

        Returns LLM api_key in cleartext — safe because this slot is only
        callable from the local Qt window (no network surface). Don't expose
        this method via any other channel without re-evaluating that.
        """
        tg = self._rs.tg
        chat = self._rs.chat
        embed = self._rs.embed
        cv_path = self._rs.cv_path
        wizard_completed = self._rs.wizard_completed

        completed: list[int] = []
        # Step 1 is "done" only if Telegram login produced a session string —
        # raw creds without a session won't let the bot connect.
        if tg is not None and getattr(tg, "session_string", None):
            completed.append(1)
        if chat is not None:
            completed.append(2)
        if embed is not None:
            completed.append(3)
        # Step 4 counts as done either when a CV path is set OR when the
        # wizard was previously finished via the "skip" branch (where cv_path
        # is intentionally empty but the step is acknowledged).
        if cv_path or wizard_completed:
            completed.append(4)

        return _ok(
            {
                "completed": completed,
                "wizard_completed": wizard_completed,
                "tg": {
                    "api_id": str(tg.api_id) if tg else "",
                    "api_hash": tg.api_hash if tg else "",
                    "phone": tg.phone if tg else "",
                    "password": tg.password if tg else "",
                },
                "chat": {
                    "base_url": chat.base_url if chat else "",
                    "api_key": chat.api_key if chat else "",
                    "model": chat.model if chat else "",
                },
                "embed": {
                    "base_url": embed.base_url if embed else "",
                    "api_key": embed.api_key if embed else "",
                    "model": embed.model if embed else "",
                },
                "cv_path": cv_path,
            }
        )

    def cleanup(self) -> None:
        """Disconnect Pyrogram session. Runner shutdown is owned by shell."""
        # Ждём здесь, а не отпускаем fire-and-forget: за `cleanup` идёт
        # закрытие окна, и незакрытый сокет пережил бы сам runner. Ходим на
        # runner только когда есть что закрывать: до входа он занят
        # запуском бота, и ждать его три секунды впустую незачем.
        if not self._login.active:
            return
        try:
            self._runner.submit(self._login.forget()).result(timeout=3)
        except Exception:
            logger.exception("WizardApi: tg disconnect on cleanup failed")

    # --- helpers -----------------------------------------------------------

    def _dispatch(self, signal: Signal, coro: Coroutine[Any, Any, Any]) -> None:
        _dispatch_json(self, signal, coro)

    # --- Telegram OTP flow -------------------------------------------------

    @Slot(str)
    def telegram_send_code(self, payload_json: str) -> None:
        _login_send_code(self, payload_json)

    @Slot(str)
    def telegram_confirm_code(self, payload_json: str) -> None:
        _login_confirm_code(self, payload_json)

    @Slot(str)
    def telegram_confirm_password(self, payload_json: str) -> None:
        _login_confirm_password(self, payload_json)

    # --- LLM check / save --------------------------------------------------

    def _make_llm_check(
        self,
        payload_json: str,
        signal: Signal,
        check_fn: Callable[[httpx.AsyncClient, str], Any],
    ) -> None:
        try:
            payload = json.loads(payload_json)
            base_url = str(payload["base_url"]).strip().rstrip("/")
            api_key = str(payload.get("api_key") or "")
            model = str(payload["model"]).strip()
        except (KeyError, ValueError, TypeError) as e:
            _log_invalid_payload("_make_llm_check", e)
            signal.emit(_err(f"Неверные поля: {e}"))
            return
        if not base_url or not model:
            signal.emit(_err("Заполните base_url и модель."))
            return

        async def run() -> str:
            cfg = LlmProviderConfig(base_url=base_url, api_key=api_key, model=model)
            ok, detail, models, _latency_ms = await _do_llm_probe(cfg, check_fn)
            if not ok:
                return _err(detail)
            return _ok({"detail": detail, "models": models})

        self._dispatch(signal, run())

    @Slot(str)
    def chat_check(self, payload_json: str) -> None:
        self._make_llm_check(payload_json, self.chat_check_done, lm_studio.check_chat)

    @Slot(str)
    def embed_check(self, payload_json: str) -> None:
        self._make_llm_check(
            payload_json, self.embed_check_done, lm_studio.check_embed
        )

    @Slot(str)
    def list_models_for(self, payload_json: str) -> None:
        """Background-fetch списка моделей провайдера; UI наполняет
        datalist для автокомплита. Best-effort: ошибки глотаем, чтобы
        юзер мог напечатать модель руками.

        Фильтруем по type/state — UX визарда и Настроек должен совпадать:
        в datalist только actually-loaded модели подходящего типа,
        иначе LM Studio тихо JIT-загружает выгруженную при первом probe.
        """
        try:
            payload = json.loads(payload_json)
            kind = str(payload.get("kind") or "")
            base_url = str(payload["base_url"]).strip().rstrip("/")
            api_key = str(payload.get("api_key") or "")
        except (KeyError, ValueError, TypeError):
            return
        if not base_url or kind not in ("chat", "embed"):
            return

        async def run() -> str:
            result = await _do_list_models_for_creds(base_url, api_key, kind=kind)
            return json.dumps({"kind": kind, **result})

        self._dispatch(self.models_listed, run())

    @Slot(str)
    def chat_save(self, payload_json: str) -> None:
        try:
            payload = json.loads(payload_json)
            base_url = str(payload["base_url"]).strip().rstrip("/")
            api_key = str(payload.get("api_key") or "")
            model = str(payload["model"]).strip()
        except (KeyError, ValueError, TypeError) as e:
            _log_invalid_payload("chat_save", e)
            self.chat_save_done.emit(_err(f"Неверные поля: {e}"))
            return

        async def run() -> str:
            await self._rs.set_chat(base_url=base_url, api_key=api_key, model=model)
            return _ok()

        self._dispatch(self.chat_save_done, run())

    @Slot(str)
    def embed_save(self, payload_json: str) -> None:
        try:
            payload = json.loads(payload_json)
            base_url = str(payload["base_url"]).strip().rstrip("/")
            api_key = str(payload.get("api_key") or "")
            model = str(payload["model"]).strip()
        except (KeyError, ValueError, TypeError) as e:
            _log_invalid_payload("embed_save", e)
            self.embed_save_done.emit(_err(f"Неверные поля: {e}"))
            return

        async def run() -> str:
            await self._rs.set_embed(base_url=base_url, api_key=api_key, model=model)
            return _ok()

        self._dispatch(self.embed_save_done, run())

    # --- CV ---------------------------------------------------------------

    @Slot(result=str)
    def pick_cv_file(self) -> str:
        path, _ = QFileDialog.getOpenFileName(
            self._parent_widget,
            "Выберите файл резюме",
            "",
            "Резюме (*.pdf *.PDF *.md *.MD *.txt *.TXT);;Все файлы (*)",
        )
        if not path:
            return _err("cancelled")
        p = Path(path)
        try:
            size = p.stat().st_size
        except OSError as e:
            return _err(f"{type(e).__name__}: {e}")
        return _ok({"path": str(p), "name": p.name, "size": size})

    @Slot(str)
    def cv_save(self, payload_json: str) -> None:
        try:
            payload = json.loads(payload_json)
            mode = str(payload.get("mode") or "").strip()
            path = str(payload.get("path") or "").strip()
        except (ValueError, TypeError) as e:
            _log_invalid_payload("cv_save", e)
            self.cv_save_done.emit(_err(f"Неверные поля: {e}"))
            return

        if mode == "skip":
            async def run_skip() -> str:
                await self._rs.set_app("cv_path", "")
                return _ok({"mode": "skip"})

            self._dispatch(self.cv_save_done, run_skip())
            return

        if not path:
            self.cv_save_done.emit(_err("Сначала выберите файл резюме."))
            return

        if mode == "attach":
            async def run_attach() -> str:
                await self._rs.set_app("cv_path", path)
                return _ok({"mode": "attach"})

            self._dispatch(self.cv_save_done, run_attach())
            return

        if mode == "parse":
            # CV parse временно отключён в wizard'е (wizard.html step 3
            # рендерит кнопку с disabled=True + «Функция находится в
            # разработке»). UI сюда не должен попасть, но если payload
            # пришёл от прямого JS-вызова или от устаревшей версии HTML —
            # отбиваем явно, не запуская PDF-парсер с известными issues
            # из feedback_*-памяти.
            self.cv_save_done.emit(
                _err("CV parsing временно отключён — выберите 'attach'.")
            )
            return

        self.cv_save_done.emit(_err(f"Неизвестный режим: {mode!r}"))

    async def _do_cv_parse_and_save(self, path: str) -> str:
        if self._rs.chat is None:
            return _err(
                "Сначала настройте чат-LLM на шаге 2 — без него парсинг невозможен."
            )

        logger.info("Parsing CV: %s", Path(path).name)
        try:
            text = _read_cv_text(Path(path))
        except Exception as e:
            return _err(f"Не удалось прочитать файл: {type(e).__name__}: {e}")
        if not text.strip():
            return _err("Файл пустой или не содержит текста.")

        chat = self._rs.chat
        client = lm_studio.make_client(chat)
        try:
            parsed = await parse_cv(text, client, chat.model)
        finally:
            await client.aclose()

        if parsed is None:
            logger.warning("CV parse: LLM returned None for %s", path)
            return _err("LLM не смогла распознать структуру резюме.")

        async with self._session_factory() as session:
            async with session.begin():
                await profile_repo.save_parsed_cv(session, parsed, cv_path=path)
        # Refresh in-memory cache so rs.cv_path reflects the just-written row.
        await self._rs.reload()
        logger.info(
            "CV parsed and saved (skills=%d, experience=%d)",
            len(parsed.skills),
            len(parsed.experience),
        )
        return _ok(
            {
                "mode": "parse",
                "skills_count": len(parsed.skills),
                "experience_count": len(parsed.experience),
            }
        )

    # --- Finish -----------------------------------------------------------

    @Slot()
    def finish(self) -> None:
        # Раньше: mark_wizard_completed здесь, до клика «Открыть Job Bot».
        # Если приложение крашилось между finish и enter_main_app, следующий
        # запуск шёл сразу в Main и юзер пропускал handoff-screen. Теперь
        # mark_wizard_completed отложен в enter_main_app — оба события
        # становятся атомарными с UX-точки зрения.
        logger.info("Wizard finish requested")
        self.finish_done.emit(_ok())

    @Slot()
    def close_window(self) -> None:
        if self._window is not None:
            self._window.close()

    @Slot()
    def enter_main_app(self) -> None:
        """Hand off from wizard to the main app — shell does the actual swap.

        ``mark_wizard_completed`` живёт здесь, а не в ``finish``: иначе при
        крахе приложения между finish и реальным переходом в Main юзер на
        следующем старте оказался бы в Main без полноценного handoff'а.
        """
        async def _mark() -> None:
            try:
                await self._rs.mark_wizard_completed()
            except Exception:
                logger.exception("mark_wizard_completed failed on enter_main_app")
        self._runner.submit(_mark())
        if self._on_enter_main is not None:
            self._on_enter_main()


# === MainApi (post-wizard window) ===========================================


_HEALTHCHECK_INTERVAL_MS = 5_000
_UNREAD_INTERVAL_MS = 15_000


class MainApi(QObject):
    """Bridge for the post-wizard main window. Owns periodic timers for
    healthcheck and unread-count, and exposes mode + ingestion controls.
    Long-running ops emit a `*_changed` / `*_finished` signal when ready."""

    health_changed = Signal(str)
    unread_changed = Signal(str)
    mode_changed = Signal(str)
    ingestion_started = Signal()
    ingestion_finished = Signal(str)
    ingestion_action_done = Signal(str)
    progress_update = Signal(str)
    profile_changed = Signal(str)
    profile_save_done = Signal(str)
    cv_replace_done = Signal(str)
    skills_changed = Signal(str)
    skills_save_done = Signal(str)
    experience_changed = Signal(str)
    experience_save_done = Signal(str)
    vacancies_changed = Signal(str)
    vacancy_detail_changed = Signal(str)
    vacancy_notes_saved = Signal(str)
    vacancy_status_saved = Signal(str)
    vacancy_history_explanation_saved = Signal(str)
    vacancy_action_done = Signal(str)
    hr_picker_loaded = Signal(str)
    company_picker_loaded = Signal(str)
    contacts_hr_list_loaded = Signal(str)
    contacts_hr_detail_loaded = Signal(str)
    contacts_hr_messages_loaded = Signal(str)
    contacts_hr_action_done = Signal(str)
    contacts_hr_messages_arrived = Signal(str)
    contacts_hr_read_receipt = Signal(str)
    contacts_hr_vacancies_loaded = Signal(str)
    contacts_hr_merge_picker_loaded = Signal(str)
    contacts_company_list_loaded = Signal(str)
    contacts_company_detail_loaded = Signal(str)
    contacts_company_vacancies_loaded = Signal(str)
    contacts_company_hrs_loaded = Signal(str)
    contacts_company_merge_picker_loaded = Signal(str)
    contacts_company_action_done = Signal(str)
    contacts_blacklist_list_loaded = Signal(str)
    contacts_blacklist_action_done = Signal(str)
    contacts_blacklist_candidates_loaded = Signal(str)
    stats_kpi_loaded = Signal(str)
    stats_status_breakdown_loaded = Signal(str)
    stats_hr_responses_loaded = Signal(str)
    stats_skills_loaded = Signal(str)
    stats_channels_pipeline_loaded = Signal(str)
    system_logs_loaded = Signal(str)
    system_log_record_pushed = Signal(str)
    system_logs_cleared = Signal(str)
    system_settings_loaded = Signal(str)
    system_telegram_logout_done = Signal(str)
    llm_probe_done = Signal(str)
    llm_models_listed = Signal(str)
    settings_save_done = Signal(str)
    delete_all_data_done = Signal(str)
    telegram_send_code_done = Signal(str)
    telegram_confirm_code_done = Signal(str)
    telegram_confirm_password_done = Signal(str)
    contacts_channel_list_loaded = Signal(str)
    contacts_channel_detail_loaded = Signal(str)
    contacts_channel_vacancies_loaded = Signal(str)
    contacts_channel_action_done = Signal(str)
    contacts_channels_changed = Signal()
    contacts_lists_changed = Signal()
    vacancies_list_changed = Signal()
    unread_chats_loaded = Signal(str)

    def __init__(
        self,
        rs: RuntimeSettings,
        session_factory: async_sessionmaker,
        runner: AsyncRunner,
        parent_widget: QWidget | None = None,
        window: QMainWindow | None = None,
        engine: AsyncEngine | None = None,
    ) -> None:
        super().__init__()
        self._rs = rs
        self._session_factory = session_factory
        self._runner = runner
        self._parent_widget = parent_widget
        self._window = window
        self._engine = engine  # для dispose() в delete_all_data
        self._bot = None
        self._bot_task: Future | None = None

        self._health_timer = QTimer(self)
        self._health_timer.timeout.connect(self._kick_health)
        self._health_timer.start(_HEALTHCHECK_INTERVAL_MS)

        self._unread_timer = QTimer(self)
        self._unread_timer.timeout.connect(self._kick_unread)
        self._unread_timer.start(_UNREAD_INTERVAL_MS)

        # Hook log-buffer → Qt signal: each new LogRecord pushed (debounce
        # is on the JS side via existing patterns). Emit must be JSON-string
        # for Signal(str), so serialize the entry inline. Push gated на
        # `_logs_subscribed` flag — ставится из JS при заходе на logs-tab,
        # снимается при уходе/выключении auto-refresh, чтобы не сжигать
        # JSON-сериализацию + cross-thread dispatch на чужих экранах.
        # Вход через экран «Настройки» держит свой временный клиент —
        # отдельный от `self._bot._client`, который стартует позже. Имя
        # сессии тоже своё: под общим они делили бы один файл.
        self._login = TelegramLogin(
            "job_bot_relogin", rs, on_saved=self._after_login_saved
        )
        # Кэш TG-username: бот стартует медленно (Pyrogram session-load
        # + connect — секунды), а UI запрашивает settings сразу после
        # логина или открытия таба. Кэш заполняется при успешном get_me()
        # (или сразу после re-login) и переживает несколько запросов
        # пока bot._client не поднимется.
        self._username_cache: str = ""
        self._logs_subscribed = False
        from backend.log_buffer import get_handler
        # Recursion-guard: если внутри _on_record логнуть warning, тот warning
        # снова попадёт в LogBufferHandler.emit → on_record → бесконечная
        # рекурсия. Флаг блокирует повторный вход.
        _on_record_in_flight = {"v": False}
        def _on_record(entry: dict) -> None:
            if not self._logs_subscribed:
                return
            try:
                self.system_log_record_pushed.emit(json.dumps(entry))
            except Exception:
                if _on_record_in_flight["v"]:
                    return
                _on_record_in_flight["v"] = True
                try:
                    logger.warning(
                        "LogBuffer on_record callback failed", exc_info=True,
                    )
                finally:
                    _on_record_in_flight["v"] = False
        get_handler().on_record = _on_record

        # Без session_string Pyrogram свалится в interactive-login на stdin
        # (запрашивает код подтверждения в терминале). Бот стартанём только
        # после того, как пользователь авторизуется через UI («Войти»).
        if rs.tg is not None and rs.tg.session_string:
            self._start_bot()
        else:
            logger.info("No TG session — bot start deferred until user logs in via Settings")

    def _start_bot(self) -> None:
        """Construct AND run the Bot inside the runner loop.

        Constructing on the Qt thread used to crash silently — Pyrogram's
        SQLite session storage is thread-affine, and any exception from
        a coroutine submitted via `submit()` sits in the Future without a
        callback to surface it.
        """
        async def _build_and_run() -> None:
            from backend.bot.client import Bot

            logger.info("Constructing Bot and starting run loop")
            self._bot = Bot(self._rs, self._session_factory)
            def _on_cycle_start() -> None:
                self.ingestion_started.emit()

            def _on_cycle_end() -> None:
                self.ingestion_finished.emit(_ok())
                self._kick_unread()

            self._bot.on_cycle_start = _on_cycle_start
            self._bot.on_cycle_end = _on_cycle_end
            self._bot.on_progress = lambda stage, label, cur, tot: (
                self.progress_update.emit(json.dumps(
                    {"stage": stage, "label": label, "current": cur, "total": tot}
                ))
            )
            def _on_new_msg(hr_id: int) -> None:
                self.contacts_hr_messages_arrived.emit(_ok({"hr_id": hr_id}))
                self._kick_unread()
            self._bot.on_new_message = _on_new_msg

            def _on_hr_read(hr_id: int, max_tg_id: int) -> None:
                self.contacts_hr_read_receipt.emit(_ok({
                    "hr_id": hr_id,
                    "max_tg_id": max_tg_id,
                }))
            self._bot.on_hr_read = _on_hr_read

            def _on_channels_changed() -> None:
                self.contacts_channels_changed.emit()
            self._bot.on_channels_changed = _on_channels_changed

            def _on_contacts_changed() -> None:
                self.contacts_lists_changed.emit()
            self._bot.on_contacts_changed = _on_contacts_changed

            def _on_vacancies_changed() -> None:
                self.vacancies_list_changed.emit()
            self._bot.on_vacancies_changed = _on_vacancies_changed
            await self._bot.run()

        future = self._runner.submit(_build_and_run())

        def _log_if_crashed(f: Future) -> None:
            exc = f.exception()
            if exc is not None:
                logger.critical("Bot crashed — UI is now zombie", exc_info=exc)

        future.add_done_callback(_log_if_crashed)
        self._bot_task = future

    # --- helpers ----------------------------------------------------------

    def _dispatch(self, signal: Signal, coro: Coroutine[Any, Any, Any]) -> None:
        _dispatch_json(self, signal, coro)

    def _dispatch_action(
        self,
        signal: Signal,
        coro: Coroutine[Any, Any, str],
        *,
        action: str,
        **error_extra,
    ) -> None:
        """Like ``_dispatch``, but wraps the coroutine so an unexpected
        exception is converted to a structured ``_err`` payload carrying
        the ``action`` discriminator + caller-provided extras (typically
        ``channel_id``). Without this, an exception lands in ``_dispatch``'s
        outer except and is emitted as a bare ``_err(message)`` without
        ``action`` — the JS handler then can't route it to the right branch
        and the UI ends up stuck (spinner stays / saving=true / popover
        ghost / optimistic flip never rolled back).
        """
        async def safe() -> str:
            try:
                return await coro
            except Exception as e:
                logger.exception("MainApi: action %s failed", action)
                return _err(f"{type(e).__name__}: {e}", action=action, **error_extra)
        self._dispatch(signal, safe())

    # --- Public slots -----------------------------------------------------

    @Slot()
    def request_initial(self) -> None:
        """Push every cached state to JS via signals — called once on UI boot."""
        self._kick_health()
        self._kick_unread()
        self._kick_mode()

    @Slot(str)
    def set_mode(self, mode_str: str) -> None:
        try:
            mode = BotMode(mode_str)
        except ValueError:
            logger.warning("set_mode: unknown mode requested: %r", mode_str)
            self.mode_changed.emit(_err(f"Неизвестный режим: {mode_str!r}"))
            return

        logger.info("Mode change requested: %s", mode.value)
        async def run() -> str:
            await self._rs.set_mode(mode)
            # Wake the bot so it picks up the new mode without waiting for
            # the next poll tick.
            if self._bot is not None:
                self._bot.kick()
            return _ok({"mode": mode.value})

        self._dispatch(self.mode_changed, run())

    @Slot()
    def trigger_ingestion(self) -> None:
        """Refresh button — force a one-shot poll regardless of bot mode.

        Если уже идёт другой цикл — показываем toast «уже идёт цикл,
        пропустил», иначе пользователь жмёт кнопку и не понимает почему
        ничего не происходит.
        """
        if self._bot is None:
            return
        logger.info("Manual ingestion triggered")

        async def run() -> str:
            status = await self._bot.force_poll_once()
            if status == "busy":
                return _err("Уже идёт другой цикл, попробуйте позже.", action="trigger_ingestion", status=status)
            if status == "ok":
                return _ok({"action": "trigger_ingestion", "status": status})
            messages = {
                "cancelled": "Поллинг отменён.",
                "error": "Не удалось прогнать каналы — см. логи.",
            }
            return _err(messages.get(status, "Не удалось прогнать."), action="trigger_ingestion", status=status)

        self._dispatch(self.ingestion_action_done, run())

    @Slot()
    def stop_ingestion(self) -> None:
        """Stop button — cancel the in-flight poll cycle (if any)."""
        if self._bot is None:
            return
        logger.info("Ingestion cancel requested")
        self._bot.cancel_current_poll()

    # --- Profile / CV ---------------------------------------------------

    @Slot()
    def request_profile(self) -> None:
        """Push the current Profile + CV path to JS."""
        async def run() -> str:
            async with self._session_factory() as session:
                profile = await profile_repo.get_profile(session)
                languages = (
                    await profile_repo.list_profile_languages(session)
                    if profile is not None
                    else []
                )
            cv_path = self._rs.cv_path
            cv_meta = _stat_cv(cv_path)
            return _ok(
                {
                    "profile": _profile_to_dict(profile, languages),
                    "cv_path": cv_path,
                    "cv_meta": cv_meta,
                }
            )

        self._dispatch(self.profile_changed, run())

    @Slot(str)
    def save_profile(self, payload_json: str) -> None:
        try:
            payload = json.loads(payload_json)
            fields = {
                "first_name": str(payload.get("first_name") or "").strip(),
                "last_name": str(payload.get("last_name") or "").strip(),
                "title": str(payload.get("title") or "").strip(),
                "email": str(payload.get("email") or "").strip(),
                "phone": _none_if_empty(payload.get("phone")),
                "location": _none_if_empty(payload.get("location")),
                "telegram_username": _none_if_empty(payload.get("telegram_username")),
                "github_url": _none_if_empty(payload.get("github_url")),
                "education": _none_if_empty(payload.get("education")),
                "free_preferences": _none_if_empty(payload.get("free_preferences")),
                "grades": _filter_set(payload.get("grades"), GRADES),
                "work_format": _filter_set(
                    payload.get("work_format"), WORK_FORMATS
                ),
            }
            languages = _filter_languages(payload.get("languages"))
        except (ValueError, TypeError) as e:
            _log_invalid_payload("save_profile", e)
            self.profile_save_done.emit(_err(f"Неверные поля: {e}"))
            return

        for required in ("first_name", "last_name", "title", "email"):
            if not fields[required]:
                self.profile_save_done.emit(
                    _err(f"Поле '{required}' обязательно.")
                )
                return

        async def run() -> str:
            async with self._session_factory() as session:
                async with session.begin():
                    profile = await profile_repo.upsert_profile(
                        session, **fields
                    )
                    await profile_repo.replace_profile_languages(
                        session, profile.id, languages
                    )
            return _ok()

        self._dispatch(self.profile_save_done, run())

    @Slot(result=str)
    def pick_cv_file_main(self) -> str:
        """File picker for replacing the CV. Returns the selected file's
        metadata (path + name + size) without saving anything."""
        path, _ = QFileDialog.getOpenFileName(
            self._parent_widget,
            "Выберите файл резюме",
            "",
            "Резюме (*.pdf *.PDF *.md *.MD *.txt *.TXT);;Все файлы (*)",
        )
        if not path:
            return _err("cancelled")
        return _ok({"path": path, **(_stat_cv(path) or {})})

    @Slot(str)
    def replace_cv(self, payload_json: str) -> None:
        try:
            payload = json.loads(payload_json)
            path = str(payload.get("path") or "").strip()
        except (ValueError, TypeError) as e:
            _log_invalid_payload("replace_cv", e)
            self.cv_replace_done.emit(_err(f"Неверные поля: {e}"))
            return
        if not path:
            self.cv_replace_done.emit(_err("Путь пустой."))
            return

        async def run() -> str:
            await self._rs.set_app("cv_path", path)
            return _ok({"path": path, **(_stat_cv(path) or {})})

        self._dispatch(self.cv_replace_done, run())

    @Slot()
    def open_cv_file(self) -> None:
        """Open the current CV with the OS-default application."""
        cv_path = self._rs.cv_path
        if not cv_path:
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(cv_path).resolve())))

    @Slot(str)
    def open_external_url(self, url: str) -> None:
        """Hand a URL off to the OS-default browser / Telegram client.

        Used by the vacancies UI for "go to source post"
        (vacancy.source_url) and "DM the HR" (https://t.me/{username})
        actions — QWebEngineView swallows ``<a target="_blank">`` clicks
        by default, so the JS side calls this slot instead.
        """
        if not url:
            return
        QDesktopServices.openUrl(QUrl(url))

    @Slot(str)
    def copy_to_clipboard(self, text: str) -> None:
        """Копирование в системный буфер для WebEngine UI (Clipboard API там часто недоступен)."""
        cb = QApplication.clipboard()
        if cb:
            cb.setText(text or "")

    # --- Skills ---------------------------------------------------------

    @Slot()
    def request_skills(self) -> None:
        async def run() -> str:
            async with self._session_factory() as session:
                rows = await profile_repo.list_skills(session)
            return _ok({"skills": [_skill_to_dict(s) for s in rows]})

        self._dispatch(self.skills_changed, run())

    @Slot(str)
    def save_skills(self, payload_json: str) -> None:
        try:
            payload = json.loads(payload_json)
            rows = payload.get("skills") or []
            if not isinstance(rows, list):
                raise ValueError("skills must be a list")
        except (ValueError, TypeError) as e:
            _log_invalid_payload("save_skills", e)
            self.skills_save_done.emit(_err(f"Неверные поля: {e}"))
            return

        async def run() -> str:
            async with self._session_factory() as session:
                async with session.begin():
                    profile = await profile_repo.get_profile(session)
                    if profile is None:
                        return _err("Сначала сохраните профайл (CV-таб).")
                    await profile_repo.save_skills(session, rows, profile.id)
            return _ok()

        self._dispatch(self.skills_save_done, run())

    # --- Experience -----------------------------------------------------

    @Slot()
    def request_experience(self) -> None:
        async def run() -> str:
            async with self._session_factory() as session:
                exps = await profile_repo.list_experience(session)
                skills = await profile_repo.list_skills(session)
            return _ok(
                {
                    "experience": [_exp_to_dict(e) for e in exps],
                    "skills_index": [_skill_to_dict(s) for s in skills],
                }
            )

        self._dispatch(self.experience_changed, run())

    @Slot(str)
    def save_experience(self, payload_json: str) -> None:
        try:
            payload = json.loads(payload_json)
            rows = payload.get("experience") or []
            if not isinstance(rows, list):
                raise ValueError("experience must be a list")
        except (ValueError, TypeError) as e:
            _log_invalid_payload("save_experience", e)
            self.experience_save_done.emit(_err(f"Неверные поля: {e}"))
            return

        async def run() -> str:
            try:
                async with self._session_factory() as session:
                    async with session.begin():
                        profile = await profile_repo.get_profile(session)
                        if profile is None:
                            return _err("Сначала сохраните профайл (CV-таб).")
                        await profile_repo.save_experience(session, rows, profile.id)
                return _ok()
            except profile_repo.SaveExperienceError as e:
                return _err(str(e))

        self._dispatch(self.experience_save_done, run())

    # --- Vacancies ------------------------------------------------------

    @Slot(str)
    def request_vacancies(self, payload_json: str = "") -> None:
        """Push the vacancy list to JS, applying sort + search server-side.

        Slice 2: minimal row-shape only (id, status, score, title, company,
        grade, salary, stack, posted_at, created_at). Each stack item is
        marked ``matched`` if it's in the profile's skills/aliases set, so
        the UI can highlight relevant chips without needing a separate
        skills request.

        ``payload_json`` is a JSON object: ``{sort, search}``. Empty / invalid
        payload falls back to defaults (``sort="newest"``, no search). The
        payload format is forward-compatible — additional filter keys
        (statuses, channels, dates, etc.) will be added in following slices
        without changing the slot signature.
        """
        try:
            payload = json.loads(payload_json) if payload_json else {}
        except (TypeError, ValueError):
            payload = {}
        sort_key = payload.get("sort") or "newest"
        search = payload.get("search") or None

        def _list(key: str) -> list[str] | None:
            raw = payload.get(key)
            if not isinstance(raw, list):
                return None
            cleaned = [str(x) for x in raw if x]
            return cleaned or None

        def _int(key: str) -> int | None:
            raw = payload.get(key)
            if raw in (None, ""):
                return None
            try:
                return int(raw)
            except (TypeError, ValueError):
                return None

        def _float(key: str) -> float | None:
            raw = payload.get(key)
            if raw in (None, ""):
                return None
            try:
                return float(raw)
            except (TypeError, ValueError):
                return None

        def _datetime(key: str) -> datetime | None:
            raw = payload.get(key)
            if not raw:
                return None
            text = str(raw)
            # JS Date.toISOString emits a trailing 'Z'; older Pythons reject
            # it on fromisoformat. 3.11+ handles it, but normalize anyway.
            if text.endswith("Z"):
                text = text[:-1] + "+00:00"
            try:
                return datetime.fromisoformat(text)
            except ValueError:
                return None

        statuses = _list("statuses")
        channels = _list("channels")
        companies = _list("companies")
        score_min = _int("score_min")
        score_max = _int("score_max")
        salary_min = _float("salary_min")
        salary_max = _float("salary_max")
        grade = (payload.get("grade") or None)
        remote = (payload.get("remote") or None)
        hr_contact = (payload.get("hr_contact") or None)
        date_from = _datetime("date_from")
        date_to = _datetime("date_to")
        limit = _int("limit")
        offset = _int("offset") or 0
        # Валидируем mode по белому списку: иначе опечатка из JS вернётся
        # эхом, фронт получит mode='apend' и трактует как replace, тихо
        # потеряв append-страницу.
        mode_raw = str(payload.get("mode") or "replace")
        mode = mode_raw if mode_raw in {"replace", "append", "refresh"} else "replace"
        epoch = _int("epoch")

        async def run() -> str:
            async with self._session_factory() as session:
                rows = await vacancies_list.list_vacancies(
                    session,
                    VacancyFilter(
                        sort=sort_key,
                        search=search,
                        statuses=statuses,
                        channels=channels,
                        companies=companies,
                        score_min=score_min,
                        score_max=score_max,
                        salary_min=salary_min,
                        salary_max=salary_max,
                        grade=grade,
                        remote=remote,
                        hr_contact=hr_contact,
                        date_from=date_from,
                        date_to=date_to,
                        limit=limit,
                        offset=offset,
                    ),
                )
                skills = await profile_repo.list_skills(session)
                activity_by_id = await vacancies_list.list_vacancy_last_activity(
                    session, [v.id for v in rows]
                )
                # Filter-popover dropdown sources are intentionally fetched
                # independent of the active filters — otherwise applying any
                # filter would shrink the channels/companies dropdowns to
                # whatever's still in the result set.
                filter_options = await vacancies_list.list_vacancy_filter_options(session)
            matched_set = _build_matched_set(skills)
            has_more = (limit is not None) and (len(rows) == limit)
            return _ok({
                "vacancies": [
                    _vacancy_list_row_to_dict(v, matched_set, activity_by_id)
                    for v in rows
                ],
                "filter_options": filter_options,
                "has_more": has_more,
                "mode": mode,
                "offset": offset,
                "epoch": epoch,
                "score_threshold": self._rs.scoring_threshold,
            })

        self._dispatch(self.vacancies_changed, run())

    @Slot(int)
    def request_vacancy_detail(self, vacancy_id: int) -> None:
        """Push the detail-pane payload for one vacancy.

        Includes everything the detail pane will eventually need across
        slices 3–9 (description / stack / contact info / status history /
        events). Slices render only what they care about; sending the full
        shape now means no bridge churn as detail panels grow.
        """
        async def run() -> str:
            async with self._session_factory() as session:
                detail = await vacancies_card.get_vacancy_detail(session, vacancy_id)
                skills = await profile_repo.list_skills(session)
            if detail is None:
                logger.warning("vacancy_id=%d not found on detail load", vacancy_id)
                return _err("Вакансия не найдена.", id=vacancy_id)
            matched_set = _build_matched_set(skills)
            return _ok({
                "vacancy": _vacancy_detail_to_dict(
                    detail, matched_set, self._rs.scoring_threshold,
                ),
            })

        self._dispatch(self.vacancy_detail_changed, run())

    @Slot(str)
    def update_vacancy_notes(self, payload_json: str) -> None:
        """Persist a new ``notes`` value for the given vacancy.

        Emits ``vacancy_notes_saved`` with ``{ok, vacancy_id, notes}`` on
        success (UI flashes the textarea border and adopts ``notes`` as the
        save-baseline) or ``{ok: false, error}`` on failure.
        ``vacancies_card.update_vacancy_notes`` normalizes empty/whitespace-only
        ``notes`` to ``NULL`` — we echo back the post-normalization value so
        the JS baseline matches what's actually in the DB.
        """
        try:
            payload = json.loads(payload_json)
            vacancy_id = int(payload["vacancy_id"])
            notes = payload.get("notes")
            if notes is not None:
                notes = str(notes)
        except (ValueError, TypeError, KeyError) as e:
            _log_invalid_payload("update_vacancy_notes", e)
            self.vacancy_notes_saved.emit(_err(f"Неверные поля: {e}"))
            return

        async def run() -> str:
            async with self._session_factory() as session:
                async with session.begin():
                    ok = await vacancies_card.update_vacancy_notes(
                        session, vacancy_id, notes
                    )
                    persisted: str | None = None
                    if ok:
                        # Re-read the post-normalization value (NULL on
                        # whitespace-only input) so the client adopts the
                        # exact DB state as its save-baseline. Without this,
                        # any keystrokes the user typed between sending and
                        # receiving the reply would be silently dropped on
                        # the next debounce.
                        v = await session.get(Vacancy, vacancy_id)
                        if v is not None:
                            persisted = v.notes
            if not ok:
                return _err("Вакансия не найдена.", vacancy_id=vacancy_id)
            return _ok({"vacancy_id": vacancy_id, "notes": persisted})

        self._dispatch(self.vacancy_notes_saved, run())

    @Slot(str)
    def update_status_history_explanation(self, payload_json: str) -> None:
        """Edit the comment on one VacancyStatusHistory row.

        Payload: ``{vacancy_id, history_id, explanation}``. Empty/whitespace
        explanation нормализуется в NULL на бэке. Эмитит на отдельный
        ``vacancy_history_explanation_saved`` (а НЕ на ``vacancy_status_saved``),
        потому что обновление коммента не требует re-fetch detail'а — UI
        обновляет одну строку on-the-fly без потери фокуса в textarea.
        """
        try:
            payload = json.loads(payload_json)
            history_id = int(payload["history_id"])
            vacancy_id = int(payload["vacancy_id"])
            explanation = payload.get("explanation")
            if explanation is not None:
                explanation = str(explanation)
        except (ValueError, TypeError, KeyError) as e:
            _log_invalid_payload("update_status_history_explanation", e)
            self.vacancy_history_explanation_saved.emit(_err(f"Неверные поля: {e}"))
            return

        async def run() -> str:
            saved: str | None = None
            async with self._session_factory() as session:
                async with session.begin():
                    ok = await vacancies_life.update_status_history_explanation(
                        session, history_id, explanation,
                    )
                    if ok:
                        # Re-read post-normalization (NULL для empty/whitespace),
                        # чтобы UI-baseline совпадал с тем, что в DB.
                        row = await session.get(VacancyStatusHistory, history_id)
                        if row is not None:
                            saved = row.explanation
            if not ok:
                logger.warning(
                    "history_id=%d not found (vacancy=%d)",
                    history_id,
                    vacancy_id,
                )
                return _err(
                    "Запись истории не найдена.",
                    history_id=history_id,
                    vacancy_id=vacancy_id,
                )
            return _ok({
                "vacancy_id": vacancy_id,
                "history_id": history_id,
                "explanation": saved,
            })

        self._dispatch(self.vacancy_history_explanation_saved, run())

    @Slot(str)
    def change_vacancy_status(self, payload_json: str) -> None:
        """Insert a manual status-history row and optionally mutate status.

        Payload: ``{vacancy_id, status, explanation?}`` where ``status`` is
        the enum VALUE string (``"New"``, ``"In Progress"``, ...), not a CSS
        class. Emits ``vacancy_status_saved`` with ``{ok, vacancy_id}`` on
        success or ``{ok:false, error}`` on failure.
        """
        try:
            payload = json.loads(payload_json)
            vacancy_id = int(payload["vacancy_id"])
            status_raw = str(payload["status"]).strip()
            explanation = payload.get("explanation")
            if explanation is not None:
                explanation = str(explanation)
            new_status = next(
                s for s in VacancyStatus if s.value == status_raw
            )
        except StopIteration:
            self.vacancy_status_saved.emit(
                _err("Неверный статус.", vacancy_id=payload.get("vacancy_id"))
            )
            return
        except (ValueError, TypeError, KeyError) as e:
            _log_invalid_payload("change_vacancy_status", e)
            self.vacancy_status_saved.emit(_err(f"Неверные поля: {e}"))
            return

        async def run() -> str:
            async with self._session_factory() as session:
                async with session.begin():
                    row = await vacancies_life.change_vacancy_status(
                        session,
                        vacancy_id=vacancy_id,
                        new_status=new_status,
                        explanation=explanation,
                    )
            # repository returns None both for "vacancy missing" and for a true
            # no-op (same status + empty explanation). Distinguish explicitly.
            if row is None:
                async with self._session_factory() as session:
                    v = await session.get(Vacancy, vacancy_id)
                if v is None:
                    return _err("Вакансия не найдена.", vacancy_id=vacancy_id)
            return _ok({"vacancy_id": vacancy_id})

        self._dispatch(self.vacancy_status_saved, run())

    @Slot(str)
    def rerun_vacancy_pipeline(self, payload_json: str) -> None:
        """Re-run LLM parse/classify for one vacancy (§3.3 «Прогнать заново»)."""
        try:
            payload = json.loads(payload_json)
            vacancy_id = int(payload["vacancy_id"])
        except (ValueError, TypeError, KeyError) as e:
            _log_invalid_payload("rerun_vacancy_pipeline", e)
            self.vacancy_action_done.emit(_err(f"Неверные поля: {e}"))
            return

        async def run() -> str:
            if self._bot is None:
                return _err("Бот ещё не готов.")
            ok = await self._bot.ui_rerun_vacancy_pipeline(vacancy_id)
            if not ok:
                return _err(
                    "Не удалось перезапустить парсинг (нет вакансии или пустой raw_text).",
                    vacancy_id=vacancy_id,
                    action="rerun",
                )
            return _ok({"vacancy_id": vacancy_id, "action": "rerun"})

        self._dispatch(self.vacancy_action_done, run())

    @Slot(str)
    def send_vacancy_application(self, payload_json: str) -> None:
        """Manual cover-letter send для конкретной вакансии — кнопка
        «Отправить отклик». Backend сам генерит письмо, прикрепляет резюме
        и шлёт связанному HR. Skip-причины пробрасываются в UI как
        конкретные сообщения, иначе юзер не отличит реальную отправку от
        SEND_LOCKED / отсутствия CV / поломки LLM."""
        try:
            payload = json.loads(payload_json)
            vacancy_id = int(payload["vacancy_id"])
        except (ValueError, TypeError, KeyError) as e:
            _log_invalid_payload("send_vacancy_application", e)
            self.vacancy_action_done.emit(_err(f"Неверные поля: {e}"))
            return

        # Skip-коды → human-readable. Совпадает с тем, что emit'ит
        # IngestionPipeline.send_application_for_vacancy и Bot.send.
        REASONS = {
            "no_vacancy":         "Вакансия не найдена.",
            "no_hr":              "К вакансии не привязан HR.",
            "already_applied":    "Отклик по этой вакансии уже отправлен.",
            "profile_empty":      "Профиль пуст — нечем заполнить cover letter.",
            "cover_letter_failed":"Cover letter не прошёл проверку (длина / формат — см. логи).",
            "cv_missing":         "Файл резюме не найден — проверьте путь в настройках.",
            "blocked":            "Отправка заблокирована (OFF mode / blacklist / у HR нет ни id, ни @username).",
            "telegram_error":     "Telegram отказался принять сообщение (см. логи).",
            "race":               "Статус вакансии успел измениться — отправка отменена.",
        }
        # Success-коды тоже доходят до UI на случай будущих кодов
        # (sent — единственный сейчас, note=None → toast не показываем,
        # UI сам нарисует обычный success).
        SUCCESS_NOTES = {
            "sent":               None,
        }

        async def run() -> str:
            if self._bot is None:
                return _err("Бот ещё не готов.")
            ok, reason = await self._bot.ui_send_vacancy_application(vacancy_id)
            if not ok:
                msg = REASONS.get(reason, f"Не удалось отправить: {reason}")
                return _err(msg, vacancy_id=vacancy_id, action="send")
            payload = {"vacancy_id": vacancy_id, "action": "send", "reason": reason}
            note = SUCCESS_NOTES.get(reason)
            if note is not None:
                payload["note"] = note
            return _ok(payload)

        self._dispatch(self.vacancy_action_done, run())

    @Slot(str)
    def delete_vacancy(self, payload_json: str) -> None:
        """Hard-delete vacancy + history/events; nulls message.vacancy_id."""
        try:
            payload = json.loads(payload_json)
            vacancy_id = int(payload["vacancy_id"])
        except (ValueError, TypeError, KeyError) as e:
            _log_invalid_payload("delete_vacancy", e)
            self.vacancy_action_done.emit(_err(f"Неверные поля: {e}"))
            return

        async def run() -> str:
            async with self._session_factory() as session:
                async with session.begin():
                    ok = await vacancies_life.delete_vacancy(session, vacancy_id)
            if not ok:
                return _err(
                    "Вакансия не найдена.",
                    vacancy_id=vacancy_id,
                    action="delete",
                )
            return _ok({"vacancy_id": vacancy_id, "action": "delete"})

        self._dispatch(self.vacancy_action_done, run())

    # --- HR / Company pickers (§5, §6) ----------------------------------

    @Slot(str)
    def request_hr_picker(self, payload_json: str) -> None:
        """Push the HR-picker payload for the «Связать с HR» modal.

        ``vacancy_id`` is echoed back as ``current_hr_id`` (the HR currently
        linked to that vacancy, NULL if unlinked) so the JS can mark the
        active row without a second round-trip. ``search`` is server-side
        casefold-filtered (Cyrillic-safe) — see ``list_hr_with_counts``.
        """
        try:
            payload = json.loads(payload_json)
            vacancy_id = int(payload["vacancy_id"])
            search = payload.get("search")
            if search is not None:
                search = str(search)
        except (ValueError, TypeError, KeyError) as e:
            _log_invalid_payload("request_hr_picker", e)
            self.hr_picker_loaded.emit(_err(f"Неверные поля: {e}"))
            return

        async def run() -> str:
            async with self._session_factory() as session:
                rows = await hr_list.list_hr_with_counts(session, search=search)
                v = await session.get(Vacancy, vacancy_id)
                if v is None:
                    return _err("Вакансия не найдена.", vacancy_id=vacancy_id)
                payload = {
                    "vacancy_id": vacancy_id,
                    "current_hr_id": v.hr_id,
                    "search": search or "",
                    "hrs": [_hr_picker_row_to_dict(r) for r in rows],
                }
            return _ok(payload)

        self._dispatch(self.hr_picker_loaded, run())

    @Slot(str)
    def request_company_picker(self, payload_json: str) -> None:
        """Push the Company-picker payload for the «Связать с компанией» modal."""
        try:
            payload = json.loads(payload_json)
            vacancy_id = int(payload["vacancy_id"])
            search = payload.get("search")
            if search is not None:
                search = str(search)
        except (ValueError, TypeError, KeyError) as e:
            _log_invalid_payload("request_company_picker", e)
            self.company_picker_loaded.emit(_err(f"Неверные поля: {e}"))
            return

        async def run() -> str:
            async with self._session_factory() as session:
                rows = await companies_list.list_companies_with_counts(
                    session, search=search
                )
                v = await session.get(Vacancy, vacancy_id)
                if v is None:
                    return _err("Вакансия не найдена.", vacancy_id=vacancy_id)
                payload = {
                    "vacancy_id": vacancy_id,
                    "current_company_id": v.company_id,
                    "search": search or "",
                    "companies": [_company_picker_row_to_dict(r) for r in rows],
                }
            return _ok(payload)

        self._dispatch(self.company_picker_loaded, run())

    @Slot(str)
    def link_vacancy_hr(self, payload_json: str) -> None:
        """Set / unset ``vacancy.hr_id`` from the HR-picker «Связать» button.

        ``hr_id`` may be null to unlink. Reuses ``vacancy_action_done`` with
        ``action="link_hr"`` so the existing toast/refresh flow lights up.
        """
        try:
            payload = json.loads(payload_json)
            vacancy_id = int(payload["vacancy_id"])
            raw = payload.get("hr_id")
            hr_id = int(raw) if raw is not None else None
        except (ValueError, TypeError, KeyError) as e:
            _log_invalid_payload("link_vacancy_hr", e)
            self.vacancy_action_done.emit(_err(f"Неверные поля: {e}"))
            return

        async def run() -> str:
            try:
                async with self._session_factory() as session:
                    async with session.begin():
                        ok = await vacancies_card.set_vacancy_hr(
                            session, vacancy_id, hr_id
                        )
            except ValueError as e:
                return _err(str(e), vacancy_id=vacancy_id, action="link_hr")
            if not ok:
                return _err(
                    "Вакансия не найдена.",
                    vacancy_id=vacancy_id,
                    action="link_hr",
                )
            return _ok({
                "vacancy_id": vacancy_id,
                "hr_id": hr_id,
                "action": "link_hr",
            })

        self._dispatch(self.vacancy_action_done, run())

    @Slot(str)
    def link_vacancy_company(self, payload_json: str) -> None:
        """Set / unset ``vacancy.company_id`` from the Company-picker «Связать»."""
        try:
            payload = json.loads(payload_json)
            vacancy_id = int(payload["vacancy_id"])
            raw = payload.get("company_id")
            company_id = int(raw) if raw is not None else None
        except (ValueError, TypeError, KeyError) as e:
            _log_invalid_payload("link_vacancy_company", e)
            self.vacancy_action_done.emit(_err(f"Неверные поля: {e}"))
            return

        async def run() -> str:
            try:
                async with self._session_factory() as session:
                    async with session.begin():
                        ok = await vacancies_card.set_vacancy_company(
                            session, vacancy_id, company_id
                        )
            except ValueError as e:
                return _err(str(e), vacancy_id=vacancy_id, action="link_company")
            if not ok:
                return _err(
                    "Вакансия не найдена.",
                    vacancy_id=vacancy_id,
                    action="link_company",
                )
            return _ok({
                "vacancy_id": vacancy_id,
                "company_id": company_id,
                "action": "link_company",
            })

        self._dispatch(self.vacancy_action_done, run())

    @Slot(str)
    def picker_create_hr(self, payload_json: str) -> None:
        """Insert a new HR from the picker's inline-create form.

        On success, re-emits the picker list so the modal can refresh in
        place. ``created_id`` lets JS pre-select the new row; the actual
        ``vacancy.hr_id`` link still requires the user to click «Связать».
        """
        try:
            payload = json.loads(payload_json)
            vacancy_id = int(payload["vacancy_id"])
            fields = read_new_hr_fields(payload)
            search = payload.get("search")
            if search is not None:
                search = str(search)
        except (ValueError, TypeError, KeyError) as e:
            _log_invalid_payload("picker_create_hr", e)
            self.hr_picker_loaded.emit(_err(f"Неверные поля: {e}"))
            return

        if not hr_is_identified(fields):
            self.hr_picker_loaded.emit(
                _err("Укажите хотя бы имя или @username.", vacancy_id=vacancy_id)
            )
            return

        async def run() -> str:
            async with self._session_factory() as session:
                async with session.begin():
                    new_hr = await hr_identify.create_hr(session, **fields)
                    created_id = new_hr.id
                rows = await hr_list.list_hr_with_counts(session, search=search)
                v = await session.get(Vacancy, vacancy_id)
                current_hr_id = v.hr_id if v is not None else None
                payload = {
                    "vacancy_id": vacancy_id,
                    "current_hr_id": current_hr_id,
                    "search": search or "",
                    "hrs": [_hr_picker_row_to_dict(r) for r in rows],
                    "created_id": created_id,
                }
            return _ok(payload)

        self._dispatch(self.hr_picker_loaded, run())

    @Slot(str)
    def picker_create_company(self, payload_json: str) -> None:
        """Insert a new Company from the picker's inline-create form.

        Catches ``IntegrityError`` from the unique-name constraint and turns
        it into a user-facing message instead of bubbling up a SQL error.
        """
        try:
            payload = json.loads(payload_json)
            vacancy_id = int(payload["vacancy_id"])
            fields = read_new_company_fields(payload)
            name = fields["name"]
            search = payload.get("search")
            if search is not None:
                search = str(search)
        except (ValueError, TypeError, KeyError) as e:
            _log_invalid_payload("picker_create_company", e)
            self.company_picker_loaded.emit(_err(f"Неверные поля: {e}"))
            return

        if not name:
            self.company_picker_loaded.emit(
                _err("Название обязательно.", vacancy_id=vacancy_id)
            )
            return

        async def run() -> str:
            try:
                async with self._session_factory() as session:
                    async with session.begin():
                        new_co = await companies_card.create_company(
                            session, **fields
                        )
                        created_id = new_co.id
                    rows = await companies_list.list_companies_with_counts(
                        session, search=search
                    )
                    v = await session.get(Vacancy, vacancy_id)
                    current_company_id = v.company_id if v is not None else None
                    payload = {
                        "vacancy_id": vacancy_id,
                        "current_company_id": current_company_id,
                        "search": search or "",
                        "companies": [_company_picker_row_to_dict(r) for r in rows],
                        "created_id": created_id,
                    }
            except IntegrityError:
                return _err(
                    f"Компания «{name}» уже существует.",
                    vacancy_id=vacancy_id,
                )
            except ValueError as e:
                return _err(str(e), vacancy_id=vacancy_id)
            return _ok(payload)

        self._dispatch(self.company_picker_loaded, run())

    # --- Contacts / HR (05) ---------------------------------------------

    @Slot(str)
    def request_contacts_hr_list(self, payload_json: str) -> None:
        """Push the HR-list payload for Contacts / HR (05).

        Same backing query as the picker (``list_hr_with_counts``) but with
        infinite-scroll: ``mode``/``offset``/``limit`` mirror the vacancies
        list. ``epoch`` is echoed back so the JS can drop stale responses
        when filters/search/sort change mid-flight.
        """
        try:
            payload = json.loads(payload_json) if payload_json else {}
            search = payload.get("search")
            if search is not None:
                search = str(search)

            def _int(key: str) -> int | None:
                raw = payload.get(key)
                if raw in (None, ""):
                    return None
                try:
                    return int(raw)
                except (TypeError, ValueError):
                    return None

            limit = _int("limit")
            # Sanity cap — JS uses 30 / 200, but a malformed payload could
            # request millions; the post-filter slice walks all rows in
            # Python, so we want a hard ceiling at the boundary.
            if limit is not None and limit > 200:
                limit = 200
            offset = _int("offset") or 0
            mode_raw = str(payload.get("mode") or "replace")
            mode = (
                mode_raw if mode_raw in {"replace", "append", "refresh"}
                else "replace"
            )
            epoch = _int("epoch")
        except (ValueError, TypeError) as e:
            _log_invalid_payload("request_contacts_hr_list", e)
            self.contacts_hr_list_loaded.emit(_err(f"Неверные поля: {e}"))
            return

        async def run() -> str:
            async with self._session_factory() as session:
                rows = await hr_list.list_hr_with_counts(
                    session,
                    search=search,
                    limit=limit,
                    offset=offset,
                    sort_by="last_activity",
                )
            has_more = (limit is not None) and (len(rows) == limit)
            return _ok({
                "search": search or "",
                "hrs": [_hr_picker_row_to_dict(r) for r in rows],
                "has_more": has_more,
                "mode": mode,
                "offset": offset,
                "epoch": epoch,
            })

        self._dispatch(self.contacts_hr_list_loaded, run())

    @Slot(str)
    def request_contacts_hr_vacancies(self, payload_json: str) -> None:
        """Push the vacancy mini-list for the HR detail pane.

        Payload: ``{hr_id, epoch}``. ``hr_id`` фильтрует ответ от другого
        выбранного HR, ``epoch`` — от race'а двух подряд request'ов на ОДНОГО
        и того же HR (например, рапид-флип статуса вакансии). Оба эхо'ятся
        обратно в ответе, JS дропает stale.
        """
        try:
            payload = json.loads(payload_json)
            hr_id = int(payload["hr_id"])
            epoch = payload.get("epoch")
        except (ValueError, TypeError, KeyError) as e:
            _log_invalid_payload("request_contacts_hr_vacancies", e)
            self.contacts_hr_vacancies_loaded.emit(_err(f"Неверные поля: {e}"))
            return

        async def run() -> str:
            async with self._session_factory() as session:
                rows = await vacancies_mini.list_vacancies_for_hr(session, hr_id)
            return _ok({
                "hr_id": hr_id,
                "epoch": epoch,
                "vacancies": [
                    {
                        "id": v.id,
                        "title": v.title or "",
                        "status": v.status.value if v.status else "New",
                        "score": v.score,
                        "created_at": _iso(v.created_at),
                    }
                    for v in rows
                ],
            })

        self._dispatch(self.contacts_hr_vacancies_loaded, run())

    @Slot(int)
    def request_contacts_hr_detail(self, hr_id: int) -> None:
        """Push the HR-detail payload for the Contacts / HR pane (05).

        Returns ``hr_id`` in the payload so JS can drop stale responses
        when the user clicks a different row mid-flight.
        """
        async def run() -> str:
            async with self._session_factory() as session:
                detail = await hr_card.get_hr_detail(session, hr_id)
            if detail is None:
                return _err("HR не найден.", hr_id=hr_id)
            return _ok({
                "hr_id": detail.hr.id,
                "name": detail.hr.name,
                "telegram_username": detail.hr.telegram_username,
                "telegram_user_id": detail.hr.telegram_user_id,
                "notes": detail.hr.notes,
                "vacancy_count": detail.vacancy_count,
                "last_company_id": detail.last_company_id,
                "last_company_name": detail.last_company_name,
                "unread_count": detail.unread_count,
                "blacklist_value": detail.blacklist_value,
                "avatar": _avatar_data_url(detail.hr.avatar),
            })

        self._dispatch(self.contacts_hr_detail_loaded, run())

    @Slot(int)
    def contacts_mark_hr_read(self, hr_id: int) -> None:
        """Mark all unread incoming messages for an HR as read (slice 5b).

        Routes through ``Bot.mark_hr_chat_read`` so the read receipt also
        propagates to Telegram via Pyrogram. Re-emits the list+detail so
        the unread bubble + chip drop immediately.
        """
        async def run() -> str:
            if self._bot is None:
                return _err("Бот ещё не запущен.", hr_id=hr_id)
            try:
                updated = await self._bot.mark_hr_chat_read(hr_id)
            except Exception as e:
                logger.exception("contacts_mark_hr_read failed")
                return _err(
                    f"{type(e).__name__}: {e}",
                    hr_id=hr_id,
                    action="mark_read",
                )
            if updated:
                self._kick_unread()
            return _ok({
                "action": "mark_read",
                "hr_id": hr_id,
                "updated": updated,
            })

        self._dispatch(self.contacts_hr_action_done, run())

    @Slot(str)
    def contacts_send_hr_message(self, payload_json: str) -> None:
        """Send a chat message to an HR (slice 5a).

        Routes through ``Bot.send_to_hr_chat`` so the same Pyrogram client
        that polls and ingests is the one that sends — no second auth, no
        second session. On success, replays the messages query so JS sees
        the new outgoing bubble immediately.
        """
        try:
            payload = json.loads(payload_json)
            hr_id = int(payload["hr_id"])
            text = str(payload.get("text") or "").strip()
        except (ValueError, TypeError, KeyError) as e:
            _log_invalid_payload("contacts_send_hr_message", e)
            self.contacts_hr_action_done.emit(_err(f"Неверные поля: {e}"))
            return

        if not text:
            self.contacts_hr_action_done.emit(
                _err("Пустое сообщение.", hr_id=hr_id)
            )
            return

        async def run() -> str:
            if self._bot is None:
                return _err("Бот ещё не запущен.", hr_id=hr_id)
            try:
                msg = await self._bot.send_to_hr_chat(hr_id, text)
            except RuntimeError as e:
                return _err(str(e), hr_id=hr_id, action="send_message")
            except Exception as e:
                logger.exception("contacts_send_hr_message failed")
                return _err(
                    f"{type(e).__name__}: {e}",
                    hr_id=hr_id,
                    action="send_message",
                )
            return _ok({
                "action": "send_message",
                "hr_id": hr_id,
                "message_id": msg.id,
            })

        self._dispatch(self.contacts_hr_action_done, run())

    @Slot(int)
    def contacts_pick_and_send_hr_media(self, hr_id: int) -> None:
        """Open native file picker, then ship the chosen file to the HR.

        Photo extensions go through ``send_photo``; everything else is sent
        as a document. Picker runs synchronously on the Qt thread; the
        actual upload is dispatched to the bot's async runner so the UI
        stays responsive during the Telegram round-trip.
        """
        path, _ = QFileDialog.getOpenFileName(
            self._parent_widget,
            "Прикрепить файл",
            "",
            "Все файлы (*);;Изображения (*.png *.jpg *.jpeg *.webp *.gif);;Документы (*.pdf *.doc *.docx *.txt *.zip *.rar *.7z)",
        )
        if not path:
            return

        async def run() -> str:
            if self._bot is None:
                return _err("Бот ещё не запущен.", hr_id=hr_id)
            try:
                msg = await self._bot.send_to_hr_media(hr_id, path)
            except RuntimeError as e:
                return _err(str(e), hr_id=hr_id, action="send_media")
            except Exception as e:
                logger.exception("contacts_pick_and_send_hr_media failed")
                return _err(
                    f"{type(e).__name__}: {e}",
                    hr_id=hr_id,
                    action="send_media",
                )
            return _ok({
                "action": "send_media",
                "hr_id": hr_id,
                "message_id": msg.id,
            })

        self._dispatch(self.contacts_hr_action_done, run())

    @Slot(str)
    def request_contacts_hr_merge_picker(self, payload_json: str) -> None:
        """List of HRs eligible to absorb the current HR. Same row shape as
        the vacancies HR-picker, minus the absorbed HR itself.
        """
        try:
            payload = json.loads(payload_json)
            absorbed_id = int(payload["absorbed_id"])
            search = payload.get("search")
            if search is not None:
                search = str(search)
        except (ValueError, TypeError, KeyError) as e:
            _log_invalid_payload("request_contacts_hr_merge_picker", e)
            self.contacts_hr_merge_picker_loaded.emit(_err(f"Неверные поля: {e}"))
            return

        async def run() -> str:
            async with self._session_factory() as session:
                rows = await hr_list.list_hr_with_counts(session, search=search)
            return _ok({
                "absorbed_id": absorbed_id,
                "search": search or "",
                "hrs": [
                    _hr_picker_row_to_dict(r) for r in rows
                    if r.hr.id != absorbed_id
                ],
            })

        self._dispatch(self.contacts_hr_merge_picker_loaded, run())

    @Slot(str)
    def contacts_merge_hr(self, payload_json: str) -> None:
        """Merge ``absorbed`` HR into ``survivor``: vacancies + messages get
        repointed, absorbed row is deleted. Backed by ``hr_card.merge_hr``.
        """
        try:
            payload = json.loads(payload_json)
            absorbed_id = int(payload["absorbed_id"])
            survivor_id = int(payload["survivor_id"])
        except (ValueError, TypeError, KeyError) as e:
            _log_invalid_payload("contacts_merge_hr", e)
            self.contacts_hr_action_done.emit(_err(f"Неверные поля: {e}"))
            return

        async def run() -> str:
            try:
                async with self._session_factory() as session:
                    async with session.begin():
                        await hr_card.merge_hr(
                            session,
                            absorbed_id=absorbed_id,
                            survivor_id=survivor_id,
                        )
            except ValueError as e:
                return _err(str(e), absorbed_id=absorbed_id, action="merge_hr")
            except Exception as e:
                logger.exception("contacts_merge_hr failed")
                return _err(
                    f"{type(e).__name__}: {e}",
                    absorbed_id=absorbed_id,
                    action="merge_hr",
                )
            self._kick_unread()
            return _ok({
                "action": "merge_hr",
                "absorbed_id": absorbed_id,
                "survivor_id": survivor_id,
            })

        self._dispatch(self.contacts_hr_action_done, run())

    @Slot(int)
    def contacts_delete_hr(self, hr_id: int) -> None:
        """Cascade-delete the HR row via ``hr_card.delete_hr``."""
        async def run() -> str:
            async with self._session_factory() as session:
                ok = await hr_card.delete_hr(session, hr_id)
                if not ok:
                    return _err("HR не найден.", hr_id=hr_id, action="delete_hr")
                await session.commit()
            self._kick_unread()
            return _ok({"action": "delete_hr", "hr_id": hr_id})

        self._dispatch(self.contacts_hr_action_done, run())

    @Slot(int)
    def contacts_remove_hr_from_blacklist(self, hr_id: int) -> None:
        """Deactivate any kind="hr" blacklist row matching this HR.

        Sets ``active=False`` rather than deleting — the blacklist screen
        keeps inactive rows visible with the toggle off, which is the
        expected UX for a «убрать из blacklist» from this screen.
        """
        async def run() -> str:
            async with self._session_factory() as session:
                hr = await session.get(HR, hr_id)
                if hr is None:
                    return _err("HR не найден.", hr_id=hr_id, action="unblacklist")
                candidates = hr_card.hr_blacklist_candidates(hr)
                if not candidates:
                    return _err(
                        "У HR нет ни @username, ни telegram_user_id.",
                        hr_id=hr_id, action="unblacklist",
                    )
                updated = await blacklist.deactivate_blacklist_values(
                    session, "hr", candidates,
                )
                await session.commit()
            self.contacts_lists_changed.emit()
            return _ok({
                "action": "unblacklist",
                "hr_id": hr_id,
                "updated": updated,
            })

        self._dispatch(self.contacts_hr_action_done, run())

    @Slot(int)
    def contacts_add_hr_to_blacklist(self, hr_id: int) -> None:
        """Insert a kind="hr" row into the blacklist for this HR.

        Value is ``@{username}`` if the HR has one, else ``user_id:{id}``.
        Idempotent: if a matching row already exists it is re-activated;
        if active already, no-op (returns ok with ``existed=True``).
        Reason left NULL — the blacklist screen lets the user fill it later.
        Does NOT delete the HR — that's a separate action.
        """
        async def run() -> str:
            async with self._session_factory() as session:
                hr = await session.get(HR, hr_id)
                if hr is None:
                    return _err("HR не найден.", hr_id=hr_id, action="blacklist")
                value = hr_card.hr_blacklist_preferred_value(hr)
                if value is None:
                    return _err(
                        "У HR нет ни @username, ни telegram_user_id.",
                        hr_id=hr_id, action="blacklist",
                    )
                _, outcome = await blacklist.create_blacklist(
                    session, kind="hr", value=value,
                )
                await session.commit()
            self.contacts_lists_changed.emit()
            return _ok({
                "action": "blacklist",
                "hr_id": hr_id,
                "value": value,
                "existed": outcome != "created",
                "was_inactive": outcome == "reactivated",
            })

        self._dispatch(self.contacts_hr_action_done, run())

    @Slot(str)
    def request_contacts_hr_messages(self, payload_json: str) -> None:
        """Push a page of chat messages for the HR detail pane.

        Payload: ``{"hr_id": int, "before_id"?: int, "mode"?: "tail"|"older"}``.
        Default mode is "tail" — newest 50 messages. ``mode="older"`` requires
        ``before_id`` (oldest currently-loaded message id) and returns the
        next 50 older messages so JS can prepend them.
        """
        try:
            payload = json.loads(payload_json) if payload_json else {}
            hr_id = int(payload["hr_id"])
            before_id = payload.get("before_id")
            before_sent_at_raw = payload.get("before_sent_at")
            mode = payload.get("mode") or "tail"
            epoch = payload.get("epoch")
            if before_id is not None:
                before_id = int(before_id)
            before_sent_at = None
            if before_sent_at_raw:
                text = str(before_sent_at_raw)
                if text.endswith("Z"):
                    text = text[:-1] + "+00:00"
                try:
                    before_sent_at = datetime.fromisoformat(text)
                except ValueError:
                    before_sent_at = None
        except (ValueError, TypeError, KeyError) as e:
            _log_invalid_payload("request_contacts_hr_messages", e)
            self.contacts_hr_messages_loaded.emit(_err(f"Неверные поля: {e}"))
            return

        async def run() -> str:
            async with self._session_factory() as session:
                msgs, has_more = await messages_repo.list_messages_for_hr(
                    session, hr_id, limit=50,
                    before_id=before_id,
                    before_sent_at=before_sent_at,
                )
            return _ok({
                "hr_id": hr_id,
                "mode": mode,
                "epoch": epoch,
                "before_id": before_id,
                "has_more": has_more,
                "messages": [
                    {
                        "id": m.id,
                        "tg_message_id": m.tg_message_id,
                        "is_incoming": m.is_incoming,
                        "text": m.text,
                        "sent_at": _iso(m.sent_at),
                        "read_at": _iso(m.read_at),
                        "vacancy_id": m.vacancy_id,
                        "is_edited": m.is_edited,
                        "is_deleted": m.is_deleted,
                        "media_kind": m.media_kind,
                        "media_path": _media_url(m.media_path),
                        "media_name": m.media_name,
                    }
                    for m in msgs
                ],
            })

        self._dispatch(self.contacts_hr_messages_loaded, run())

    @Slot(str)
    def contacts_update_hr(self, payload_json: str) -> None:
        """Patch one or more HR columns from inline form fields (slice 3+).

        Payload shape: ``{"hr_id": int, "name"?: str, "telegram_username"?:
        str, "notes"?: str}``. Missing keys mean «leave unchanged» (sentinel
        on the repo side). Empty strings collapse to NULL.

        Re-emits the contacts list so the row's name/username refresh, and
        the detail payload so the head + form pick up canonicalised values
        (e.g. stripped «@»).
        """
        try:
            payload = json.loads(payload_json)
            hr_id = int(payload["hr_id"])
        except (ValueError, TypeError, KeyError) as e:
            _log_invalid_payload("contacts_update_hr", e)
            self.contacts_hr_action_done.emit(_err(f"Неверные поля: {e}"))
            return

        # Только присланные поля: отсутствие ключа значит «не трогать».
        kwargs = {
            key: payload[key]
            for key in ("name", "telegram_username", "notes")
            if key in payload
        }
        if not kwargs:
            self.contacts_hr_action_done.emit(
                _err("Нечего обновлять.", hr_id=hr_id)
            )
            return

        async def run() -> str:
            try:
                async with self._session_factory() as session:
                    async with session.begin():
                        ok = await hr_card.update_hr_fields(session, hr_id, **kwargs)
            except ValueError as e:  # негодный ник — ответ формы, а не сбой
                return _err(f"Неверные поля: {e}", hr_id=hr_id, action="update_hr")
            if not ok:
                return _err("HR не найден.", hr_id=hr_id, action="update_hr")
            return _ok({
                "action": "update_hr",
                "hr_id": hr_id,
                "fields": list(kwargs.keys()),
            })

        self._dispatch(self.contacts_hr_action_done, run())

    @Slot(str)
    def contacts_create_hr(self, payload_json: str) -> None:
        """Insert a new HR from the «Добавить HR» modal in Contacts / HR.

        On success returns ``created_id`` so JS can pre-select the new row,
        and the caller is expected to re-issue ``request_contacts_hr_list``
        to refresh.
        """
        try:
            payload = json.loads(payload_json)
            fields = read_new_hr_fields(payload)
        except (ValueError, TypeError, KeyError) as e:
            _log_invalid_payload("contacts_create_hr", e)
            self.contacts_hr_action_done.emit(_err(f"Неверные поля: {e}"))
            return

        if not hr_is_identified(fields):
            self.contacts_hr_action_done.emit(
                _err("Укажите хотя бы имя или @username.")
            )
            return

        async def run() -> str:
            async with self._session_factory() as session:
                async with session.begin():
                    new_hr = await hr_identify.create_hr(session, **fields)
                    created_id = new_hr.id
            return _ok({"action": "create_hr", "created_id": created_id})

        self._dispatch(self.contacts_hr_action_done, run())

    def cleanup(self) -> None:
        """Stop timers + the background bot. Runner shutdown is owned by shell.

        Cancels any in-flight poll cycle BEFORE waiting on the bot task so
        shutdown is fast even mid-Full-cycle (otherwise Qt's main thread
        would freeze for the rest of the channel pull).
        """
        self._health_timer.stop()
        self._unread_timer.stop()
        if self._bot is not None and self._bot_task is not None:
            self._bot.cancel_current_poll()
            self._bot.request_stop()
            try:
                self._bot_task.result(timeout=5)
            except TimeoutError:
                logger.warning(
                    "MainApi cleanup: bot task did not stop within 5s"
                )
            except Exception:
                logger.exception("MainApi cleanup: bot task raised on shutdown")

    # --- Background tickers ----------------------------------------------

    def _kick_mode(self) -> None:
        async def run() -> str:
            mode = await self._rs.get_mode()
            return _ok({"mode": mode.value})

        self._dispatch(self.mode_changed, run())

    def _kick_unread(self) -> None:
        async def run() -> str:
            async with self._session_factory() as session:
                count = await messages_repo.count_unread_incoming(session)
            return _ok({"count": count})

        self._dispatch(self.unread_changed, run())

    @Slot()
    def request_unread_chats(self) -> None:
        """List of HRs with at least one unread incoming message — feeds the
        footer pop-up (TODO #4). Ordered by most recent unread first.
        """
        async def run() -> str:
            async with self._session_factory() as session:
                rows = await hr_list.list_hrs_with_unread(session)
            return _ok({"chats": rows})

        self._dispatch(self.unread_chats_loaded, run())

    # === Contacts / Companies (06) =====================================

    @Slot(str)
    def request_contacts_company_list(self, payload_json: str) -> None:
        """Page of Companies for the Contacts/Companies pane.

        Payload mirrors `request_contacts_hr_list` — search + epoch +
        offset/limit + replace/append/refresh mode. Backend echoes epoch
        so JS can drop stale responses when search/scroll race.
        """
        try:
            payload = json.loads(payload_json) if payload_json else {}
            search = payload.get("search")
            if search is not None:
                search = str(search)
            limit = payload.get("limit")
            limit = int(limit) if limit is not None else 50
            if limit > 200:
                limit = 200  # cap; mirrors the HR list slot
            offset = payload.get("offset")
            offset = int(offset) if offset is not None else 0
            mode = payload.get("mode") or "replace"
            if mode not in ("replace", "append", "refresh"):
                mode = "replace"
            epoch = payload.get("epoch")
        except (ValueError, TypeError) as e:
            _log_invalid_payload("request_contacts_company_list", e)
            self.contacts_company_list_loaded.emit(_err(f"Неверные поля: {e}"))
            return

        async def run() -> str:
            async with self._session_factory() as session:
                rows = await companies_list.list_companies_with_counts(
                    session, search=search, limit=limit, offset=offset,
                )
            has_more = (limit is not None) and (len(rows) == limit)
            return _ok({
                "search": search or "",
                "companies": [_company_picker_row_to_dict(r) for r in rows],
                "has_more": has_more,
                "mode": mode,
                "offset": offset,
                "epoch": epoch,
            })

        self._dispatch(self.contacts_company_list_loaded, run())

    @Slot(int)
    def request_contacts_company_detail(self, company_id: int) -> None:
        async def run() -> str:
            async with self._session_factory() as session:
                detail = await companies_card.get_company_detail(session, company_id)
            if detail is None:
                return _err("Компания не найдена.", company_id=company_id)
            return _ok({
                "company_id": detail.company.id,
                "name": detail.company.name,
                "website": detail.company.website,
                "aliases": list(detail.company.aliases or []),
                "notes": detail.company.notes,
                "vacancy_count": detail.vacancy_count,
                "hr_count": detail.hr_count,
                "blacklist_value": detail.blacklist_value,
            })

        self._dispatch(self.contacts_company_detail_loaded, run())

    @Slot(str)
    def request_contacts_company_vacancies(self, payload_json: str) -> None:
        """Push the vacancy mini-list for the Company detail pane.

        Payload: ``{company_id, epoch}``. ``company_id`` фильтрует ответ при
        переключении на другую компанию, ``epoch`` — race на одной и той же
        компании (рапид-флип статуса вакансии). Оба эхо'ятся обратно.
        """
        try:
            payload = json.loads(payload_json)
            company_id = int(payload["company_id"])
            epoch = payload.get("epoch")
        except (ValueError, TypeError, KeyError) as e:
            _log_invalid_payload("request_contacts_company_vacancies", e)
            self.contacts_company_vacancies_loaded.emit(_err(f"Неверные поля: {e}"))
            return

        async def run() -> str:
            async with self._session_factory() as session:
                rows = await vacancies_mini.list_vacancies_for_company(session, company_id)
            return _ok({
                "company_id": company_id,
                "epoch": epoch,
                "vacancies": [
                    {
                        "id": v.id,
                        "title": v.title or "",
                        "status": v.status.value if v.status else "New",
                        "score": v.score,
                        "created_at": _iso(v.created_at),
                    }
                    for v in rows
                ],
            })

        self._dispatch(self.contacts_company_vacancies_loaded, run())

    @Slot(int)
    def request_contacts_company_hrs(self, company_id: int) -> None:
        """HRs that have at least one vacancy at this company, with
        per-HR vacancy count restricted to that company.
        """
        async def run() -> str:
            async with self._session_factory() as session:
                rows = await hr_list.list_hrs_for_company(session, company_id)
            return _ok({
                "company_id": company_id,
                "hrs": [
                    {
                        "id": hr.id,
                        "name": hr.name,
                        "telegram_username": hr.telegram_username,
                        "vacancy_count": cnt,
                        "avatar": _avatar_data_url(hr.avatar),
                    }
                    for hr, cnt in rows
                ],
            })

        self._dispatch(self.contacts_company_hrs_loaded, run())

    @Slot(str)
    def update_blacklist(self, payload_json: str) -> None:
        """Partial update value/reason для одного blacklist-ряда.
        Payload: ``{id, value?, reason?}`` — присылаем только изменённое
        поле, бэкенд игнорит отсутствующие через sentinel.
        """
        blacklist_id = None
        try:
            payload = json.loads(payload_json)
            blacklist_id = int(payload["id"])
            kwargs: dict = {}
            if "value" in payload:
                kwargs["value"] = payload.get("value")
            if "reason" in payload:
                kwargs["reason"] = payload.get("reason")
            if not kwargs:
                raise KeyError("value / reason")
        except (ValueError, TypeError, KeyError) as e:
            _log_invalid_payload("update_blacklist", e)
            self.contacts_blacklist_action_done.emit(_err(
                f"Неверные поля: {e}", action="update", id=blacklist_id,
            ))
            return

        async def run() -> str:
            try:
                async with self._session_factory() as session:
                    async with session.begin():
                        ok = await blacklist.update_blacklist(
                            session, blacklist_id, **kwargs
                        )
            except blacklist.BlacklistUpdateError as e:
                return _err(str(e), id=blacklist_id, action="update")
            if not ok:
                return _err(
                    "Запись не найдена.",
                    id=blacklist_id, action="update",
                )
            # value мог поменяться → `is_blacklisted` в HR/Company может
            # перестать совпадать (или начать) → кросс-таб refresh.
            if "value" in kwargs:
                self.contacts_lists_changed.emit()
            return _ok({
                "id": blacklist_id,
                "fields": list(kwargs.keys()),
                "action": "update",
            })

        self._dispatch_action(
            self.contacts_blacklist_action_done, run(),
            action="update", id=blacklist_id,
        )

    @Slot(str)
    def request_create_blacklist(self, payload_json: str) -> None:
        """Add a new blacklist row from the UI «Добавить» modal.

        Payload: ``{kind, value, reason?}``. Бэк дедуплицирует по
        (kind, value): если ряд уже есть и неактивен — реактивирует, если
        активен — возвращает как есть. В обоих этих случаях ответ:
        ``{ok:true, id, created:false, action:"create"}``. На вставке
        нового — ``created:true``.
        """
        try:
            payload = json.loads(payload_json) if payload_json else {}
            kind = (payload.get("kind") or "").strip()
            value = (payload.get("value") or "").strip()
            reason = payload.get("reason")
        except (ValueError, TypeError) as e:
            _log_invalid_payload("request_create_blacklist", e)
            self.contacts_blacklist_action_done.emit(_err(
                f"Неверные поля: {e}", action="create",
            ))
            return

        if kind not in BLACKLIST_KINDS:
            self.contacts_blacklist_action_done.emit(_err(
                "Неверный тип записи.", action="create",
            ))
            return
        if not value:
            self.contacts_blacklist_action_done.emit(_err(
                "Значение не может быть пустым.", action="create",
            ))
            return

        async def run() -> str:
            try:
                async with self._session_factory() as session:
                    async with session.begin():
                        row, outcome = await blacklist.create_blacklist(
                            session, kind=kind, value=value, reason=reason,
                        )
                        new_id = row.id
                        # kind=channel → автоматически выключаем подходящие
                        # каналы. Без этого канал остался бы is_active=true
                        # после блокировки, и UI-toggle давал бы запутанную
                        # картину (загорелось — но bot всё равно скипает).
                        deactivated = 0
                        if kind == "channel":
                            deactivated = await channels_repo.deactivate_blacklisted_channels(session)
            except blacklist.BlacklistUpdateError as e:
                return _err(str(e), action="create")
            # Новая (или реактивированная) запись блеклиста влияет на
            # `is_blacklisted` HR/Company/Channel list rows — пушим refresh.
            self.contacts_lists_changed.emit()
            return _ok({
                "id": new_id,
                "created": outcome == "created",
                "deactivated_channels": deactivated,
                "action": "create",
            })

        self._dispatch_action(
            self.contacts_blacklist_action_done, run(), action="create",
        )

    @Slot(int)
    def delete_blacklist(self, blacklist_id: int) -> None:
        """Delete a blacklist row by id. UI всегда зовёт после confirm-
        модалки, повторное подтверждение не нужно.
        """
        async def run() -> str:
            async with self._session_factory() as session:
                async with session.begin():
                    ok = await blacklist.delete_blacklist(session, blacklist_id)
            if not ok:
                return _err(
                    "Запись не найдена.",
                    id=blacklist_id,
                    action="delete",
                )
            # `is_blacklisted` запечён в HR/Company list rows — сигналим
            # кросс-таб refresh, чтобы они не показывали удалённую
            # запись как блокирующую.
            self.contacts_lists_changed.emit()
            return _ok({"id": blacklist_id, "action": "delete"})

        self._dispatch_action(
            self.contacts_blacklist_action_done, run(),
            action="delete", id=blacklist_id,
        )

    @Slot(str)
    def set_blacklist_active(self, payload_json: str) -> None:
        """Toggle Blacklist.active для одного ряда. Echoes ``id`` и
        ``active`` чтобы UI откатил optimistic flip на ошибке.
        """
        blacklist_id = None
        active = None
        try:
            payload = json.loads(payload_json)
            raw_id = payload.get("id")
            if raw_id is not None:
                blacklist_id = int(raw_id)
            raw_active = payload.get("active")
            if raw_active is not None:
                active = bool(raw_active)
            if blacklist_id is None or active is None:
                raise KeyError("id / active")
        except (ValueError, TypeError, KeyError) as e:
            _log_invalid_payload("set_blacklist_active", e)
            self.contacts_blacklist_action_done.emit(_err(
                f"Неверные поля: {e}",
                action="set_active",
                id=blacklist_id,
                active=active,
            ))
            return

        async def run() -> str:
            async with self._session_factory() as session:
                async with session.begin():
                    ok = await blacklist.set_blacklist_active(
                        session, blacklist_id, active
                    )
            if not ok:
                return _err(
                    "Запись не найдена.",
                    id=blacklist_id,
                    active=active,
                    action="set_active",
                )
            # См. delete_blacklist — `is_blacklisted` в HR/Company должен
            # синхронизироваться по toggle тоже.
            self.contacts_lists_changed.emit()
            return _ok({
                "id": blacklist_id,
                "active": active,
                "action": "set_active",
            })

        self._dispatch_action(
            self.contacts_blacklist_action_done, run(),
            action="set_active",
            id=blacklist_id,
            active=active,
        )

    @Slot(str)
    def request_system_logs(self, payload_json: str) -> None:
        """Snapshot текущего log-buffer'а с фильтрами по level/source/search.

        Payload: ``{level?, source?, search?, limit?}``. level — точное
        совпадение на levelname, source — startswith (logger 'backend.flows'
        матчит фильтр 'backend'), search — substring case-insensitive по
        msg+details.

        Дешёвая 1-сек защита от auto-fire'а из JS (например, log-poll'а в
        пол-секунды): второй вызов в окне 1 секунды считается избыточным,
        UI всё равно перерендерится через подписку на push-сигнал.
        """
        import time as _time
        last_ts = getattr(self, "_logs_request_last_ts", 0.0)
        now = _time.time()
        if now - last_ts < 1.0:
            logger.debug("request_system_logs: debounced (interval %.2fs)", now - last_ts)
            return
        self._logs_request_last_ts = now
        from backend.log_buffer import get_handler
        try:
            payload = json.loads(payload_json) if payload_json else {}
            level = payload.get("level")
            source = payload.get("source")
            search = payload.get("search")
            limit = int(payload.get("limit") or 1000)
            if limit > 5000:
                limit = 5000
        except (ValueError, TypeError) as e:
            _log_invalid_payload("request_system_logs", e)
            self.system_logs_loaded.emit(_err(f"Неверные поля: {e}"))
            return

        async def run() -> str:
            # Один snapshot для всего: иначе race между среза'ми может
            # дать инконсистентные records vs counts.
            all_records = get_handler().snapshot()
            sources = sorted({r["source"] for r in all_records})
            level_counts: dict[str, int] = {}
            for r in all_records:
                lvl = r["level"]
                # CRITICAL рендерится как ERROR в UI — счётчик объединяем,
                # чтобы ERROR-pill не недоучитывал.
                if lvl == "CRITICAL":
                    lvl = "ERROR"
                level_counts[lvl] = level_counts.get(lvl, 0) + 1

            records = all_records
            if level:
                if level == "ERROR":
                    records = [r for r in records if r["level"] in ("ERROR", "CRITICAL")]
                else:
                    records = [r for r in records if r["level"] == level]
            if source:
                records = [r for r in records if r["source"].startswith(source)]
            if search:
                q = search.casefold()
                records = [
                    r for r in records
                    if q in r["msg"].casefold()
                    or (r.get("details") and q in r["details"].casefold())
                ]
            # Newest-first; UI рендерит сверху-вниз.
            records = list(reversed(records))[:limit]
            return _ok({
                "records": records,
                "sources": sources,
                "level_counts": level_counts,
                "total": len(all_records),
            })

        self._dispatch(self.system_logs_loaded, run())

    @Slot(bool)
    def set_logs_subscribed(self, subscribed: bool) -> None:
        """JS toggle'ит при заходе/уходе с logs-таба и при включении/
        выключении auto-refresh. Когда False, push-сигнал гасится в
        источнике (см. `_on_record` в __init__).
        """
        self._logs_subscribed = bool(subscribed)

    @Slot()
    def request_system_logs_clear(self) -> None:
        """Очищает in-memory ring-buffer. Не трогает файлы/stdout — это
        чисто UI-action для сброса видимого списка.
        """
        from backend.log_buffer import get_handler
        async def run() -> str:
            cleared = get_handler().clear()
            return _ok({"cleared": cleared})

        self._dispatch(self.system_logs_cleared, run())

    @Slot()
    def request_system_settings(self) -> None:
        """Snapshot of current runtime settings for the Settings screen.

        api_hash отправляем — eye-toggle в UI должен уметь показать значение.
        QWebChannel живёт только в локальном Qt-окне, не уезжает в сеть.
        """
        tg = self._rs.tg
        chat = self._rs.chat
        embed = self._rs.embed
        bot = self._bot

        async def run() -> str:
            client = getattr(bot, "_client", None) if bot is not None else None
            # На холодном старте Pyrogram session-load + connect занимает
            # пару секунд; UI запросит settings раньше. Ждём короткий
            # connect-window (до 3 сек).
            if client is not None and not getattr(client, "is_connected", False):
                for _ in range(15):
                    await asyncio.sleep(0.2)
                    if getattr(client, "is_connected", False):
                        break
            asked = None
            connected = client is not None and getattr(client, "is_connected", False)
            if connected:
                asked = await username_of(client)
                if asked is None:
                    logger.warning("get_me() failed for settings", exc_info=True)
            if asked is None:
                # Спросить не вышло или бот ещё не подключился — отдаём кэш.
                username = self._username_cache
            else:
                # Пустая строка — это ответ «ника нет», и он перебивает кэш:
                # снятый ник иначе остался бы на экране прежним.
                username = asked
                self._username_cache = asked
            return _ok({
                "tg": {
                    "api_id": str(tg.api_id) if tg else "",
                    "api_hash": tg.api_hash if tg else "",
                    "phone": tg.phone if tg else "",
                    "has_password": bool(tg and tg.password),
                    "has_session": bool(tg and tg.session_string),
                    "username": username,
                },
                "chat": {
                    "base_url": chat.base_url if chat else "",
                    "api_key": chat.api_key if chat else "",
                    "model": chat.model if chat else "",
                },
                "embed": {
                    "base_url": embed.base_url if embed else "",
                    "api_key": embed.api_key if embed else "",
                    "model": embed.model if embed else "",
                },
                "pipeline": {
                    "scoring_threshold": self._rs.scoring_threshold,
                    "poll_interval_sec": self._rs.poll_interval_sec,
                    "backfill_limit": self._rs.backfill_limit,
                    "dm_backfill_limit": self._rs.dm_backfill_limit,
                    "send_locked": self._rs.send_locked,
                },
            })

        self._dispatch(self.system_settings_loaded, run())

    @Slot(str)
    def request_llm_probe(self, payload_json: str) -> None:
        """Connectivity check for an LLM provider (chat / embed).

        Payload: ``{kind: 'chat'|'embed', base_url, api_key, model}``.
        Использует draft-значения из UI, не текущий rs — чтобы юзер мог
        проверить новые настройки до сохранения. Замеряем latency полного
        check'а (list_models + 1-token ping).
        """
        # Init defaults ДО try, чтобы все error-ветки могли echo'нуть kind
        # обратно — JS использует его для роутинга в нужный *Probe-state.
        kind = ""
        try:
            payload = json.loads(payload_json) if payload_json else {}
            kind = str(payload.get("kind", "")).strip()
            base_url = str(payload.get("base_url", "")).strip().rstrip("/")
            api_key = str(payload.get("api_key", ""))
            model = str(payload.get("model", "")).strip()
            if kind not in ("chat", "embed"):
                raise ValueError(f"bad kind: {kind!r}")
            if not base_url or not model:
                raise ValueError("base_url и model обязательны")
        except (ValueError, TypeError) as e:
            _log_invalid_payload("request_llm_probe", e)
            self.llm_probe_done.emit(_err(f"Неверные поля: {e}", kind=kind))
            return

        cfg = LlmProviderConfig(base_url=base_url, api_key=api_key, model=model)
        check_fn = lm_studio.check_chat if kind == "chat" else lm_studio.check_embed

        async def run() -> str:
            try:
                ok, detail, _models, latency_ms = await _do_llm_probe(cfg, check_fn)
            except Exception as e:
                logger.exception("llm probe failed")
                return _err(f"{type(e).__name__}: {e}", kind=kind)
            if not ok:
                return _err(detail, kind=kind)
            return _ok({"kind": kind, "model": cfg.model, "latency_ms": latency_ms})

        self._dispatch(self.llm_probe_done, run())

    @Slot(str)
    def save_settings(self, payload_json: str) -> None:
        """Apply a partial settings patch — autosave из UI на blur/change.

        Payload — словарь с любыми из ключей:
        - chat: {base_url, api_key, model}
        - embed: {base_url, api_key, model}
        - app: {scoring_threshold, poll_interval_sec, backfill_limit,
          dm_backfill_limit, ...}
        Применяем через rs.set_chat / rs.set_embed / rs.set_app. Ошибки
        возвращаем в payload, UI показывает toast.
        """
        try:
            payload = json.loads(payload_json) if payload_json else {}
        except (ValueError, TypeError) as e:
            _log_invalid_payload("save_settings", e)
            self.settings_save_done.emit(_err(f"Неверные поля: {e}"))
            return

        chat = payload.get("chat") if isinstance(payload.get("chat"), dict) else None
        embed = payload.get("embed") if isinstance(payload.get("embed"), dict) else None
        app = payload.get("app") if isinstance(payload.get("app"), dict) else None

        # Pre-validate: пустой model — почти всегда last-blur'на стерлась
        # в tab-switch'е (см. main.html guards). Раньше уходило в
        # _set_llm как пустая строка, _from_llm_row возвращал None и
        # config «исчезал» — юзер думал «починилось», а LLM-вызовы
        # начинали валиться. Лучше отбить рано с понятной ошибкой.
        for kind_name, payload in (("chat", chat), ("embed", embed)):
            if payload is None:
                continue
            model_val = str(payload.get("model") or "").strip()
            if not model_val:
                logger.warning(
                    "save_settings: empty model for %s — refusing to save",
                    kind_name,
                )
                self.settings_save_done.emit(
                    _err(f"{kind_name}: пустое имя модели — сохранение отклонено")
                )
                return

        async def run() -> str:
            applied: list[str] = []
            try:
                if chat is not None:
                    await self._rs.set_chat(
                        base_url=str(chat.get("base_url") or "").strip().rstrip("/"),
                        api_key=str(chat.get("api_key") or ""),
                        model=str(chat.get("model") or "").strip(),
                    )
                    applied.append("chat")
                if embed is not None:
                    await self._rs.set_embed(
                        base_url=str(embed.get("base_url") or "").strip().rstrip("/"),
                        api_key=str(embed.get("api_key") or ""),
                        model=str(embed.get("model") or "").strip(),
                    )
                    applied.append("embed")
                if app is not None:
                    # Whitelist: чтобы UI не мог по ошибке/опечатке писать
                    # произвольные ключи в app_settings.
                    allowed = {
                        "scoring_threshold", "poll_interval_sec",
                        "backfill_limit", "dm_backfill_limit",
                        "send_locked",
                    }
                    for key, value in app.items():
                        if key not in allowed:
                            logger.warning("save_settings: unknown app key %r ignored", key)
                            continue
                        # Bool → "true"/"false": app_settings хранит строки,
                        # rs.send_locked парсит обратно в lower-case bool
                        # (см. RuntimeSettings.send_locked). True/False через
                        # str() дали бы "True"/"False" — не пройдут .lower()
                        # сравнение с "true".
                        if isinstance(value, bool):
                            value = "true" if value else "false"
                        await self._rs.set_app(str(key), str(value))
                        applied.append(f"app.{key}")
                    # Sync send_locked в adapters.telegram чтобы новое значение
                    # начало действовать без рестарта бота. Авторитет —
                    # rs.send_locked; константа — кеш для горячего пути отправки.
                    if "send_locked" in app:
                        from adapters import telegram as _tg
                        _tg.SEND_LOCKED = self._rs.send_locked
            except Exception as e:
                logger.exception("save_settings failed")
                return _err(f"{type(e).__name__}: {e}", applied=applied)
            return _ok({"applied": applied})

        self._dispatch(self.settings_save_done, run())

    @Slot()
    def request_delete_all_data(self) -> None:
        """Опасная зона → «Удалить всё». Останавливает бота, закрывает
        DB-engine, удаляет файлы (jobbot.db + sidecars, sessions/, media/),
        и завершает приложение через QApplication.quit() (юзер сам
        перезапустит — следующий старт уйдёт в визард, т.к. все настройки
        стерты вместе с БД).
        """
        bot = self._bot
        bot_task = self._bot_task
        # Захватываем сразу, потом null'им — чтобы health-timer не дёрнулся
        # на полу-удалённой БД. И, главное, тут же тушим сами таймеры
        # (health/unread) — иначе после engine.dispose() их следующий тик
        # откроет fresh connection из пула и Windows откажется удалять
        # jobbot.db с открытым handle'ом.
        self._bot = None
        self._bot_task = None
        self._health_timer.stop()
        self._unread_timer.stop()

        async def run() -> str:
            import shutil
            from config import get_data_dir
            errors: list[str] = []

            # 1) Стопаем бота — Pyrogram-сессия закроется, файлы освободятся.
            if bot is not None:
                try:
                    bot.cancel_current_poll()
                except Exception:
                    logger.debug("delete_all: cancel_current_poll failed", exc_info=True)
                try:
                    bot.request_stop()
                except Exception:
                    logger.debug("delete_all: request_stop failed", exc_info=True)
            if bot_task is not None:
                try:
                    await asyncio.wait_for(asyncio.wrap_future(bot_task), timeout=10)
                except asyncio.TimeoutError:
                    logger.warning("delete_all: bot did not stop within 10s")
                except Exception:
                    logger.exception("delete_all: bot task raised")

            # 2) Закрываем engine — иначе Windows не даст удалить jobbot.db.
            if self._engine is not None:
                try:
                    await self._engine.dispose()
                except Exception as e:
                    errors.append(f"engine.dispose: {e}")
                    logger.exception("delete_all: engine.dispose failed")

            # 3) Удаляем файлы.
            data_dir = get_data_dir()
            for name in ("jobbot.db", "jobbot.db-shm", "jobbot.db-wal"):
                p = data_dir / name
                if p.exists():
                    try:
                        p.unlink()
                    except Exception as e:
                        errors.append(f"{name}: {e}")
                        logger.exception("delete_all: failed to remove %s", p)
            for sub in ("sessions", "media"):
                d = data_dir / sub
                if d.exists():
                    try:
                        shutil.rmtree(d)
                    except Exception as e:
                        errors.append(f"{sub}/: {e}")
                        logger.exception("delete_all: failed to remove %s", d)

            # 4) Удаляем Fernet master key из OS-keychain'а. Без этого
            # после reinstall'а у юзера висит мёртвая запись в Windows
            # Credential Manager / macOS Keychain — некритично (новый
            # ключ перегенерится), но «delete all» должно быть «delete
            # all», а не «delete most».
            try:
                import keyring as _keyring
                from backend.crypto import (
                    _KEYRING_SERVICE,
                    _KEYRING_KEY,
                )
                _keyring.delete_password(_KEYRING_SERVICE, _KEYRING_KEY)
            except Exception as e:
                # delete_password может бросить если записи нет — это OK.
                logger.debug("delete_all: keyring entry already absent (%s)", e)

            if errors:
                return _err("Не все файлы удалось удалить: " + "; ".join(errors))
            return _ok({})

        # После завершения корутины (успех/ошибка) — эмитим результат и
        # сразу убиваем процесс через os._exit(0). Штатный QApplication.quit()
        # здесь приводит к зависанию: aboutToQuit → api.cleanup() →
        # runner.stop() → gather отменяемых тасков, и какой-то из них
        # натыкается на удалённую sessions/jobbot.db и блокирует unwind.
        # Для «wipe everything» все нужные действия (бот остановлен,
        # engine disposed, файлы удалены) уже сделаны выше — штатный
        # cleanup нам не нужен.
        future = self._runner.submit(run())

        def _on_done(f: Future) -> None:
            try:
                payload = f.result()
            except Exception as e:
                payload = _err(f"{type(e).__name__}: {e}")
            self.delete_all_data_done.emit(payload)
            import os
            os._exit(0)

        future.add_done_callback(_on_done)

    @Slot(str)
    def request_llm_models(self, payload_json: str) -> None:
        """Background-fetch списка моделей — UI наполняет datalist для
        автокомплита поля «Модель». Под LM Studio предпочтительно
        ``/api/v0/models`` с фильтром по type/state (см. lm_studio.list_models),
        фолбэк на OpenAI-совместимый ``/v1/models``. Best-effort, ошибки в
        payload."""
        try:
            payload = json.loads(payload_json) if payload_json else {}
            kind = str(payload.get("kind") or "")
            base_url = str(payload.get("base_url") or "").strip().rstrip("/")
            api_key = str(payload.get("api_key") or "")
        except (ValueError, TypeError):
            return
        if not base_url or kind not in ("chat", "embed"):
            return

        async def run() -> str:
            result = await _do_list_models_for_creds(base_url, api_key, kind=kind)
            return json.dumps({"kind": kind, **result})

        self._dispatch(self.llm_models_listed, run())

    @Slot()
    def request_telegram_logout(self) -> None:
        """Stop the bot, revoke server-side TG session, clear creds in DB.

        Sequence:
          1. cancel current poll + ask bot to stop (via log_out_session, which
             sends DROP_AUTH then sets stop_event)
          2. wait for the bot run-task to finish (its finally calls
             client.stop() — already disconnected after log_out, no-op)
          3. clear session_string + password in DB so health/UI flip to
             "Нет сессии"
          4. null out _bot/_bot_task — re-login starts a fresh bot
        """
        bot = self._bot
        bot_task = self._bot_task

        async def run() -> str:
            # Если в момент logout открыта модалка re-auth, закрываем её
            # бэкенд-state тоже — иначе при следующем «Войти» налетим на
            # «уже отправили код».
            await self._login.forget()
            if bot is not None:
                bot.cancel_current_poll()
                await bot.log_out_session()
            if bot_task is not None:
                try:
                    await asyncio.wait_for(
                        asyncio.wrap_future(bot_task), timeout=10
                    )
                except asyncio.TimeoutError:
                    logger.warning("logout: bot did not stop within 10s")
                except Exception:
                    logger.exception("logout: bot task raised")
            await self._rs.clear_tg()
            self._username_cache = ""
            return _ok({})

        # Null out before dispatch so concurrent slots don't try to use a
        # half-stopped bot.
        self._bot = None
        self._bot_task = None
        self._dispatch(self.system_telegram_logout_done, run())

    @Slot()
    def cancel_telegram_login(self) -> None:
        """Юзер закрыл модалку re-auth до завершения. Чистим временный
        Pyrogram-клиент и обнуляем OTP-state, чтобы не оставлять открытый
        сокет и не уйти в «уже отправили код» при следующей попытке.
        """
        self._dispatch_noop(self._login.forget())

    def _dispatch_noop(self, coro: Coroutine[Any, Any, Any]) -> None:
        """Fire-and-forget: запускаем корутину на runner'е, ошибки в лог.
        Сигнал обратно не нужен — UI закрывает модалку оптимистично.
        """
        future = self._runner.submit(coro)

        def _on_done(f: Future) -> None:
            try:
                f.result()
            except (CancelledError, asyncio.CancelledError):
                pass
            except Exception:
                logger.warning("noop dispatch failed", exc_info=True)

        future.add_done_callback(_on_done)

    # --- Telegram OTP flow (re-login через Настройки) ---------------------
    # Отдельные slots нужны потому что QWebChannel регистрирует один объект
    # "api" — после онбординга на канале сидит MainApi, и WizardApi'шные
    # методы недоступны. Сам вход у обоих один и тот же.

    @Slot(str)
    def telegram_send_code(self, payload_json: str) -> None:
        _login_send_code(self, payload_json)

    @Slot(str)
    def telegram_confirm_code(self, payload_json: str) -> None:
        _login_confirm_code(self, payload_json)

    @Slot(str)
    def telegram_confirm_password(self, payload_json: str) -> None:
        _login_confirm_password(self, payload_json)

    def _after_login_saved(self, username: str | None) -> None:
        """Новая сессия сохранена: запомнить ник и поднять бота, если он лежит.

        Не спросившийся ник (`None`) прежний в кэше не трогает: показать
        старый вернее, чем стереть его до первого удачного `get_me` у бота.
        """
        if username is not None:
            self._username_cache = username
        if self._bot is None:
            self._start_bot()

    @Slot(str)
    def request_stats_status_breakdown(self, period: str) -> None:
        """Counts по 11 статусам за period — для funnel и all-status
        счётчиков. Echoes period для drop'а stale-ответов.
        """
        async def run() -> str:
            async with self._session_factory() as session:
                data = await stats_summary.get_stats_status_breakdown(
                    session, period=period,
                )
            return _ok(data)

        self._dispatch(self.stats_status_breakdown_loaded, run())

    @Slot(str)
    def request_stats_kpi(self, period: str) -> None:
        """Top-row KPIs для экрана Statistics. period ∈
        {today, week, month, quarter, all}.
        """
        async def run() -> str:
            async with self._session_factory() as session:
                data = await stats_summary.get_stats_kpi(session, period=period)
            return _ok(data)

        self._dispatch(self.stats_kpi_loaded, run())

    @Slot(str)
    def request_stats_hr_responses(self, period: str) -> None:
        """HR-response-time + weekday-распределение. Source:
        VacancyStatusHistory (Applied) + Message (incoming) — см.
        get_stats_hr_responses в repository."""
        async def run() -> str:
            async with self._session_factory() as session:
                data = await stats_summary.get_stats_hr_responses(
                    session, period=period,
                )
            return _ok(data)

        self._dispatch(self.stats_hr_responses_loaded, run())

    @Slot(str)
    def request_stats_skills(self, period: str) -> None:
        """Top-N skills (vacancy.stack tags за period) + флаг mine."""
        async def run() -> str:
            async with self._session_factory() as session:
                data = await stats_summary.get_stats_skills(
                    session, period=period,
                )
            return _ok(data)

        self._dispatch(self.stats_skills_loaded, run())

    @Slot(str)
    def request_stats_channels_pipeline(self, period: str) -> None:
        """Per-channel pipeline (Ингест / Воронка отклика / Конверсия)."""
        async def run() -> str:
            async with self._session_factory() as session:
                data = await stats_pipeline.get_stats_channels_pipeline(
                    session, period=period,
                )
            return _ok(data)

        self._dispatch(self.stats_channels_pipeline_loaded, run())

    @Slot(str)
    def request_blacklist_candidates(self, kind: str) -> None:
        """Список options для combobox'а add-modal'а blacklist'а.
        Echoes ``kind`` чтобы JS дропнул stale-ответ если юзер успел
        сменить тип до прихода данных.
        """
        async def run() -> str:
            async with self._session_factory() as session:
                items = await blacklist_candidates.list_blacklist_candidates(
                    session, kind
                )
            return _ok({"kind": kind, "items": items})

        self._dispatch(self.contacts_blacklist_candidates_loaded, run())

    @Slot()
    def request_contacts_blacklist_list(self) -> None:
        """Пуш всех строк blacklist'а — без пагинации/SQL-фильтров,
        размер мал. UI фильтрует локально (kind / search).
        """
        async def run() -> str:
            async with self._session_factory() as session:
                rows = await blacklist.list_blacklist(session)
            return _ok({
                "items": [_blacklist_row_to_dict(r) for r in rows],
            })

        self._dispatch(self.contacts_blacklist_list_loaded, run())

    @Slot(str)
    def request_contacts_channel_list(self, payload_json: str) -> None:
        """Full list of Telegram channels for the Contacts/Channels pane.

        No pagination — channel sets are tiny. Echoes the request epoch so
        the UI can drop stale responses when search races.
        """
        try:
            payload = json.loads(payload_json) if payload_json else {}
            search = payload.get("search")
            if search is not None:
                search = str(search)
            epoch = payload.get("epoch")
        except (ValueError, TypeError) as e:
            _log_invalid_payload("request_contacts_channel_list", e)
            self.contacts_channel_list_loaded.emit(_err(f"Неверные поля: {e}"))
            return

        async def run() -> str:
            async with self._session_factory() as session:
                # Self-heal: тушим каналы, попавшие в blacklist, но всё ещё
                # помеченные is_active=true (исторический дрейф / правки БД
                # мимо UI). Идемпотентно, и держит инвариант «blacklisted
                # ⇒ is_active=false» — иначе bot polling всё ещё трогал бы
                # запрещённые каналы.
                async with session.begin():
                    await channels_repo.deactivate_blacklisted_channels(session)
                rows = await channels_repo.list_telegram_channels(session, search=search)
            return _ok({
                "search": search or "",
                "channels": [_channel_row_to_dict(r) for r in rows],
                "epoch": epoch,
            })

        self._dispatch(self.contacts_channel_list_loaded, run())

    @Slot(int)
    def request_contacts_channel_detail(self, channel_id: int) -> None:
        """Detail-pane payload for one Telegram channel.

        Echoes ``channel_id`` so the UI drops stale responses when the user
        clicks another row mid-flight (mirrors HR/Company detail pattern).
        Includes computed stats (status breakdown + KPI ratios + recent
        ingestion rate) — see ``ChannelStats`` for shape.
        """
        async def run() -> str:
            async with self._session_factory() as session:
                detail = await channels_repo.get_channel_detail(session, channel_id)
            if detail is None:
                return _err("Канал не найден.", channel_id=channel_id)
            ch = detail.channel
            stats = detail.stats
            return _ok({
                "channel_id": ch.id,
                "username": ch.username,
                "title": ch.title,
                "is_active": bool(ch.is_active),
                "avatar": _avatar_data_url(ch.avatar),
                "stats": {
                    "status_counts": stats.status_counts,
                    "total": stats.total,
                    "vacancies_per_day": stats.vacancies_per_day,
                    "fit_percent": stats.fit_percent,
                    "apply_percent": stats.apply_percent,
                    "response_percent": stats.response_percent,
                },
                "blacklist_value": detail.blacklist_value,
            })

        self._dispatch(self.contacts_channel_detail_loaded, run())

    @Slot(str)
    def request_contacts_channel_vacancies(self, payload_json: str) -> None:
        """Pagination-aware vacancies fetch for the channels detail pane.

        Payload: ``{channel_id, limit, offset, mode}``. ``mode`` ∈
        {"replace", "append"} — replace wipes JS-side list, append concat'ит
        к существующему. Backend echoes channel_id + offset + has_more
        чтобы фронт мог дропать stale-ответы при гонке скролла/выбора.
        """
        try:
            payload = json.loads(payload_json) if payload_json else {}
            channel_id = int(payload["channel_id"])
            limit = int(payload.get("limit") or 50)
            if limit > 200:
                limit = 200
            offset = int(payload.get("offset") or 0)
            mode = payload.get("mode") or "replace"
            if mode not in ("replace", "append"):
                mode = "replace"
        except (ValueError, TypeError, KeyError) as e:
            _log_invalid_payload("request_contacts_channel_vacancies", e)
            self.contacts_channel_vacancies_loaded.emit(_err(f"Неверные поля: {e}"))
            return

        async def run() -> str:
            async with self._session_factory() as session:
                rows = await vacancies_mini.list_vacancies_for_channel(
                    session, channel_id, limit=limit, offset=offset,
                )
                # Diagnostic — раз баг проявляется: 0 здесь vs N в stats
                # помогает понять, в репо ли проблема или в bridge-эхо.
                if not rows:
                    total_for_channel = int(
                        (
                            await session.execute(
                                select(func.count(Vacancy.id))
                                .where(Vacancy.source_channel_id == channel_id)
                            )
                        ).scalar_one()
                    )
                    if total_for_channel > 0:
                        logger.warning(
                            "channel %d: list_vacancies_for_channel returned 0 "
                            "but %d rows match source_channel_id (limit=%d offset=%d) "
                            "— investigate query mismatch with stats",
                            channel_id,
                            total_for_channel,
                            limit,
                            offset,
                        )
            return _ok({
                "channel_id": channel_id,
                "offset": offset,
                "mode": mode,
                "has_more": len(rows) == limit,
                "vacancies": [
                    {
                        "id": v.id,
                        "title": v.title or "",
                        "status": v.status.value if v.status else "New",
                        "score": v.score,
                        "created_at": _iso(v.created_at),
                        "posted_at": _iso(v.posted_at),
                    }
                    for v in rows
                ],
            })

        self._dispatch(self.contacts_channel_vacancies_loaded, run())

    @Slot(int)
    def contacts_add_channel_to_blacklist(self, channel_id: int) -> None:
        """Insert kind="channel" blacklist row for this channel.
        Value = `@{username}`. Idempotent (re-activates inactive row).
        Mirrors HR/Company patterns. Pushes contacts_lists_changed so
        cross-tab `is_blacklisted` flags refresh.
        """
        async def run() -> str:
            async with self._session_factory() as session:
                ch = await session.get(TelegramChannel, channel_id)
                if ch is None:
                    return _err("Канал не найден.", channel_id=channel_id, action="blacklist")
                value = channels_repo.channel_blacklist_preferred_value(ch)
                if value is None:
                    return _err(
                        "У канала нет @username.",
                        channel_id=channel_id, action="blacklist",
                    )
                _, outcome = await blacklist.create_blacklist(
                    session, kind="channel", value=value,
                )
                # Канал в blacklist → автоматически выключаем сам канал,
                # чтобы UI-toggle отражал реальное «канал не работает».
                if ch.is_active:
                    ch.is_active = False
                await session.commit()
            self.contacts_lists_changed.emit()
            return _ok({
                "action": "blacklist",
                "channel_id": channel_id,
                "value": value,
                "existed": outcome != "created",
                "was_inactive": outcome == "reactivated",
            })

        self._dispatch(self.contacts_channel_action_done, run())

    @Slot(int)
    def contacts_remove_channel_from_blacklist(self, channel_id: int) -> None:
        """Deactivate any kind="channel" blacklist row for this channel."""
        async def run() -> str:
            async with self._session_factory() as session:
                ch = await session.get(TelegramChannel, channel_id)
                if ch is None:
                    return _err("Канал не найден.", channel_id=channel_id, action="unblacklist")
                candidates = channels_repo.channel_blacklist_candidates(ch)
                if not candidates:
                    return _err(
                        "У канала нет @username.",
                        channel_id=channel_id, action="unblacklist",
                    )
                updated = await blacklist.deactivate_blacklist_values(
                    session, "channel", candidates,
                )
                await session.commit()
            self.contacts_lists_changed.emit()
            return _ok({
                "action": "unblacklist",
                "channel_id": channel_id,
                "updated": updated,
            })

        self._dispatch(self.contacts_channel_action_done, run())

    @Slot(int)
    def request_channel_poll_now(self, channel_id: int) -> None:
        """UI «Прогнать сейчас» — single-channel poll."""
        async def run() -> str:
            if self._bot is None:
                return _err("Бот ещё не готов.", channel_id=channel_id, action="poll_now")
            status = await self._bot.poll_channel_now(channel_id)
            if status == "ok":
                return _ok({
                    "channel_id": channel_id,
                    "action": "poll_now",
                    "status": status,
                })
            messages = {
                "busy": "Уже идёт другой цикл, попробуйте позже.",
                "missing": "Канал не найден или без @username.",
                "cancelled": "Поллинг канала отменён.",
                "error": "Не удалось прогнать канал — см. логи.",
            }
            return _err(
                messages.get(status, "Не удалось прогнать канал."),
                channel_id=channel_id,
                action="poll_now",
                status=status,
            )

        self._dispatch_action(
            self.contacts_channel_action_done, run(),
            action="poll_now", channel_id=channel_id,
        )

    @Slot(int)
    def request_channel_reset_cursor(self, channel_id: int) -> None:
        """UI «Сбросить курсор» — clears last_processed_msg_id."""
        async def run() -> str:
            if self._bot is None:
                return _err("Бот ещё не готов.", channel_id=channel_id, action="reset_cursor")
            ok = await self._bot.reset_channel_cursor(channel_id)
            if not ok:
                return _err(
                    "Канал не найден.",
                    channel_id=channel_id,
                    action="reset_cursor",
                )
            return _ok({"channel_id": channel_id, "action": "reset_cursor"})

        self._dispatch_action(
            self.contacts_channel_action_done, run(),
            action="reset_cursor", channel_id=channel_id,
        )

    @Slot(int)
    def request_channel_delete(self, channel_id: int) -> None:
        """UI «Удалить канал» — nulls vacancy FKs, deletes row."""
        async def run() -> str:
            if self._bot is None:
                return _err("Бот ещё не готов.", channel_id=channel_id, action="delete")
            detached = await self._bot.delete_channel(channel_id)
            if detached is None:
                return _err(
                    "Канал не найден.",
                    channel_id=channel_id,
                    action="delete",
                )
            return _ok({
                "channel_id": channel_id,
                "detached_vacancies": detached,
                "action": "delete",
            })

        self._dispatch_action(
            self.contacts_channel_action_done, run(),
            action="delete", channel_id=channel_id,
        )

    @Slot(str)
    def request_create_channel(self, payload_json: str) -> None:
        """Add a new TelegramChannel from the UI «Добавить канал» modal.

        Accepts raw input — `@username`, plain `username`, or any t.me URL
        — and normalizes via the same parser used for HR contacts. On
        duplicate (channel already exists), returns ``ok=true`` with
        ``created=false`` so the UI selects the existing row instead of
        showing an error. Metadata fetch is opportunistic on the backend.
        """
        try:
            payload = json.loads(payload_json) if payload_json else {}
            raw = (payload.get("input") or "").strip()
        except (ValueError, TypeError) as e:
            _log_invalid_payload("request_create_channel", e)
            self.contacts_channel_action_done.emit(
                _err(f"Неверные поля: {e}", action="create")
            )
            return

        if not raw:
            self.contacts_channel_action_done.emit(
                _err("Укажите @username или ссылку на канал.", action="create")
            )
            return

        username = normalize_username(raw)
        if not username:
            self.contacts_channel_action_done.emit(
                _err(
                    "Не удалось распознать @username канала. "
                    "Поддерживаются форматы: @name, name, t.me/name.",
                    action="create",
                )
            )
            return

        async def run() -> str:
            if self._bot is None:
                return _err("Бот ещё не готов.", action="create")
            channel_id, status = await self._bot.add_channel(username)
            if status == "invalid":
                return _err(
                    f"Telegram не нашёл канал @{username}. Проверьте имя.",
                    action="create",
                    status=status,
                )
            return _ok({
                "channel_id": channel_id,
                "username": username,
                "created": status == "created",
                "action": "create",
                "status": status,
            })

        self._dispatch_action(
            self.contacts_channel_action_done, run(), action="create",
        )

    @Slot(str)
    def set_all_channels_active(self, payload_json: str) -> None:
        """Bulk-flip is_active на всех каналах. Echoes ``is_active`` чтобы
        фронт мог откатить optimistic-update на ошибке.
        """
        try:
            payload = json.loads(payload_json)
            is_active = bool(payload["is_active"])
        except (ValueError, TypeError, KeyError) as e:
            _log_invalid_payload("set_all_channels_active", e)
            self.contacts_channel_action_done.emit(_err(
                f"Неверные поля: {e}", action="set_all_active",
            ))
            return

        async def run() -> str:
            async with self._session_factory() as session:
                async with session.begin():
                    affected = await channels_repo.set_all_channels_active(
                        session, is_active
                    )
            return _ok({
                "is_active": is_active,
                "affected": affected,
                "action": "set_all_active",
            })

        self._dispatch_action(
            self.contacts_channel_action_done, run(),
            action="set_all_active", is_active=is_active,
        )

    @Slot(str)
    def set_channel_active(self, payload_json: str) -> None:
        """Toggle TelegramChannel.is_active for one row.

        Echoes ``channel_id`` and the requested ``is_active`` so the UI can
        rollback its optimistic flip on error without re-querying the list.
        """
        # Парсим осторожно: если payload неполный, тянем сколько смогли,
        # чтобы action+channel_id всё же попали в _err — иначе фронт не
        # знает, какой именно ряд откатывать.
        channel_id = None
        is_active = None
        try:
            payload = json.loads(payload_json)
            raw_id = payload.get("channel_id")
            if raw_id is not None:
                channel_id = int(raw_id)
            raw_active = payload.get("is_active")
            if raw_active is not None:
                is_active = bool(raw_active)
            if channel_id is None or is_active is None:
                raise KeyError("channel_id / is_active")
        except (ValueError, TypeError, KeyError) as e:
            _log_invalid_payload("set_channel_active", e)
            self.contacts_channel_action_done.emit(_err(
                f"Неверные поля: {e}",
                action="set_active",
                channel_id=channel_id,
                is_active=is_active,
            ))
            return

        async def run() -> str:
            async with self._session_factory() as session:
                async with session.begin():
                    # Включить канал, который сейчас в blacklist'е, нельзя —
                    # блокируем на уровне бэка, чтобы любой канал-toggle (в
                    # т.ч. через bulk «Включить все») не оживлял запрещённое.
                    if is_active and await channels_repo.is_channel_blacklisted(
                        session, channel_id
                    ):
                        return _err(
                            "Канал в blacklist — нельзя включить.",
                            channel_id=channel_id,
                            is_active=is_active,
                            action="set_active",
                        )
                    ok = await channels_repo.set_channel_active(
                        session, channel_id, is_active
                    )
            if not ok:
                return _err(
                    "Канал не найден.",
                    channel_id=channel_id,
                    is_active=is_active,
                    action="set_active",
                )
            return _ok({
                "channel_id": channel_id,
                "is_active": is_active,
                "action": "set_active",
            })

        self._dispatch_action(
            self.contacts_channel_action_done, run(),
            action="set_active",
            channel_id=channel_id,
            is_active=is_active,
        )

    @Slot(str)
    def request_contacts_company_merge_picker(self, payload_json: str) -> None:
        try:
            payload = json.loads(payload_json)
            absorbed_id = int(payload["absorbed_id"])
            search = payload.get("search")
            if search is not None:
                search = str(search)
        except (ValueError, TypeError, KeyError) as e:
            _log_invalid_payload("request_contacts_company_merge_picker", e)
            self.contacts_company_merge_picker_loaded.emit(_err(f"Неверные поля: {e}"))
            return

        async def run() -> str:
            async with self._session_factory() as session:
                rows = await companies_list.list_companies_with_counts(session, search=search)
            return _ok({
                "absorbed_id": absorbed_id,
                "search": search or "",
                "companies": [
                    _company_picker_row_to_dict(r) for r in rows
                    if r.company.id != absorbed_id
                ],
            })

        self._dispatch(self.contacts_company_merge_picker_loaded, run())

    @Slot(str)
    def contacts_create_company(self, payload_json: str) -> None:
        try:
            payload = json.loads(payload_json)
            fields = read_new_company_fields(payload)
            name = fields["name"]
        except (ValueError, TypeError) as e:
            _log_invalid_payload("contacts_create_company", e)
            self.contacts_company_action_done.emit(_err(f"Неверные поля: {e}"))
            return
        if not name:
            self.contacts_company_action_done.emit(
                _err("Название обязательно.", action="create_company")
            )
            return

        async def run() -> str:
            try:
                async with self._session_factory() as session:
                    co = await companies_card.create_company(session, **fields)
                    await session.commit()
            except IntegrityError:
                return _err(
                    f"Компания «{name}» уже существует.",
                    action="create_company",
                )
            except Exception as e:
                logger.exception("contacts_create_company failed")
                return _err(f"{type(e).__name__}: {e}", action="create_company")
            return _ok({"action": "create_company", "created_id": co.id})

        self._dispatch(self.contacts_company_action_done, run())

    @Slot(str)
    def contacts_update_company(self, payload_json: str) -> None:
        try:
            payload = json.loads(payload_json)
            company_id = int(payload["company_id"])
        except (ValueError, TypeError, KeyError) as e:
            _log_invalid_payload("contacts_update_company", e)
            self.contacts_company_action_done.emit(_err(f"Неверные поля: {e}"))
            return
        kwargs: dict = {}
        for key in ("name", "website", "notes"):
            if key in payload:
                kwargs[key] = payload[key]
        if "aliases" in payload:
            raw = payload["aliases"]
            if not isinstance(raw, (str, list)):
                self.contacts_company_action_done.emit(
                    _err("aliases должен быть list или строка через запятую.")
                )
                return
            kwargs["aliases"] = read_company_spellings(raw)
        if not kwargs:
            self.contacts_company_action_done.emit(
                _err("Нечего обновлять.", company_id=company_id)
            )
            return

        async def run() -> str:
            async with self._session_factory() as session:
                async with session.begin():
                    ok = await companies_card.update_company_fields(
                        session, company_id, **kwargs,
                    )
            if not ok:
                return _err(
                    "Компания не найдена или название пустое.",
                    company_id=company_id, action="update_company",
                )
            return _ok({
                "action": "update_company",
                "company_id": company_id,
                "fields": list(kwargs.keys()),
            })

        self._dispatch(self.contacts_company_action_done, run())

    @Slot(int)
    def contacts_delete_company(self, company_id: int) -> None:
        async def run() -> str:
            async with self._session_factory() as session:
                ok = await companies_card.delete_company(session, company_id)
                if not ok:
                    return _err(
                        "Компания не найдена.",
                        company_id=company_id, action="delete_company",
                    )
                await session.commit()
            return _ok({"action": "delete_company", "company_id": company_id})

        self._dispatch(self.contacts_company_action_done, run())

    @Slot(str)
    def contacts_merge_company(self, payload_json: str) -> None:
        try:
            payload = json.loads(payload_json)
            absorbed_id = int(payload["absorbed_id"])
            survivor_id = int(payload["survivor_id"])
        except (ValueError, TypeError, KeyError) as e:
            _log_invalid_payload("contacts_merge_company", e)
            self.contacts_company_action_done.emit(_err(f"Неверные поля: {e}"))
            return

        async def run() -> str:
            try:
                async with self._session_factory() as session:
                    async with session.begin():
                        await companies_card.merge_company(
                            session,
                            absorbed_id=absorbed_id,
                            survivor_id=survivor_id,
                        )
            except ValueError as e:
                return _err(str(e), absorbed_id=absorbed_id, action="merge_company")
            except Exception as e:
                logger.exception("contacts_merge_company failed")
                return _err(
                    f"{type(e).__name__}: {e}",
                    absorbed_id=absorbed_id, action="merge_company",
                )
            return _ok({
                "action": "merge_company",
                "absorbed_id": absorbed_id,
                "survivor_id": survivor_id,
            })

        self._dispatch(self.contacts_company_action_done, run())

    @Slot(int)
    def contacts_add_company_to_blacklist(self, company_id: int) -> None:
        """Insert / re-activate a kind="company" blacklist row for this
        company. Value is the company name. Idempotent.
        """
        async def run() -> str:
            async with self._session_factory() as session:
                co = await session.get(Company, company_id)
                if co is None:
                    return _err(
                        "Компания не найдена.",
                        company_id=company_id, action="blacklist",
                    )
                value = companies_card.company_blacklist_preferred_value(co)
                if value is None:
                    return _err(
                        "У компании нет имени.",
                        company_id=company_id, action="blacklist",
                    )
                _, outcome = await blacklist.create_blacklist(
                    session, kind="company", value=value,
                )
                await session.commit()
            self.contacts_lists_changed.emit()
            return _ok({
                "action": "blacklist",
                "company_id": company_id,
                "value": value,
                "existed": outcome != "created",
                "was_inactive": outcome == "reactivated",
            })

        self._dispatch(self.contacts_company_action_done, run())

    @Slot(int)
    def contacts_remove_company_from_blacklist(self, company_id: int) -> None:
        async def run() -> str:
            async with self._session_factory() as session:
                co = await session.get(Company, company_id)
                if co is None:
                    return _err(
                        "Компания не найдена.",
                        company_id=company_id, action="unblacklist",
                    )
                candidates = companies_card.company_blacklist_candidates(co)
                if not candidates:
                    return _err(
                        "У компании нет имени.",
                        company_id=company_id, action="unblacklist",
                    )
                updated = await blacklist.deactivate_blacklist_values(
                    session, "company", candidates,
                )
                await session.commit()
            self.contacts_lists_changed.emit()
            return _ok({
                "action": "unblacklist",
                "company_id": company_id,
                "updated": updated,
            })

        self._dispatch(self.contacts_company_action_done, run())

    def _kick_health(self) -> None:
        async def run() -> str:
            results = {"db": False, "tg": False, "chat": False, "embed": False}

            try:
                async with self._session_factory() as session:
                    await session.execute(sa_text("SELECT 1"))
                results["db"] = True
            except Exception as e:
                logger.debug("healthcheck: db probe failed: %s", e)

            # TG: проверяем живость уже работающего Pyrogram-клиента в
            # Bot.run. ``is_connected`` отражает state MTProto-сессии и
            # отваливается, когда Pyrogram'овский heartbeat ловит timeout
            # (≈30-60с после реального отключения сети). Параллельный
            # connect отсюда устроил бы конфликт сессий, поэтому смотрим
            # только на бот'овский клиент. До старта бота (нет
            # session_string или ранний этап init'а) — false: пока сессия
            # не поднята, считать TG здоровым нечестно.
            results["tg"] = bool(
                self._bot is not None
                and self._bot.is_ready
                and getattr(self._bot._client, "is_connected", False)
            )

            if self._rs.chat is not None:
                client = lm_studio.make_client(self._rs.chat)
                try:
                    models = await lm_studio.list_models(client)
                    results["chat"] = self._rs.chat.model in models
                except Exception as e:
                    logger.debug("healthcheck: chat probe failed: %s", e)
                finally:
                    await client.aclose()

            if self._rs.embed is not None:
                client = lm_studio.make_client(self._rs.embed)
                try:
                    models = await lm_studio.list_models(client)
                    results["embed"] = self._rs.embed.model in models
                except Exception as e:
                    logger.debug("healthcheck: embed probe failed: %s", e)
                finally:
                    await client.aclose()

            return _ok(results)

        self._dispatch(self.health_changed, run())


def _profile_to_dict(p, languages=None) -> dict | None:
    if p is None:
        return None
    return {
        "first_name": p.first_name,
        "last_name": p.last_name,
        "title": p.title,
        "email": p.email,
        "phone": p.phone,
        "location": p.location,
        "telegram_username": p.telegram_username,
        "github_url": p.github_url,
        "education": p.education,
        "free_preferences": p.free_preferences,
        "grades": list(p.grades or []),
        "work_format": list(p.work_format or []),
        "languages": [
            {"language": lang.language, "level": lang.level}
            for lang in (languages or [])
        ],
        "updated_at": _iso(p.updated_at),
    }


def _filter_set(values, allowed: tuple[str, ...]) -> list[str]:
    """Keep only known values, in `allowed` order, no duplicates."""
    if not isinstance(values, list):
        return []
    seen = {str(v) for v in values if isinstance(v, str)}
    return [v for v in allowed if v in seen]


def _filter_languages(items) -> list[tuple[str, str]]:
    """Validate language entries from the UI.

    Drops rows with empty language name. Falls back to ``B2`` if the level
    is unknown (UI-typed garbage shouldn't break save). De-dups by language
    name (case-insensitive) — last write wins, matching the UI behaviour
    where editing replaces the row.
    """
    if not isinstance(items, list):
        return []
    seen: dict[str, str] = {}  # lower(name) -> name
    out: list[tuple[str, str]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        name = str(item.get("language") or "").strip()
        if not name:
            continue
        level = str(item.get("level") or "").strip()
        if level not in LANGUAGE_LEVELS:
            level = "B2"
        key = name.lower()
        if key in seen:
            # Replace previous tuple for this name with the newer level.
            for i, (existing, _) in enumerate(out):
                if existing.lower() == key:
                    out[i] = (existing, level)
                    break
            continue
        seen[key] = name
        out.append((name, level))
    return out


def _skill_to_dict(s) -> dict:
    return {
        "id": s.id,
        "category": s.category,
        "name": s.name,
        "level": s.level,
        "aliases": list(s.aliases or []),
    }


def _exp_to_dict(e) -> dict:
    return {
        "id": e.id,
        "company": e.company,
        "company_url": e.company_url,
        "role": e.role,
        "start_date": e.start_date.isoformat() if e.start_date else None,
        "end_date": e.end_date.isoformat() if e.end_date else None,
        "achievements": list(e.achievements or []),
        "responsibilities": list(e.responsibilities or []),
        "skill_names": [s.name for s in (e.skills or [])],
    }


# Thin compat alias kept so the two existing call-sites read naturally
# ("matched_set"). The actual lookup logic lives in ``domain.scoring.build_skill_lookup``
# — one place defines what "this stack item is known to the profile" means
# for both the UI chip highlighting and the scoring penalty.
_build_matched_set = build_skill_lookup


def _stack_items(stack, matched_set: set[str]) -> list[dict]:
    out: list[dict] = []
    for item in (stack or []):
        if isinstance(item, str) and item:
            out.append(
                {"name": item, "matched": skill_key(item) in matched_set}
            )
    return out


def _vacancy_detail_to_dict(
    detail, matched_set: set[str], score_threshold: int,
) -> dict:
    """Detail-pane payload. Linked Company / HR / Channel fields fall back
    to the raw parsed strings on the vacancy when the FK isn't set, so the
    UI can always render *something* without lazy-loading."""
    v = detail.vacancy
    company_name = v.company.name if v.company is not None else v.company_name
    company_website = v.company.website if v.company is not None else None
    channel_username = v.channel.username if v.channel is not None else None
    hr_block = None
    if v.hr is not None:
        hr_block = {
            "id": v.hr.id,
            "name": v.hr.name,
            "telegram_username": v.hr.telegram_username,
            "avatar": _avatar_data_url(v.hr.avatar),
        }
    return {
        "id": v.id,
        "status": v.status.value,
        "score": v.score,
        "score_threshold": score_threshold,
        "title": v.title,
        "description": v.description,
        "raw_text": v.raw_text,
        "company_id": v.company_id,
        "company_name": company_name,
        "company_website": company_website,
        "hr": hr_block,
        "grade": v.grade,
        "salary": v.salary,
        "remote": v.remote,
        "location": v.location,
        "channel_username": channel_username,
        "source_msg_id": v.source_msg_id,
        "source_url": v.source_url,
        "stack": _stack_items(v.stack, matched_set),
        "notes": v.notes,
        "posted_at": _iso(v.posted_at),
        "created_at": _iso(v.created_at),
        "history": [
            {
                "id": h.id,
                "previous_status": h.previous_status.value if h.previous_status else None,
                "status": h.status.value,
                "explanation": h.explanation,
                "applied": h.applied,
                "source": h.source.value,
                "changed_at": _iso(h.changed_at),
            }
            for h in detail.history
        ],
        "events": [
            {
                "id": e.id,
                "kind": e.kind,
                "payload": e.payload,
                "created_at": _iso(e.created_at),
            }
            for e in detail.events
        ],
    }


def _avatar_data_url(blob: bytes | None) -> str | None:
    """Encode raw avatar bytes (Telegram delivers JPEGs) as a data URL.

    The frontend embeds these directly in <img src=...> so we ship them
    inline with the list/detail payload — Telegram small-file avatars are
    a few KB each, so the JSON bloat is negligible vs a separate per-row
    fetch round-trip.
    """
    if not blob:
        return None
    return "data:image/jpeg;base64," + base64.b64encode(blob).decode("ascii")


def _hr_picker_row_to_dict(item) -> dict:
    """Shape for the HR-picker rows (§5) AND Contacts/HR list (05).

    Includes ``unread_count`` and ``is_blacklisted`` for the lime unread
    badge / red blacklist marker in Contacts/HR; the picker ignores them.
    """
    hr = item.hr
    return {
        "id": hr.id,
        "name": hr.name,
        "telegram_username": hr.telegram_username,
        "telegram_user_id": hr.telegram_user_id,
        "vacancy_count": item.vacancy_count,
        "last_company_name": item.last_company_name,
        "unread_count": item.unread_count,
        "is_blacklisted": getattr(item, "is_blacklisted", False),
        "avatar": _avatar_data_url(hr.avatar),
    }


def _blacklist_row_to_dict(row: Blacklist) -> dict:
    """Shape для Contacts/Blacklist (08).

    `kind` — свободная строка (исторически использовались "hr", "company";
    добавляем "keyword", "channel"). Frontend различает кинды и красит чипы.
    """
    return {
        "id": row.id,
        "kind": row.kind,
        "value": row.value,
        "reason": row.reason,
        "active": bool(row.active),
        "created_at": _iso(row.created_at),
    }


def _channel_row_to_dict(item) -> dict:
    """Shape for the Contacts/Channels list (07).

    Avatar carried as base64 data URL; same convention as HR rows.
    """
    ch = item.channel
    return {
        "id": ch.id,
        "username": ch.username,
        "title": ch.title,
        "is_active": bool(ch.is_active),
        "vacancy_count": item.vacancy_count,
        "avatar": _avatar_data_url(ch.avatar),
        "is_blacklisted": getattr(item, "is_blacklisted", False),
    }


def _company_picker_row_to_dict(item) -> dict:
    """Shape for the Company-picker rows (§6) AND Contacts/Companies list
    (06). ``is_blacklisted`` rides along for the red marker in the list."""
    co = item.company
    return {
        "id": co.id,
        "name": co.name,
        "website": co.website,
        "aliases": list(co.aliases or []),
        "vacancy_count": item.vacancy_count,
        "is_blacklisted": getattr(item, "is_blacklisted", False),
    }


def _vacancy_list_row_to_dict(
    v, matched_set: set[str], activity_by_id: dict[int, Any] | None = None
) -> dict:
    """Shape for the list pane (slice 2). Linked Company.name wins over the
    raw vacancy.company_name; falls back to raw if no FK is set. Each stack
    item is paired with a ``matched`` flag against the casefolded profile
    skills + aliases set so the UI can highlight relevant chips."""
    if v.company is not None:
        company = v.company.name
    else:
        company = v.company_name
    channel_username = v.channel.username if v.channel is not None else None
    last_activity = None
    if activity_by_id:
        last_activity = activity_by_id.get(int(v.id))
    return {
        "id": v.id,
        "status": v.status.value,
        "score": v.score,
        "title": v.title,
        "description": v.description,
        "notes": v.notes,
        "company": company,
        "company_id": v.company_id,
        "company_raw_name": v.company_name,
        "hr_name": v.hr.name if v.hr is not None else None,
        "hr_username": v.hr.telegram_username if v.hr is not None else None,
        "hr_id": v.hr_id,
        "channel_username": channel_username,
        "grade": v.grade,
        "salary": v.salary,
        "remote": v.remote,
        "stack": _stack_items(v.stack, matched_set),
        "posted_at": _iso(v.posted_at),
        "created_at": _iso(v.created_at),
        "last_activity_at": _iso(last_activity),
    }


def _stat_cv(cv_path: str) -> dict | None:
    if not cv_path:
        return None
    try:
        p = Path(cv_path)
        st = p.stat()
        return {"name": p.name, "size": st.st_size, "exists": True}
    except OSError:
        return {"name": Path(cv_path).name, "size": 0, "exists": False}


def _read_cv_text(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        from pypdf import PdfReader

        reader = PdfReader(str(path))
        return "\n\n".join(page.extract_text() or "" for page in reader.pages)
    raw = path.read_bytes()
    for enc in ("utf-8-sig", "utf-8", "cp1251"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")
