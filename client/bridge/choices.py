"""Просеивание значений, пришедших из окна, по известному набору."""

from __future__ import annotations

from backend.domain.taxonomy import LANGUAGE_LEVELS


def _filter_set(values, allowed: tuple[str, ...]) -> list[str]:
    """Keep only known values, in `allowed` order, no duplicates."""
    if not isinstance(values, list):
        return []
    seen = {str(v) for v in values if isinstance(v, str)}
    return [v for v in allowed if v in seen]


def _filter_languages(items) -> list[tuple[str, str]]:
    """Validate language entries from the UI.

    Drops rows with empty language name. Falls back to ``B2`` if the level
    is unknown (UI-typed garbage shouldn't break save). De-dups by language
    name (case-insensitive) — last write wins, matching the UI behaviour
    where editing replaces the row.
    """
    if not isinstance(items, list):
        return []
    # Место строки, а не только её имя: повтор языка правит уже лежащую
    # строку, и без места её пришлось бы искать вторым обходом.
    seen: dict[str, int] = {}  # lower(name) -> место в out
    out: list[tuple[str, str]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        name = str(item.get("language") or "").strip()
        if not name:
            continue
        level = str(item.get("level") or "").strip()
        if level not in LANGUAGE_LEVELS:
            level = "B2"
        key = name.lower()
        if key in seen:
            at = seen[key]
            out[at] = (out[at][0], level)
            continue
        seen[key] = len(out)
        out.append((name, level))
    return out
