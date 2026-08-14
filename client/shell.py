"""Окно Qt, показывавшее страницу через QWebEngineView.

Точка входа зовёт отсюда `run_ui()` — так было и так остаётся до слайса А3, где
её место занимает окно pywebview (`client/window.py`).

**Моста в этом окне больше нет.** Публиковать поверхность канал Qt умел только
объектами `QObject` со слотами, а поверхность стала деревом обычных доменов,
отвечающих возвратом. Пока окна pywebview не существует, страница здесь
открывается без `api` — приложение на этой ветке всё равно не открывается с
первого же переехавшего домена, и довод записан в плане.
"""

import logging
import sys
from concurrent.futures import Future
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QIcon
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QApplication, QMainWindow
from sqlalchemy.ext.asyncio import async_sessionmaker

from adapters import db
from backend.models import BotMode
from backend.runtime_settings import RuntimeSettings
from client.bridge import AsyncRunner
from client import raise_window
from config import get_database_url


logger = logging.getLogger(__name__)


CLIENT_DIR = Path(__file__).parent
WEB_DIR = CLIENT_DIR / "web"
WIZARD_HTML = WEB_DIR / "wizard.html"
MAIN_HTML = WEB_DIR / "main.html"
ICON_FILE = CLIENT_DIR / "icon.ico"
if not ICON_FILE.exists():
    # QIcon молча возвращает null-icon на отсутствующем файле, окно
    # рендерится с дефолтной Qt-иконкой и юзер на packaging-issue
    # натыкается визуально, без диагностики. Лог при старте даёт ops'у
    # сразу понять «иконка пропала, в .exe не запаковалась».
    logger.warning("ICON_FILE missing at %s — window will render without icon", ICON_FILE)

WIZARD_WINDOW_SIZE = (640, 620)
MAIN_WINDOW_DEFAULT = (900, 660)
# Min equals default — the layout has lots of elements and wraps badly
# below this. Window can grow but not shrink past the design size.
MAIN_WINDOW_MIN = MAIN_WINDOW_DEFAULT


def _await(future: Future) -> Any:
    return future.result()


def run_ui() -> int:
    # Windows taskbar groups by AppUserModelID — without an explicit one
    # the bot inherits python.exe's icon. Set ours before QApplication exists.
    if sys.platform == "win32":
        try:
            import ctypes

            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                "DeadEye.JobBot.UI"
            )
        except Exception:
            logger.warning("Failed to set Windows AppUserModelID; taskbar icon may group with python.exe", exc_info=True)

    logger.info("UI starting")
    app = QApplication(sys.argv)
    icon = QIcon(str(ICON_FILE.resolve()))
    app.setWindowIcon(icon)

    runner = AsyncRunner()

    engine = db.make_engine(get_database_url())
    # expire_on_commit=False — load-bearing: весь repository/ и bot.py
    # держит ORM-объекты живыми после session.close()/commit() (например,
    # ``hr_for_send`` из flows/parse.py, parse_and_update_vacancy, используется уже
    # вне сессии для авто-отправки). С expire_on_commit=True атрибут
    # доступ кинул бы DetachedInstanceError. Не трогать.
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    rs: RuntimeSettings = _await(
        runner.submit(RuntimeSettings.load(session_factory))
    )
    # Always start with the bot in Off mode — running app == bot quietly
    # waiting for the user to flip the toggle. Persisted Full / DM Only from
    # a previous session would otherwise spring the bot to life on launch.
    logger.info("Forcing bot mode to Off on launch")
    _await(runner.submit(rs.set_mode(BotMode.OFF)))

    # Sessions cleanup: если в БД лежит Fernet-encrypted session_string
    # (Bot работает в in-memory mode), локальные sessions/*.session
    # файлы уже не используются и хранят cleartext auth_key. Сносим
    # их — security review L3.
    if rs.tg is not None and rs.tg.session_string:
        try:
            from adapters.telegram import SESSIONS_DIR as sessions_dir
            if sessions_dir.exists():
                removed = 0
                for p in sessions_dir.iterdir():
                    if p.is_file() and p.suffix in (".session", ".session-journal"):
                        try:
                            p.unlink()
                            removed += 1
                        except Exception as e:
                            logger.debug("session cleanup: %s: %s", p.name, e)
                if removed:
                    logger.info(
                        "session cleanup: removed %d stale .session file(s)",
                        removed,
                    )
        except Exception:
            logger.exception("session cleanup failed")

    window = QMainWindow()
    window.setWindowTitle("Job Bot")
    window.setWindowIcon(icon)
    # Слушаем просьбы второй копии сразу, как появилось что показывать, — до
    # загрузки страницы и до `show()`: всё это время человек уже может нажать
    # ярлык второй раз. Имя держится до конца работы, потому что слушатель жив,
    # пока на него ссылаются.
    _second_copy_listener = raise_window.listen(window)

    view = QWebEngineView()
    # Suppress the default browser right-click menu (Back / Reload / View
    # source ...) — this is a desktop app, not a browser.
    view.setContextMenuPolicy(Qt.NoContextMenu)
    if rs.wizard_completed:
        logger.info("Wizard completed; entering main app")
        _enter_main_mode(window, view)
    else:
        logger.info("Wizard incomplete; showing wizard screen")
        _enter_wizard_mode(window, view)

    window.setCentralWidget(view)

    def on_quit() -> None:
        logger.info("Application quit requested")
        runner.stop()

    app.aboutToQuit.connect(on_quit)

    window.show()
    return app.exec()


def _enter_wizard_mode(window: QMainWindow, view: QWebEngineView) -> None:
    w, h = WIZARD_WINDOW_SIZE
    window.setMinimumSize(w, h)
    window.setMaximumSize(w, h)
    window.resize(w, h)
    view.load(QUrl.fromLocalFile(str(WIZARD_HTML.resolve())))


def _enter_main_mode(window: QMainWindow, view: QWebEngineView) -> None:
    window.setMaximumSize(16777215, 16777215)
    window.setMinimumSize(*MAIN_WINDOW_MIN)
    window.resize(*MAIN_WINDOW_DEFAULT)
    view.load(QUrl.fromLocalFile(str(MAIN_HTML.resolve())))
