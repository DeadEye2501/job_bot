"""Запись события вакансии своей транзакцией."""

import logging

from backend.repository.vacancies_life import add_vacancy_event

logger = logging.getLogger(__name__)


async def record_vacancy_event(
    session_factory, vacancy_id: int, kind: str, payload: dict
) -> None:
    """Записать событие в ленту вакансии, не роняя дело, ради которого оно.

    Событие — след для человека, а не часть работы: он смотрит на вакансию
    через месяцы и хочет понять, почему всё пошло так. Поэтому поломка записи
    уходит в журнал с трассировкой и дальше не идёт — иначе упавшая лента
    отменяла бы отправку, которая уже случилась.

    Дом здесь, а не в репозитории: тот принимает сессию, а транзакцию вокруг
    события открывают сами — двое зовущих пишут его в те мгновения, когда
    чужой сессии рядом нет.
    """
    try:
        async with session_factory() as session:
            await add_vacancy_event(session, vacancy_id, kind, payload)
            await session.commit()
    except Exception:
        logger.exception(
            "vacancy event %r persist failed",
            kind,
            extra={"vacancy_id": vacancy_id},
        )
