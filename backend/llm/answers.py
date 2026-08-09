"""Разбор того, что ответила модель."""


import re

_JSON_OBJECT_RE = re.compile(r"\{[^{}]*\}", re.DOTALL)


QUOTE_TRANSLATION = str.maketrans({
    "“": '"',
    "”": '"',
    "‘": "'",
    "’": "'",
})


def extract_last_json(answer: str) -> str | None:
    cleaned = answer.translate(QUOTE_TRANSLATION)
    matches = _JSON_OBJECT_RE.findall(cleaned)
    return matches[-1] if matches else None


def normalize_enum(value, allowed: tuple[str, ...]) -> str | None:
    if not isinstance(value, str):
        return None
    v = value.strip().lower()
    if v in allowed:
        return v
    return None
