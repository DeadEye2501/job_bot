"""Job Bot — single CLI entry point.

Run:
    python main.py            — launch the desktop UI (wizard on first run,
                                otherwise the main app window with the bot
                                running in the background).
"""

import importlib
import logging
import sys
import threading
import traceback

from backend.log_file import LogFileHandler
from config import LOG_KEPT, get_lock_path, get_log_path


def _use_utf8_stdout() -> None:
    """Перенастроить вывод на UTF-8, а неудачу показать, не проглотив.

    Логирование к этому мигу ещё не настроено, поэтому сообщать можно только
    прямо в поток ошибок. Молчать нельзя: без перенастройки вывод ломается на
    кириллице, и виновника потом не найти.

    В оконной сборке потока ошибок нет вовсе, и сообщение пропадёт. Канал,
    переживающий его отсутствие, теперь есть — файл журнала, — но берёт он
    запись журнала, а её к этому мигу ещё не из чего сделать: логирование
    настраивается ниже.
    """
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        if sys.stderr is None:
            return  # оконная сборка: писать некуда
        traceback.print_exc()


_use_utf8_stdout()


LOG_BYTES = 5 * 1024 * 1024


def _log_handlers() -> list[logging.Handler]:
    """Куда пишется журнал приложения.

    Файл — всегда: в оконной сборке (`console=False`) `sys.stdout` и
    `sys.stderr` равны `None`, и обработчик, настроенный на поток, теряет всё
    молча. Кольцевой буфер экрана «Логи» тоже не спасает — он в памяти и
    пропадает вместе с окном, а разбирать падение приходится после него.

    Кодировка задаётся явно: без неё файл открылся бы кодировкой системы, а
    в журнал попадают тексты из Telegram — эмодзи и письменности, которых в
    однобайтовой кодировке нет, сорвали бы запись.

    Открытие отложено: без этого пустой файл заводился бы на каждый ввоз
    модуля, в том числе прогоном тестов и инструментами.
    """
    handlers: list[logging.Handler] = [
        LogFileHandler(
            get_log_path(),
            maxBytes=LOG_BYTES,
            backupCount=LOG_KEPT,
            encoding="utf-8",
            delay=True,
        )
    ]
    if sys.stdout is not None:
        handlers.append(logging.StreamHandler(sys.stdout))
    return handlers


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=_log_handlers(),
)
# Attach the in-memory buffer handler that backs the UI «Логи» screen.
# Идемпотентно — повторный install() не-op.
from backend import log_buffer as _log_buffer, log_secrets as _log_secrets
_log_buffer.install()
# Secret-redaction filter ставим ДО первого logger.* и ПОСЛЕ того, как все
# обработчики на месте: он вешается на них, а не на logger. Иначе Bearer-
# токены / api_hash / session-string'и из третьих либ (httpx debug, pyrogram,
# sqlalchemy echo) легли бы в файл журнала как есть — и пережили бы окно.
_log_secrets.install_secret_filter()
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


def _log_uncaught(exc_type, exc, tb) -> None:
    """Отдать в журнал падение, которое некому было поймать.

    Штатный ответ на такое — печать трассировки в поток ошибок, а у оконной
    сборки его нет: в файле оставались бы обычная работа и обрыв на полуслове.

    Остановка по воле человека падением не считается — так же, как у потоков
    не считается `SystemExit`: записанная, она зажгла бы в окне счётчик
    ошибок на обычном выходе из приложения.
    """
    if issubclass(exc_type, KeyboardInterrupt):
        return
    logger.critical("Необработанное исключение", exc_info=(exc_type, exc, tb))


def _log_uncaught_in_thread(args) -> None:
    """То же для постороннего потока: у них своя дорога мимо `sys.excepthook`.

    `SystemExit` пропускается — так же, как его пропускает штатный крючок:
    поток, завершивший себя сам, падением не является, а запись о нём
    зажгла бы счётчик ошибок в окне.
    """
    if args.exc_type is SystemExit:
        return
    _log_uncaught(args.exc_type, args.exc_value, args.exc_traceback)


