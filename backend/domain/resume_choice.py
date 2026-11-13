"""Чьё резюме идёт к отклику — основное или английское.

Язык решает `letter_language` — та же развилка, что выбирает готовое письмо и
язык отклика. Язык важнее формы: английское резюме одной ссылкой к отклику
по-английски лучше основного файлом. Резюме на языке отклика нет — идёт
другое: отклик с резюме не на том языке лучше, чем без резюме.
"""

from typing import Literal

from backend.domain.language_choice import INTERNATIONAL_LANGUAGE, letter_language

ResumeSlot = Literal["main", "english"]


def reply_slot(language: str, main: bool, english: bool) -> ResumeSlot | None:
    """Резюме к отклику на `language`; `main` и `english` — есть ли это резюме
    хоть файлом, хоть ссылкой. Нет обоих — пусто."""
    if letter_language(language) == INTERNATIONAL_LANGUAGE:
        order: tuple[tuple[ResumeSlot, bool], ...] = (("english", english), ("main", main))
    else:
        order = (("main", main), ("english", english))
    return next((slot for slot, given in order if given), None)
