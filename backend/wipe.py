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

from backend.single_instance import release_the_lock
from config import data_dirs, data_files


logger = logging.getLogger(__name__)


def _close_log_files() -> list[str]:
    """Закрыть файлы журнала, которые держит сам процесс; вернуть беды.

    После этого писать в журнал некуда, и это осознанно: следом идёт удаление
    его файла, а сразу за сносом — выход из процесса. Поэтому беда отсюда
    возвращается зовущему, а не пишется: сказать её человеку может только
    ответ окна.
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
    return troubles


async def wipe_all(engine) -> list[str]:
    """Закрыть базу и снести каталог данных; вернуть беды, какие случились.

    Движок закрывается первым: Windows не отдаст файл базы, пока у неё открыт
    хоть один держатель, и снос без этого молча оставил бы базу на месте.

    Свои держатели отпускаются до удаления: журнал держит обработчик записи,
    файл замка — открытый дескриптор единственной копии, и Windows занятый
    файл удалить не даст. Прощать этот отказ молча нельзя — прощённым он
    оставлял бы на диске ровно то, ради чего снос и зовут: записи журнала с
    перепиской.

    Что удалять, перечислено `config.data_files` и `config.data_dirs`.
    """
    release_the_lock()
    errors: list[str] = _close_log_files()
    if engine is not None:
        try:
            await engine.dispose()
        except Exception as e:
            errors.append(f"engine.dispose: {e}")
            logger.exception("wipe: engine.dispose failed")

    for path in data_files():
        if not path.exists():
            continue
        try:
            path.unlink()
        except Exception as e:
            errors.append(f"{path.name}: {e}")
            logger.exception("wipe: failed to remove %s", path)

    for path in data_dirs():
        if not path.exists():
            continue
        try:
            shutil.rmtree(path)
        except Exception as e:
            errors.append(f"{path.name}/: {e}")
            logger.exception("wipe: failed to remove %s", path)

    return errors
