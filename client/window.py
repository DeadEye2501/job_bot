"""Окно приложения: как оно открывается и чем гасится.

Точка входа зовёт отсюда `run_ui()`. Всё, что живёт дольше одного экрана —
мотор, хозяйство моста, бот, — заводится здесь и здесь же гасится: окно и есть
то, чему они ровесники.
"""

from __future__ import annotations

import logging
import sys
from concurrent.futures import Future
from pathlib import Path
from typing import Any

import webview
from sqlalchemy.ext.asyncio import async_sessionmaker

from adapters import db
from backend.bot.media import MEDIA_DIR
from backend.models import BotMode
from backend.repository.bot_mode import write_mode
from backend.runtime_settings import RuntimeSettings
from client import raise_window, window_size
from client.bridge import Api, AsyncRunner, lifespan
from client.serving import served_files
from config import get_database_url


logger = logging.getLogger(__name__)


CLIENT_DIR = Path(__file__).parent
WEB_DIST = CLIENT_DIR / "web" / "dist"
ICON_FILE = CLIENT_DIR / "icon.ico"

_ENGINE_CLOSING_WAIT_S = 5.0
"""Сколько ждём, пока движок базы отпустит соединения.

Столько же, сколько ждут бота: закрывается движок обычно мгновенно, а
затягивает его та же беда, что и бота, — незакрытая работа на моторе. Дольше
держать закрытие незачем: файл базы всё равно освободится со смертью процесса.
"""

WINDOW_BACKGROUND = "#2d2d2f"
"""Чем залито окно, пока страница его не закрыла.

Тот же цвет, что `--bg-secondary` в палитре, и повторён он здесь потому, что
читать его оттуда некому: палитра — таблица стилей, а красит окно система ещё
до того, как страница вообще открыта. Без этой строки pywebview заливает окно
белым, и при растягивании, пока WebView2 не догнал новый размер, вместо
оболочки видна ярко-белая вспышка со шлейфом прежнего кадра.
"""



def run_ui() -> int:
    """Открыть окно и держать его, пока человек не закроет.

    Порядок сборки значим. Мотор заводится первым — на нём делается всё
    остальное, включая чтение настроек. Режим сбрасывается в выключенный до
    подъёма хозяйства: иначе бот принялся бы за работу раньше, чем человек
    увидел окно. Хозяйство поднимается до окна, потому что окну оно нужно
    поверхностью.
    """
    _own_the_taskbar_icon()
    logger.info("окно открывается")
    runner = _open_runner()
    engine, session_factory = _open_database()
    rs: RuntimeSettings = _await(runner.submit(prepare(session_factory)))
    _drop_stale_session_files(rs)

    hub = lifespan.start(runner, session_factory, rs, engine=engine)
    listening = None
    try:
        window = _open_window(hub, settled=rs.wizard_completed)
        # Окно — хозяйству: до диалога выбора файла добраться больше неоткуда,
        # а мост собран раньше окна и сам его не видит.
        hub.window = window
        listening = raise_window.listen(window)
        webview.start(icon=_icon())
    finally:
        # Через `finally`, потому что окно поднимается не всегда: на машине без
        # WebView2 первый же запуск отказывает здесь. Пройди отказ мимо, бот
        # остался бы работать до самой смерти процесса — вместо того чтобы
        # проститься с Telegram и закрыть базу.
        _put_out(hub, runner, listening)
    return 0


def _open_window(hub, *, settled: bool):
    """Поднять окно под ту поверхность, которую человек сейчас увидит.

    Настроенное приложение открывается своим размером и тянется; мастер —
    своим, меньшим, и не тянется вовсе. Дойдя до конца, мастер растит окно сам
    (`window_size.grow_to_main`): pywebview отдаёт размеры системе один раз, и
    открытое по-мастерски окно иначе таким и осталось бы.
    """
    size = window_size.MAIN if settled else window_size.WIZARD
    return webview.create_window(
        "Job Bot",
        served_files(WEB_DIST, MEDIA_DIR),
        js_api=Api(hub),
        width=size[0],
        height=size[1],
        min_size=size,
        resizable=settled,
        background_color=WINDOW_BACKGROUND,
    )


