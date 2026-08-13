"""Поверхность окна первого запуска."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Callable, Coroutine

import httpx
from PySide6.QtCore import QObject, Signal, Slot
from PySide6.QtWidgets import QFileDialog, QMainWindow, QWidget
from sqlalchemy.ext.asyncio import async_sessionmaker

from adapters import lm_studio
from adapters.lm_studio import LlmProviderConfig
from backend.llm.cv import parse_cv
from backend.repository import profile as profile_repo
from backend.runtime_settings import RuntimeSettings
from backend.telegram_login import TelegramLogin
from client.bridge.answer import _dispatch_json, _err, _ok
from client.bridge.cv_file import _read_cv_text
from client.bridge.llm import _do_list_models_for_creds, _do_llm_probe
from client.bridge.login import TelegramLoginSlots
from client.bridge.payload import _log_invalid_payload
from client.bridge.runner import AsyncRunner


logger = logging.getLogger(__name__)


class WizardApi(TelegramLoginSlots, QObject):
    """Exposed to JS as `window.api`. All long-running ops are non-blocking;
    JS must connect to the matching `*_done` signal to get the result."""

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
        _dispatch_json(self._runner, signal, coro)

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
