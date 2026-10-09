"""Приём объявления, вставленного человеком: тот же конвейер, но без канала.

Найденное глазами — на бирже, в почте, по наводке — бот не принесёт никогда,
а вести по воронке его надо тем же экраном. Текст объявления человек приносит
сам, и дальше строка идёт обычной дорогой: отпечаток, отсев уже заведённого,
разбор моделью, балл и приговор.

От соседнего `ingest.py` отличается источником, и только им: там пост канала с
номером, курсором и статьёй по ссылке, здесь — голый текст. Всё, что о
происхождении знал приём поста, здесь не знают вовсе, и выдумывать это нельзя:
проставленный наугад канал сделал бы строку чужой статистикой.
"""

import logging
from datetime import datetime
from typing import Literal

from backend.flows import embeddings, intake, parse, sameness
from backend.models import Vacancy
from backend.repository.vacancies_new import HAND_MADE

logger = logging.getLogger(__name__)

PastedIntakeOutcome = Literal["ok", "duplicate", "embed", "llm", "trash"]
"""Чем кончился приём вставленного текста.

Словами, а не «да/нет»: молчащий поставщик отпечатков, уже заведённое
объявление, не дошедший разбор, снесённый разбором мусор и удача — пять разных
вестей человеку, и различить их после того, как ответ сведён к признаку, уже
нечем.
"""

WHAT = "вставленный текст"
"""Чей текст не посчитался — так это назовут в журнале.

Именем, а не литералом у зова: та же строка уходит и в жалобу молчащего
поставщика, по которой потом ищут в журнале.
"""


async def ingest_pasted_text(
    pipeline, text: str, posted_at: datetime | None
) -> PastedIntakeOutcome:
    """Завести вакансию по вставленному тексту; сказать, чем это кончилось.

    Ответ словом, а не номером строки: зовущий отвечает человеку фразой, и
    беды у этой работы три — поставщик отпечатков молчит, объявление уже
    заведено, разбор не задался. Номер человеку не нужен: строка появляется в
    списке сама.

    Отпечаток считается до записи: без него строка вышла бы из отсева
    перепостов, и то же объявление, пришедшее следом из канала, завелось бы
    второй раз.

    Разбор зовётся с правом убрать непригодное — тем же, с каким его зовёт
    приём поста: вставленный текст ничем не надёжнее опубликованного, и след
    от рекламы засорял бы список.
    """
    try:
        match = await sameness.known_or_new(pipeline, text, WHAT)
    except embeddings.ProviderIsSilent:
        logger.warning("%s: поставщик отпечатков молчит", WHAT)
        return "embed"
    if match is None:
        return "embed"
    if match.kind != "new":
        return await _finish_or_refuse(pipeline, match, text)

    vacancy_id = await _save_pasted_vacancy(pipeline, text, match.embedding, posted_at)
    return await _parsed(pipeline, vacancy_id, text)


async def _finish_or_refuse(
    pipeline, match: sameness.Match, text: str
) -> PastedIntakeOutcome:
    """Что делать со вставленным текстом уже знакомого объявления.

    Знакомая строка бывает двух родов, и приём поста канала разводит их так
    же: настоящий повтор — про него говорят человеку, — и вакансия, брошенная
    недоразобранной. Вторую дорзабирают вставленным текстом: сказав про неё
    «уже заведено», человека послали бы искать в списке строку, которой там
    нет — показывают только разобранные.
    """
    if match.kind == "parsed":
        logger.info("%s: уже заведено вакансией %d", WHAT, match.vacancy_id)
        return "duplicate"
    logger.info("%s: дочитывает брошенную вакансию %d", WHAT, match.vacancy_id)
    return await _parsed(pipeline, match.vacancy_id, text)


async def _parsed(pipeline, vacancy_id: int, text: str) -> PastedIntakeOutcome:
    """Разобрать строку и сказать, вышло ли.

    Слепки конвейера перечитываются перед разбором — так же, как это делают
    обход каналов и прогон заново: наполняет их только перечитывание, а зовут
    его не во всяком режиме бота. Разбери по пустым, и балл выйдет нулевым,
    чёрный список не сработает вовсе, а о пригодности рассудят по анкете, в
    которой ничего нет.

    Удачей не зовут два исхода. Не дошедший разбор — строка осталась
    неразобранной, а показывают только разобранные. И снесённое разбором:
    «дошло» он отвечает и там, где сам убрал строку как рекламу, пост
    соискателя или пустышку. Оба раза «объявление заведено» послало бы
    человека искать то, чего он не найдёт.
    """
    await pipeline.reload_resources()
    if not await parse.parse_and_update_vacancy(pipeline, vacancy_id, text, None):
        return "llm"
    return "ok" if await _still_there(pipeline, vacancy_id) else "trash"


async def _still_there(pipeline, vacancy_id: int) -> bool:
    """Осталась ли строка в базе после разбора.

    Иначе не отличить: разбор отвечает «дошло» и когда записал поля, и когда
    снёс непригодное, а человеку это две разные вести.
    """
    async with pipeline.session_factory() as session:
        return await session.get(Vacancy, vacancy_id) is not None


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
