"""Приём объявления, вставленного человеком: тот же конвейер, но без канала.

Найденное глазами — на бирже, в почте, по наводке — бот не принесёт никогда,
а вести по воронке его надо тем же экраном. Текст объявления человек приносит
сам, и дальше строка идёт дорогой заведённой человеком: отпечаток, разбор
моделью и балл, но без приговора и без слияния с похожими.

От соседнего `ingest.py` отличается источником и тем, кто завёл: там пост
канала с номером и курсором, найденный обходом, здесь — голый текст от
человека. Статьи по ссылкам дописывает обоим одна склейка. Всё, что о
происхождении знал приём поста, здесь не знают вовсе, и выдумывать это нельзя:
проставленный наугад канал сделал бы строку чужой статистикой.

Хвост этой дороги (`file_by_hand`) общий и у поста, заведённого по ссылке:
полный текст от человека дальше идёт одинаково, откуда бы он ни пришёл.
"""

import logging
from collections.abc import Awaitable, Callable
from datetime import datetime

from backend.flows import embeddings, hand_repeat, handover, intake, linked_article
from backend.flows.hand_outcome import show_parsing, tell
from backend.flows.handover import Intake
from backend.models import Vacancy

logger = logging.getLogger(__name__)

WHAT = "вставленный текст"
"""Чей текст не скачал статьи — так это назовут в журнале."""

BY_HAND = "заведённое человеком объявление"
"""Чей текст не посчитался — так это назовут в журнале.

Именем, а не литералом у зова: та же строка уходит и в жалобу молчащего
поставщика, по которой потом ищут в журнале.
"""


async def ingest_pasted_text(
    pipeline, text: str, posted_at: datetime | None, hands_over: bool
) -> None:
    """Завести вакансию по вставленному тексту; итог окну — вестью (`tell`).

    Статьи дочитываются первыми, как у поста канала: отпечаток, строка и
    разбор идут по полному тексту. Не скачалась — строка не заводится вовсе:
    приём поста ждёт статью у заведённой строки, а здесь человек может просто
    нажать ещё раз.

    Отпечаток считается до записи: без него строка вышла бы из отсева
    перепостов, и то же объявление, пришедшее следом из канала, завелось бы
    второй раз. Похожую заведённую он не ищет: сходство однозначного повтора
    не даёт, и вставленное человеком заводится своей строкой, а с чужой
    брошенной не сливается. Повтор — только тот же текст (`file_by_hand`).

    Отдавать ли откликателю (`hands_over`), решал человек переключателем окна.
    """
    show_parsing(pipeline)
    text, whole = await linked_article.with_linked_articles(text)
    if not whole:
        logger.info("%s: статья по ссылке не скачалась, не заведено", WHAT)
        tell(pipeline, "article")
        return
    by_hand = handover.hand_made_intake(hands_over)

    async def save(embedding: list[float]) -> int:
        # Колонок источника у строки нет: канала за вставленным текстом не
        # стоит, и проставленный наугад сделал бы строку чужой статистикой.
        kind, payload = by_hand.event("pasted", {})
        row = Vacancy(raw_text=text, embedding=embedding, posted_at=posted_at)
        return await intake.save_new_vacancy(pipeline, row, kind, payload)

    await file_by_hand(pipeline, text, by_hand, save)


async def file_by_hand(
    pipeline, text: str, by_hand: Intake, save: Callable[[list[float]], Awaitable[int | None]]
) -> None:
    """Общий хвост ручного заведения полного текста — вставленного и поста по
    ссылке: отпечаток, строка, разбор; итог окну — вестью.

    `save` пишет строку по отпечатку и называет её номер; пусто — не
    записана, и сказал об этом уже он сам.

    Отпечаток в той же точке, что у заведённой, — тот же текст, однозначный
    повтор (`hand_repeat.known_and_told`); просто похожий — своя строка.

    Слепки перечитываются перед разбором: наполняет их только перечитывание,
    а зовут его не во всяком режиме бота, и балл по пустым вышел бы нулевым.
    """
    embedding = await embeddings.embed_or_none(pipeline, text, BY_HAND)
    if embedding is None:
        tell(pipeline, "embed")
        return
    same = await embeddings.similar_vacancy_id(pipeline, embedding, embeddings.SAME_TEXT_COSINE)
    if same is not None and await hand_repeat.known_and_told(pipeline, [same]):
        return
    vacancy_id = await save(embedding)
    if vacancy_id is None:
        return
    await pipeline.reload_resources()
    await handover.judge_and_hand_over(pipeline, vacancy_id, text, by_hand)
