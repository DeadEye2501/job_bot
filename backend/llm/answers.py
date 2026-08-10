"""Разбор того, что ответила модель."""


import json
import re

_JSON_OBJECT_RE = re.compile(r"\{[^{}]*\}", re.DOTALL)


QUOTE_TRANSLATION = str.maketrans({
    "“": '"',
    "”": '"',
    "‘": "'",
    "’": "'",
})


def extract_last_json(answer: str) -> str | None:
    """Последний объект JSON из ответа модели.

    Сначала ищется разбираемый объект в тексте как есть, и только потом — в
    тексте с выпрямленными кавычками. Порядок важен: выпрямление заведено
    ради моделей, ставящих ёлочки вместо кавычек JSON, но те же ёлочки
    встречаются и внутри значений по-русски — выпрямив их там, мы ломаем
    годный ответ.

    Если не разбирается ничто, отдаётся последний найденный огрызок: зовущий
    сообщит о неразбираемом ответе так же, как и прежде.
    """
    straightened = answer.translate(QUOTE_TRANSLATION)
    for text in (answer, straightened):
        for candidate in reversed(_JSON_OBJECT_RE.findall(text)):
            try:
                json.loads(candidate)
            except ValueError:
                continue
            return candidate
    matches = _JSON_OBJECT_RE.findall(straightened)
    return matches[-1] if matches else None


def normalize_enum(value, allowed: tuple[str, ...]) -> str | None:
    if not isinstance(value, str):
        return None
    v = value.strip().lower()
    if v in allowed:
        return v
    return None