def _put_out(hub, runner, listening) -> None:
    """Погасить всё, что держало открытое окно, в порядке от верхнего к нижнему.

    Слушатель первым: пока он жив, вторая копия получает от него обещание
    показать окно — а показывать уже нечего, и человек, нажавший ярлык, не
    увидит ничего.

    Мост раньше мотора: гашение моста отправляет остановку бота на мотор и ждёт
    её. Погасни мотор первым, этой работе некуда было бы уехать.

    Движок последним и через мотор: закрывать его — работа асинхронная, а
    делать её после остановки мотора уже негде.
    """
    logger.info("окно закрыто, гасим мост")
    if listening is not None:
        listening.close()
    lifespan.stop(hub)
    if hub.engine is not None:
        runner.submit(hub.engine.dispose()).result(timeout=_ENGINE_CLOSING_WAIT_S)
    runner.stop()


async def prepare(session_factory) -> RuntimeSettings:
    """Настройки в том виде, в каком окно застаёт их при открытии.

    Режим сбрасывается в выключенный, каким бы он ни остался со вчера: он
    переживает выход, и человек, выключивший бота вечером, утром увидел бы его
    работающим ещё до того, как открылось окно.
    """
    rs = await RuntimeSettings.load(session_factory)
    async with session_factory() as session:
        async with session.begin():
            await write_mode(session, BotMode.OFF)
    return rs


def _open_runner() -> AsyncRunner:
    """Мотор под окном. Объявлен отдельно, чтобы сторожа подменяли его целиком:
    свой поток и свой цикл в прогоне встали бы рядом с его собственным."""
    return AsyncRunner()


def _open_database() -> tuple[Any, async_sessionmaker]:
    """Движок базы и фабрика сессий над ним.

    `expire_on_commit=False` — несущая настройка: репозиторий и бот держат
    записи живыми после закрытия сессии, и с обратным значением первое же
    обращение к полю уронило бы отсоединённую запись.
    """
    engine = db.make_engine(get_database_url())
    return engine, async_sessionmaker(engine, expire_on_commit=False)


def _await(future: Future) -> Any:
    """Дождаться работы, отправленной на мотор до того, как окно открылось."""
    return future.result()


def _icon() -> str | None:
    """Путь к иконке окна, либо пусто, если её не оказалось.

    Пропавшая иконка — след неудачной упаковки: библиотека молча берёт свою, и
    человек видит чужую картинку в панели задач, ничего не понимая. Запись в
    журнал — единственное, по чему это потом находят.
    """
    if not ICON_FILE.exists():
        logger.warning("иконки нет по пути %s — окно откроется с чужой", ICON_FILE)
        return None
    return str(ICON_FILE.resolve())


def _own_the_taskbar_icon() -> None:
    """Назвать себя системе до того, как поднимется окно.

    Windows складывает окна в панели задач по этому имени. Без него приложение
    садится под именем интерпретатора и делит значок с любым другим питоном.
    """
    if sys.platform != "win32":
        return
    import ctypes

    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("DeadEye.JobBot.UI")
    except (AttributeError, OSError):
        logger.warning("имя для панели задач не принято", exc_info=True)


def _drop_stale_session_files(rs: RuntimeSettings) -> None:
    """Снести файлы сеанса Telegram, оставшиеся от прежнего устройства.

    Сеанс лежит в базе зашифрованным, и бот поднимается из него, а файлы рядом
    хранят тот же ключ открытым текстом. Пока сеанса в базе нет, файлы могут
    быть единственным, что осталось, — потому и сносим только при живом.
    """
    if not rs.has_tg_session:
        return
    from adapters.telegram import SESSIONS_DIR

    if not SESSIONS_DIR.exists():
        return
    dropped = 0
    for one in SESSIONS_DIR.iterdir():
        if not one.is_file() or one.suffix not in (".session", ".session-journal"):
            continue
        try:
            one.unlink()
            dropped += 1
        except OSError:
            logger.exception("файл сеанса не удалён: %s", one.name)
    if dropped:
        logger.info("снесено файлов сеанса: %d", dropped)
