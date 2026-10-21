"""Окно о беде на маке — двойник `trouble_box.show_trouble`.

Окно рисует `osascript`: оно не требует ни поднятого приложения, ни AppKit в
этом процессе. Текст беды идёт аргументом скрипта, а не вписывается в него:
кавычки и обратные косые в тексте сбоя скрипт тогда не ломают.
"""

import logging
import subprocess

logger = logging.getLogger(__name__)

_ALERT = (
    "-e", "on run argv",
    "-e", 'display alert "Job Bot" message (item 1 of argv) as critical',
    "-e", "end run",
)


def show_trouble(text: str) -> None:
    """Показать беду окном системы.

    Своя беда здесь гасится записью: это последняя дорога к человеку, и упасть
    на ней значит не сказать ему вовсе ничего — а зовущий в этот миг уже
    выходит и перехватить нас не может.
    """
    try:
        subprocess.run(["osascript", *_ALERT, text], check=True)
    except Exception:
        logger.exception("не вышло показать беду окном системы: %s", text)
