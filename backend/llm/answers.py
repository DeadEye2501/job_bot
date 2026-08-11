"""Разбор того, что ответила модель."""


import json
import logging
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


def json_object(answer: str, log: logging.Logger, purpose: str) -> dict | None:
    """Объект JSON из ответа модели, а неразбираемое — как отсутствие.

    Ответ модели превращают в словарь пятеро, и различаются они не разбором,
    а тем, что делают с неудачей: у одного откат `None`, у другого пара с
    причиной, у третьего «не поймали — пропускаем». Поэтому здесь только
    разбор; откат остаётся делом зовущего.

    Пишет логгером зовущего: в окне журнала у строки виден источник, и пять
    обращений иначе схлопнулись бы под одним именем. Уровень отладочный,
    потому что о самой неудаче зовущие говорят громко и сами — каждый своими
    словами и своим уровнем. Здесь остаётся то, чего у них нет: что именно
    не разобралось.
    """
    raw = extract_last_json(answer)
    if raw is None:
        log.debug("%s: в ответе модели нет объекта JSON (%r)", purpose, answer[:200])
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        log.debug("%s: объект не разбирается (%r)", purpose, raw[:200], exc_info=True)
        return None


def str_or_none(value) -> str | None:
    """Строка из ответа модели, а пустая и не-строка — как отсутствие.

    Модель на «нет значения» отвечает то пропуском поля, то пустой
    строкой, то пробелами, то числом; зовущим все четыре случая значат
    одно.
    """
    if not isinstance(value, str):
        return None
    return value.strip() or None


def normalize_enum(value, allowed: tuple[str, ...]) -> str | None:
    """Значение из ответа модели, сведённое к справочнику, а чужое — как
    отсутствие.

    Модель отвечает свободным текстом: то с заглавной, то с пробелами по
    краям, то словом, которого в справочнике нет вовсе. Приговор, уровень и
    формат работы после этого либо ложатся в колонку из закрытого набора,
    либо не ложатся никак — третьего колонки не принимают.
    """
    if not isinstance(value, str):
        return None
    v = value.strip().lower()
    if v in allowed:
        return v
    return None
