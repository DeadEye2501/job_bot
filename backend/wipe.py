"""Снос всего, что приложение записало на диск.

Заводится рядом с `bootstrap.py` — тот владеет заведением схемы, этот
обратным движением. Прежде снос был написан целиком в теле слота окна: он сам
закрывал движок базы, сам собирал имена файлов строками и сам тянул закрытые
имена из хранилища ключей. Имён он при этом знал пять из семи — журнал и замок
переживали «удалить всё».

Мост после этого перестаёт знать, из чего состоит каталог данных: он говорит
«снеси», получает перечень бед и решает, что сказать человеку.
"""

from __future__ import annotations

import logging
import shutil

from backend.single_instance import hold_the_only_copy, release_the_lock
from config import data_dirs, data_files, get_lock_path


logger = logging.getLogger(__name__)


def _close_log_files() -> list[str]:
    """Закрыть файлы журнала, которые держит сам процесс; вернуть беды.

    После этого писать в файл журнала некуда, и это осознанно: следом идёт
    удаление самого файла, а сразу за сносом — выход из процесса. Беда отсюда
    возвращается зовущему: по перечню он решает, отказывать ли человеку вовсе,
    а сказанное на экране «Логи» кольцо в памяти держит и без файла.
    """
    troubles: list[str] = []
    root = logging.getLogger()
    for handler in list(root.handlers):
        if not isinstance(handler, logging.FileHandler):
            continue
        root.removeHandler(handler)
        try:
            handler.close()
        except Exception as e:
            troubles.append(f"журнал: {e}")
            logger.exception("wipe: failed to close %s", handler.baseFilename)
    return troubles


def _remove_the_data() -> list[str]:
    """Удалить перечисленное в каталоге данных; вернуть беды.

    Держатели к этому мигу отпущены зовущим: Windows занятый файл удалить не
    даст, а прощённый молча отказ оставил бы на диске ровно то, ради чего снос
    и зовут, — записи журнала с перепиской.
    """
    troubles: list[str] = []
    for path in data_files():
        if not path.exists():
            continue
        try:
            path.unlink()
        except Exception as e:
            troubles.append(f"{path.name}: {e}")
            logger.exception("wipe: failed to remove %s", path)

    for path in data_dirs():
        if not path.exists():
            continue
        try:
            shutil.rmtree(path)
        except Exception as e:
            troubles.append(f"{path.name}/: {e}")
            logger.exception("wipe: failed to remove %s", path)

    return troubles


async def wipe_all(engine) -> list[str]:
    """Закрыть базу и снести каталог данных; вернуть беды, какие случились.

    Свои держатели отпускаются до удаления: журнал держит обработчик записи,
    движок — файл базы, файл замка — открытый дескриптор единственной копии.

    Замок отпускается последним и только ради своего же файла, а при бедах
    берётся обратно: не удавшийся снос оставляет приложение жить, и без
    сторожа рядом запустилась бы вторая копия над теми же данными.

    Что удалять, перечислено `config.data_files` и `config.data_dirs`.
    """
    errors: list[str] = _close_log_files()
    if engine is not None:
        try:
            await engine.dispose()
        except Exception as e:
            errors.append(f"engine.dispose: {e}")
            logger.exception("wipe: engine.dispose failed")

    release_the_lock()
    errors += _remove_the_data()
    if errors and hold_the_only_copy(get_lock_path()) is None:
        # Занять его в этот миг успевает вторая копия — запущенная ровно между
        # отпусканием и обратным взятием. Сказать это человеку можно только
        # журналом: файлы его закрыты, но экран журнала кормит буфер.
        logger.error("wipe: lock taken by someone else, running unguarded")
    return errors
