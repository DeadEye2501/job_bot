"""Оповещение окна: позвать подписчика, не дав его поломке уронить работу."""

import logging

logger = logging.getLogger(__name__)


def fire(hook, name: str, *args) -> None:
    """Позвать подписчика окна, если он есть.

    Оповещение только красит окно; отменять из-за его поломки работу,
    ради которой всё затевалось, значило бы менять важное на украшение.
    Поэтому поломка идёт в журнал с трассировкой и наружу не выходит.
    """
    if hook is None:
        return
    try:
        hook(*args)
    except Exception:
        logger.exception("%s hook failed", name)
