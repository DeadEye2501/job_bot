"""Удаление вакансий и гашение по сроку молчания."""

import logging

from backend.models import Vacancy
from backend.repository.vacancies_life import delete_vacancy as repo_delete_vacancy
from backend.repository.vacancies_life import record_trash_event

from backend.flows import embeddings
from backend.notify import fire

logger = logging.getLogger(__name__)

_NO_TRASH_EVENT = object()


async def check_ghosting_timeouts(pipeline) -> int:
    """Сканирует Applied/In Progress вакансии и переводит в Ghosting
    те, по которым HR молчит дольше GHOSTING_TIMEOUT_DAYS.

    Дёргается из Bot.run loop'а раз в poll-tick (DM_ONLY и FULL —
    в OFF не запускается, бот считается «на паузе»). Стоимость
    низкая: только Applied/In Progress попадают в шорт-лист, для
    каждой 2 SQL-запроса (max(message), max(history)). Если
    кандидатов нет — ранний return.
    """
    from backend.domain.transitions import GHOSTING_TIMEOUT_DAYS
    from backend.repository.vacancies_life import mark_ghosted_vacancies

    try:
        async with pipeline._session_factory() as session:
            async with session.begin():
                affected = await mark_ghosted_vacancies(
                    session, timeout_days=GHOSTING_TIMEOUT_DAYS,
                )
    except Exception:
        logger.exception("check_ghosting_timeouts failed")
        return 0
    if affected:
        logger.info(
            "ghosting timer: marked %d vacancies (ids=%s)",
            len(affected), affected,
        )
        fire(pipeline.on_vacancies_changed, "on_vacancies_changed")
    return len(affected)


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
