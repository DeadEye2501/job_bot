"""Подмена бандла скачанным обновлением на маке — двойник `updater`.

Ход тот же, что у Windows: файл релиза ложится рядом с приложением, подменщик
ждёт его выхода, ставит новое на место и запускает. Отличий два.

Подменяется вся папка `JobBot.app`, а не один файл: в ней и программа, и всё,
что она с собой несёт, а правка файла внутри ломала бы подпись бандла.

Копия приложения в подменщики не нужна: мак не держит файлы запущенной
программы, поэтому подмену делает `sh` своим процессом. Ждёт он само
приложение — onedir-сборка живёт в одном процессе, без загрузчика-родителя.
"""

import logging
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from backend.update_download import remove_leftover

logger = logging.getLogger(__name__)

# Позиционные доводы: номер приложения, бандл, распакованный бандл, папка
# распаковки, zip. Не встал новый — отведённый старый возвращается; запуск —
# при любом исходе, как у Windows-подменщика: человек ждёт приложения.
_SWAP = """
while kill -0 "$1" 2>/dev/null; do sleep 0.5; done
rm -rf "$2.old"
if mv "$2" "$2.old"; then
  if mv "$3" "$2"; then rm -rf "$2.old"; else mv "$2.old" "$2"; fi
fi
rm -rf "$4" "$5"
open "$2"
"""


_swapper: subprocess.Popen | None = None
"""Запущенный подменщик. Держится до выхода приложения: брошенный `Popen`
предупреждает, что процесс ещё жив, а этот так и задуман — он ждёт нашего выхода."""


def bundle() -> Path:
    """Запущенный `JobBot.app`: программа лежит в его `Contents/MacOS`."""
    return Path(sys.executable).parents[2]


def download_path() -> Path:
    """Куда ложится скачанный zip: рядом с бандлом, а не во временной папке —
    подмена — переименование, а оно не ходит между дисками."""
    return bundle().with_name("JobBot-update.zip")


def _unpacked() -> Path:
    return bundle().with_name("JobBot-update")


def launch_updater(new: Path) -> None:
    """Распаковать скачанное рядом с бандлом и запустить подменщика.

    Сбой распаковки уходит наверх как `OSError`: файл скачан и сверен, не
    вышла только передача, и зовущий говорит человеку именно это.
    """
    global _swapper
    # Распаковка поверх прежней оставила бы в бандле файлы старой версии.
    shutil.rmtree(_unpacked(), onexc=_report)
    try:
        subprocess.run(["ditto", "-x", "-k", str(new), str(_unpacked())], check=True)
    except subprocess.CalledProcessError as error:
        raise OSError(f"обновление не распаковалось: {new}") from error
    log = Path(tempfile.gettempdir()) / "JobBot-update.log"
    with log.open("a", encoding="utf-8") as out:
        _swapper = subprocess.Popen(
            ["/bin/sh", "-c", _SWAP, "jobbot-update", str(os.getpid()), str(bundle()),
             str(_unpacked() / "JobBot.app"), str(_unpacked()), str(new)],
            stdout=out, stderr=out, start_new_session=True,
        )


def clear_leftovers() -> None:
    """При обычном запуске убрать оставшееся от обновления, в том числе от
    сорванной подмены."""
    remove_leftover(download_path())
    for folder in (_unpacked(), bundle().with_name(bundle().name + ".old")):
        shutil.rmtree(folder, onexc=_report)


def _report(_function, path, error) -> None:
    if os.path.exists(path):
        logger.warning("не удалось убрать остаток обновления %s", path, exc_info=error)
