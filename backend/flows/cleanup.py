"""Удаление вакансии конвейером — вместе с её вектором в кэше.

Дорога здесь одна: приговор «мусор» при разборе. Удаление по кнопке из окна
идёт мимо, прямо в репозиторий, и кэш векторов за собой не чистит — это
записано отдельным пунктом плана, `forget_vacancy` пока не зовёт никто, кроме
тестов.

Гашение по сроку молчания уехало соседом (`flows/ghosting.py`): вакансия там
не пропадает, а меняет статус.
"""

import logging

from backend.models import Vacancy
from backend.repository.vacancies_life import delete_vacancy as repo_delete_vacancy
from backend.repository.vacancies_life import record_trash_event

from backend.flows import embeddings

logger = logging.getLogger(__name__)

_NO_TRASH_EVENT = object()


async def _delete_and_forget(
    pipeline, vacancy_id: int, *, trash_reason=_NO_TRASH_EVENT
) -> int | None:
    """Удалить вакансию, забыть её вектор и разбудить окно; отдать её канал.

    Дорог к удалению две — забыть вакансию насовсем и удалить её приговором
    «мусор», — и различие у них ровно одно: вторая до удаления оставляет
    отметку о мусоре, иначе «канал прислал N мусора» посчитать нечем, строка
    исчезает совсем. Часовой отличает «отметки не надо» от «отметка без
    причины»: причина бывает и пустой.

    **Третья дорога идёт мимо и это долг, а не задумка:** удаление по кнопке
    в окне зовёт репозиторий напрямую, то есть вектор в кэше оставляет. Долг
    записан в `docs/backend/04-layers.md`, пункт 5.

    Вычёркивание вектора не украшение: оставь кэш вектор удалённой строки,
    и следующее похожее объявление отсеется как повтор того, чего больше
    нет. Разойдись дороги, одна из двух эту память бы и оставляла.

    Удаление идёт через репозиторий, а не своим `session.delete`: у этого
    движка проверка внешних ключей выключена, и дети строки — история
    статусов и лента — остались бы сиротами.
    """
    async with pipeline._session_factory() as session:
        v = await session.get(Vacancy, vacancy_id)
        channel_id = v.source_channel_id if v is not None else None
        if trash_reason is not _NO_TRASH_EVENT:
            await record_trash_event(
                session,
                source_channel_id=channel_id,
                source_msg_id=v.source_msg_id if v is not None else None,
                reason=trash_reason,
            )
        await repo_delete_vacancy(session, vacancy_id)
        await session.commit()
    embeddings.drop_embedding(pipeline, vacancy_id)
    # Vacancy_count у HR/Company изменился — пушим refresh.
    pipeline._fire_contacts_changed()
    pipeline._fire_vacancies_changed()
    return channel_id


async def forget_vacancy(pipeline, vacancy_id: int) -> None:
    """Удалить вакансию по просьбе человека.

    Тёзка в репозитории удаляет только строку. Звать её отсюда напрямую —
    ловушка: вектор остался бы в кэше отсева перепостов, и следующее похожее
    объявление отсеклось бы как повтор того, чего больше нет.
    """
    await _delete_and_forget(pipeline, vacancy_id)
    logger.info("vacancy %d: deleted from DB and embedding cache", vacancy_id)


async def delete_vacancy_as_trash(
    pipeline, vacancy_id: int, reason: str | None
) -> None:
    """Удалить вакансию приговором «мусор», оставив отметку о ней."""
    channel_id = await _delete_and_forget(
        pipeline, vacancy_id, trash_reason=reason
    )
    logger.info(
        "vacancy %d: deleted as trash (event recorded for channel=%s)",
        vacancy_id, channel_id,
    )