sys.excepthook = _log_uncaught
threading.excepthook = _log_uncaught_in_thread


def _started_or_told_why() -> int:
    """Пройти пролог и открыть окно; отказ показать человеку и уйти.

    Отделено от `main`, потому что предмет другой: там замок и разговор двух
    копий, здесь — сам запуск и его беда.

    Ввозы отложены по той же причине, что и у зовущего: ввоз `client.window`
    тянет за собой окно, а ввоз `main` правит корневой logger.
    """
    from backend import bootstrap
    from backend.crypto import _check_keyring_backend
    from client.trouble_box import show_trouble
    from client.window import run_ui

    # Весь пролог под одним перехватом. Работ до окна четыре — хранилище
    # ключей, схема базы, подъём базы и чтение настроек внутри `run_ui`, — и
    # отказ любой из них выглядел одинаково: человек жмёт ярлык, и не
    # происходит ничего. Столько раз, сколько он нажмёт.
    #
    # Небезопасное или сломанное хранилище ключей отбивается первым: с ним
    # секреты ушли бы на диск открытым текстом либо потерялись после первого
    # же запуска.
    #
    # Схема доводится до порядка ДО того, как поднимется окно: alembic крутит
    # внутри себя свой asyncio.run, и делать это под живым циклом окна нельзя.
    try:
        _check_keyring_backend()
        bootstrap.ensure_schema()
        return run_ui()
    except Exception as e:
        logger.critical("запуск не состоялся", exc_info=True)
        show_trouble(
            f"Не удалось запуститься: {e}\n\n"
            f"Подробности — в журнале: {get_log_path()}"
        )
        return 2


def _served_mac_watcher() -> bool:
    """Отработать сторожем привязанных процессов мака, если позвали им.

    Сторож — эта же программа с флагом: в замороженной сборке другого
    исполняемого нет. Ему не нужны ни замок, ни окно. Мак-модуль грузится
    строкой, чтобы не попасть в Windows-сборку.
    """
    if sys.platform != "darwin":
        return False
    tie_watch = importlib.import_module("adapters.tie_watch_macos")
    if sys.argv[1:2] != [tie_watch.TIE_WATCH_FLAG]:
        return False
    tie_watch.watch(sys.stdin)
    return True


def main() -> int:
    if _served_mac_watcher():
        return 0

    from backend import updater
    from backend.single_instance import hold_the_only_copy

    # Копия-подменщик — до замка: его ещё держит закрывающееся приложение, чей
    # exe она ждёт, чтобы подменить. Журнал её не касается: файл открывается
    # только записью, а она пишет в свой.
    if sys.argv[1:2] == [updater.UPDATE_FLAG]:
        return updater.run(sys.argv[2:])

    # Замок берётся первым и держится до самого конца: живёт он, пока жив
    # дескриптор. Две копии над одним каталогом данных делят файл журнала — а
    # тот поворачивается переименованием, и после первой же ротации одна из
    # копий пишет в переименованный файл, который сотрут следующей.
    the_only_copy = hold_the_only_copy(get_lock_path())
    if the_only_copy is None:
        # Ни записи, ни сообщения: второе нажатие на ярлык — не беда, а просьба
        # показать приложение, и человек ждёт окна, а не объяснений. Показать
        # их всё равно негде — в оконной сборке нет ни консоли, ни потока
        # ошибок, — а запись пошла бы в тот самый журнал, который замок и
        # сторожит. Вместо этого просим открытую копию выйти вперёд.
        from client.raise_window import ask_to_raise

        # Ответ не смотрим: уходить всё равно, а сказать «не дозвался» негде.
        # Отказ бывает и штатным — первая копия ещё не дошла до окна.
        ask_to_raise()
        return 3
    with the_only_copy:
        updater.clear_leftovers()
        # Мак-модуль грузится строкой, чтобы не попасть в Windows-сборку.
        if sys.platform == "darwin":
            importlib.import_module("adapters.install_places_macos").widen_path()
        return _started_or_told_why()


if __name__ == "__main__":
    sys.exit(main())
