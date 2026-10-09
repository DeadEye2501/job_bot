"""Удаление вакансии конвейером — вместе с её вектором в кэше.

Дорог сюда две: приговор «мусор» при разборе и кнопка удаления в окне. Вторая
приходит через `Bot.ui_forget_vacancy`; мимо, прямо в репозиторий, окно ходит
только пока бот не поднят — тогда и кэша векторов не существует.

Гашение по сроку молчания уехало соседом (`flows/ghosting.py`): вакансия там
не пропадает, а меняет статус.
"""

import logging

from backend.models import Vacancy
from backend.repository.vacancies_life import delete_vacancy as repo_delete_vacancy
from backend.repository.vacancies_life import record_trash_event


logger = logging.getLogger(__name__)

_NO_TRASH_EVENT = object()


async def _delete_and_forget(
    pipeline, vacancy_id: int, *, trash_reason=_NO_TRASH_EVENT
) -> tuple[bool, int | None]:
    """Удалить вакансию, забыть её вектор и разбудить окно.

    В ответе два слова: было ли что удалять и с какого канала строка пришла.
    Первое спрашивают у репозитория, а не отдельным чтением до удаления: между
    ними строку успевает снести идущий рядом цикл, и ответ «удалили» приходил
    бы над чужой работой.

    Дорог к удалению две — забыть вакансию насовсем и удалить её приговором
    «мусор», — и различие ровно одно: вторая до удаления оставляет отметку о
    мусоре, иначе «источник прислал N мусора» посчитать нечем. Часовой отличает
    «отметки не надо» от «отметка без причины»: причина бывает и пустой.

    Вычёркивание вектора не украшение: оставь кэш вектор удалённой строки, и
    следующее похожее объявление отсеется как повтор того, чего больше нет.
    Разойдись дороги, одна из двух эту память бы и оставляла. Ни его, ни
    побудку окна не делают, когда удалять было нечего.

    Удаление идёт через репозиторий, а не своим `session.delete`: детей строки
    убирает он, а без них включённая проверка внешних ключей удаление уронила бы.
    """
    async with pipeline.session_factory() as session:
        v = await session.get(Vacancy, vacancy_id)
        channel_id = v.source_channel_id if v is not None else None
        if trash_reason is not _NO_TRASH_EVENT:
            await record_trash_event(session, v, trash_reason)
        deleted = await repo_delete_vacancy(session, vacancy_id)
        await session.commit()
    if deleted:
        pipeline.embeddings.drop(vacancy_id)
        # Vacancy_count у HR/Company изменился — пушим refresh.
        pipeline.fire_contacts_changed()
        pipeline.fire_vacancies_changed()
    return deleted, channel_id


async def forget_vacancy(pipeline, vacancy_id: int) -> bool:
    """Удалить вакансию по просьбе человека; сказать, было ли что удалять.

    Тёзка в репозитории удаляет только строку. Звать её отсюда напрямую —
    ловушка: вектор остался бы в кэше отсева перепостов, и следующее похожее
    объявление отсеклось бы как повтор того, чего больше нет.

    Отказ нужен окну: строку мог убрать другой экран или сам конвейер, пока
    карточка была открыта, и «удалено» над несуществующей строкой человек
    прочёл бы как успех.
    """
    deleted, _ = await _delete_and_forget(pipeline, vacancy_id)
    if deleted:
        logger.info("vacancy %d: deleted from DB and embedding cache", vacancy_id)
    return deleted


async def delete_vacancy_as_trash(
    pipeline, vacancy_id: int, reason: str | None
) -> None:
    """Удалить вакансию приговором «мусор», оставив отметку о ней."""
    _, channel_id = await _delete_and_forget(
        pipeline, vacancy_id, trash_reason=reason
    )
    logger.info(
        "vacancy %d: deleted as trash (event recorded for channel=%s)",
        vacancy_id, channel_id,
    )
