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
"""

import logging
from datetime import datetime

from backend.flows import embeddings, handover, intake, linked_article
from backend.flows.hand_outcome import tell
from backend.flows.handover import Intake
from backend.models import Vacancy
from backend.repository.vacancies_new import HAND_MADE

logger = logging.getLogger(__name__)

WHAT = "вставленный текст"
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
    брошенной не сливается — её доберёт подбор недоразобранного.

    Отдавать ли откликателю (`hands_over`), решал человек переключателем окна.

    Нижняя полоса показывает разбор с нулями — «шкала неизвестна»: сколько
    шагов займёт разбор одного объявления, заранее не знает никто.
    """
    pipeline.emit_progress("pasted", "Разбор объявления", 0, 0)
    text, whole = await linked_article.with_linked_articles(text)
    if not whole:
        logger.info("%s: статья по ссылке не скачалась, не заведено", WHAT)
        tell(pipeline, "article")
        return
    embedding = await embeddings.embed_or_none(pipeline, text, WHAT)
    if embedding is None:
        tell(pipeline, "embed")
        return
    vacancy_id = await _save_pasted_vacancy(pipeline, text, embedding, posted_at)
    # Слепки перечитываются перед разбором: наполняет их только перечитывание,
    # а зовут его не во всяком режиме бота, и балл по пустым вышел бы нулевым.
    await pipeline.reload_resources()
    await handover.judge_and_hand_over(
        pipeline, vacancy_id, text, Intake(hands_over=hands_over, tells_window=True)
    )


async def _save_pasted_vacancy(
    pipeline, text: str, embedding: list[float], posted_at: datetime | None
) -> int:
    """Записать строку по вставленному тексту и назвать её номер.

    Колонок источника у неё нет: канала за вставленным текстом не стоит, и
    проставленный наугад сделал бы строку чужой статистикой. Лента получает
    тот же род события, что и заведение через форму: для человека это одно и
    то же — вакансия, которую он завёл сам, а не бот.
    """
    return await intake.save_new_vacancy(
        pipeline,
        Vacancy(raw_text=text, embedding=embedding, posted_at=posted_at),
        HAND_MADE,
    )
