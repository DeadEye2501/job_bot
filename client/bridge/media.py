"""Картинка в виде адреса, который разметка вставит в `src`."""

from __future__ import annotations

import base64
from pathlib import Path


def _media_url(stored_path: str | None) -> str | None:
    """Convert the ``message.media_path`` column into a ``file://`` URL the
    SPA can render. New rows hold a posix path relative to ``MEDIA_DIR``
    (e.g. ``"1/42.jpg"``); legacy rows from earlier sessions may hold an
    absolute path or a project-relative one — `is_absolute` + the bot's
    `MEDIA_DIR` cover both.
    """
    if not stored_path:
        return None
    from backend.bot.media import MEDIA_DIR
    p = Path(stored_path)
    if not p.is_absolute():
        p = (MEDIA_DIR / p).resolve()
    return p.as_uri()


def _avatar_data_url(blob: bytes | None) -> str | None:
    """Encode raw avatar bytes (Telegram delivers JPEGs) as a data URL.

    The frontend embeds these directly in <img src=...> so we ship them
    inline with the list/detail payload — Telegram small-file avatars are
    a few KB each, so the JSON bloat is negligible vs a separate per-row
    fetch round-trip.
    """
    if not blob:
        return None
    return "data:image/jpeg;base64," + base64.b64encode(blob).decode("ascii")
