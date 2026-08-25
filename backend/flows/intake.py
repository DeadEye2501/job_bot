"""Запись новой строки вакансии: строка, событие ленты и вектор в кэше.

Три этих дела неразделимы, и разделённые они расходятся молча: строка без
события выглядит взявшейся ниоткуда, а строка без вектора выпадает из отсева
перепостов — то же объявление, пришедшее следом, заведётся второй раз, и
заметит это только человек, у которого список забился одним и тем же.

Заводят вакансию из текста двое — обход канала и человек со вставленным
объявлением (`ingest.py`, `pasted.py`), — и оба зовут отсюда. Чем строки
отличаются, знает зовущий: он и собирает её сам, а сюда приносит готовую.
"""

import logging

from backend.models import Vacancy
from backend.repository.vacancies_life import add_vacancy_event

logger = logging.getLogger(__name__)


async def save_new_vacancy(
    pipeline, vacancy: Vacancy, kind: str, payload: dict | None = None
) -> int:
    """Записать собранную строку с её событием и назвать номер.

    Вектор кладётся в кэш после записи, а не до: сорвись она, в памяти остался
    бы отпечаток строки, которой нет, и следующее похожее объявление молча
    сочли бы повтором.

    Строка без отпечатка кэша не касается вовсе. Отпечатка не бывает у той,
    что заведена мимо бота, — модель отпечатков поднимают не всегда, — а
    пустота, положенная в кэш, отняла бы у него ширину: следующий настоящий
    вектор в него уже не встал бы, и строка к тому мигу была бы записана.
    """
    async with pipeline.session_factory() as session:
        session.add(vacancy)
        await session.flush()
        await add_vacancy_event(session, vacancy.id, kind, payload)
        await session.commit()
    if vacancy.embedding is not None:
        pipeline.embeddings.append(vacancy.id, vacancy.embedding)
    logger.info("вакансия %d заведена, событие %s", vacancy.id, kind)
    return vacancy.id
