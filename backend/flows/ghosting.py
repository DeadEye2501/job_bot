"""Гашение вакансий, по которым HR замолчал дольше срока."""

import logging

from backend.domain.transitions import GHOSTING_TIMEOUT_DAYS
from backend.notify import fire
from backend.repository.vacancies_life import mark_ghosted_vacancies

logger = logging.getLogger(__name__)


async def check_ghosting_timeouts(pipeline) -> int:
    """Сканирует Applied/In Progress вакансии и переводит в Ghosting
    те, по которым HR молчит дольше GHOSTING_TIMEOUT_DAYS.

    Дёргается из Bot.run loop'а раз в poll-tick (DM_ONLY и FULL —
    в OFF не запускается, бот считается «на паузе»). Стоимость
    низкая: только Applied/In Progress попадают в шорт-лист, и берётся
    он одним заходом в базу — см. `vacancies_life._silence_candidates`.
    """

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
