"""Общая обстановка проверок журнала: корневой логгер, файл и готовая запись.

Смотрят на журнал трое — кольцо записей, вымарывание секретов и файл журнала, —
и обстановка у них общая: корневой логгер это состояние всего процесса, файл
журнала один, а готовую запись подают и фильтру, и обработчику.
"""

import logging

import pytest

from config import get_log_path


@pytest.fixture
def clean_root_logger():
    """Возвращает корневой logger в исходное состояние после теста.

    Помимо списка обработчиков, фильтров и собственного уровня снимает и
    восстанавливает уровень каждого уже навешенного обработчика: установка
    буфера журнала правит их на месте, и без возврата чужой обработчик —
    например, тот, которым pytest ловит записи, — остался бы испорченным
    до конца прогона.
    """
    root = logging.getLogger()
    handlers = list(root.handlers)
    filters = list(root.filters)
    level = root.level
    handler_levels = {h: h.level for h in handlers}
    yield root
    root.handlers = handlers
    root.filters = filters
    root.setLevel(level)
    for handler, original_level in handler_levels.items():
        handler.setLevel(original_level)


@pytest.fixture
def clean_log_file():
    """Пустой файл журнала на входе в тест и убранный на выходе.

    В него обработчик буфера сообщает о своих бедах, минуя логирование.
    Остаток от прошлого теста подменял бы «записалось сейчас» на «лежало
    и раньше».
    """
    path = get_log_path()
    path.unlink(missing_ok=True)
    yield path
    path.unlink(missing_ok=True)


def record(msg: str, *, name: str = "проверка", level: int = logging.INFO):
    """Готовая запись журнала для подачи в фильтр или обработчик."""
    return logging.LogRecord(
        name=name, level=level, pathname=__file__, lineno=1,
        msg=msg, args=(), exc_info=None,
    )
