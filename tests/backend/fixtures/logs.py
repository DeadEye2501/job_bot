"""Возврат корневого логгера в состояние, в котором его застали."""

import logging

import pytest


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
