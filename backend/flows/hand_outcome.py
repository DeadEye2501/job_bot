"""Итог ручного заведения для окна: чем кончилось и о какой вакансии.

Отдельно от потока ручного заведения (`hand_made`), потому что итог говорят
несколько мест ниже него — приём вставленного текста, передача после разбора,
— а сами они поток не ввозят: ввези они его, ввозы пошли бы по кругу.
"""

from dataclasses import dataclass
from typing import Literal

from backend.telegram_lookup import TelegramTrouble

HandOutcome = Literal[
    "ok", "duplicate", "embed", "llm", "article",
    TelegramTrouble, "no_post", "empty_post", "channel_link",
]
"""Чем кончилось ручное заведение.

Словами, а не «да/нет»: молчащий поставщик отпечатков, однозначный повтор, не
дошедший разбор, не скачавшаяся статья, беда Telegram, пропавший или пустой
пост, ссылка на канал вместо поста и удача — разные вести человеку, и различить
их после того, как ответ сведён к признаку, уже нечем.
"""


@dataclass(frozen=True)
class HandResult:
    """Итог для окна: слово исхода и номер вакансии — заведённой или той, что
    уже была; пусто — строки нет."""

    outcome: HandOutcome
    vacancy_id: int | None = None


def tell(pipeline, outcome: HandOutcome, vacancy_id: int | None = None) -> None:
    """Сказать окну итог ручного заведения — сразу, не дожидаясь отклика.

    Окно ждёт, пока вакансия встанет в New, а не конца отклика: при
    подтверждении тот длится до часа, и всё это время черновик и кнопка
    «Создать» стояли бы запертыми.
    """
    pipeline.emit_hand_made(HandResult(outcome, vacancy_id))
