"""Заявка окна «Добавить вакансию»: довести её до строки дорогой её вкладки.

Отличие от `pasted`: тот доводит до строки вставленный текст, а здесь заявку
любой вкладки — текст отдают ему, поля заводят сами. Поля с выключенным
переключателем заводит мост без бота, но той же `file_fields`; бот получает
их, только когда заведённое надо отдать откликателю, а отклик идёт через место
прогона.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from backend.agent.kit import AgentKit
from backend.flows import pasted
from backend.flows.hand_outcome import HandResult, tell
from backend.flows.handover import hand_over
from backend.flows.parse import Judged
from backend.repository.vacancies_new import create_vacancy

HandTab = Literal["fields", "text"]
"""Вкладка окна, с которой пришла заявка."""


@dataclass(frozen=True)
class HandRequest:
    """Заявка окна: вкладка, введённое (поля формы словарём или текст),
    названная дата публикации и отдавать ли откликателю."""

    tab: HandTab
    value: str | dict
    posted_at: datetime | None
    hands_over: bool


async def ingest_by_hand(kit: AgentKit, request: HandRequest) -> None:
    """Довести заявку окна до строки; итог — вестью окну (`tell`)."""
    if request.tab == "text":
        await pasted.ingest_pasted_text(
            kit.pipeline, request.value, request.posted_at, request.hands_over
        )
        return
    await _filed(kit.pipeline, request.value, request.hands_over)


async def file_fields(session_factory, fields: dict) -> HandResult:
    """Завести набранное в окне: заведено — с номером, повтор по «Ссылке на
    объявление» — с номером существующей. Набранное — уже разбор, модели оно
    не отдаётся."""
    async with session_factory() as session:
        async with session.begin():
            vacancy_id, created = await create_vacancy(session, fields)
    return HandResult("ok" if created else "duplicate", vacancy_id)


async def _filed(pipeline, fields: dict, hands_over: bool) -> None:
    """Завести набранное и отдать откликателю; повтор не отдаётся — окно
    перейдёт на существующую."""
    result = await file_fields(pipeline.session_factory, fields)
    if result.outcome == "ok":
        pipeline.fire_vacancies_changed()
    tell(pipeline, result.outcome, result.vacancy_id)
    if result.outcome == "ok":
        await hand_over(pipeline, [(result.vacancy_id, Judged(True))], applies=hands_over)
