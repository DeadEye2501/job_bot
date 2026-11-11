"""Выбор готового сопроводительного письма человека под отклик.

Одно правило на все способы отклика: язык решает язык отклика, длину — предел,
в который письмо должно влезть. Подходящего нет — письмо пишет модель.
"""

from backend.domain.language_choice import in_app_language


def ready_letter(letters, language: str, limit: int | None, *, short: bool = False) -> str | None:
    """Готовое письмо под отклик; пусто — подходящего нет.

    `letters` — что угодно с `app`, `app_short`, `en`, `en_short`, или пусто,
    если писем не писали. Полное берётся, когда влезает в `limit`, иначе
    короткое; `short` — сразу короткое. Пустое письмо другим языком не
    подменяется: вакансия на языке приложения с английским письмом выглядела бы
    ошибкой.
    """
    if letters is None:
        return None
    if in_app_language(language):
        pair = (letters.app, letters.app_short)
    else:
        pair = (letters.en, letters.en_short)
    for text in pair[1:] if short else pair:
        if text and (limit is None or len(text) <= limit):
            return text
    return None
