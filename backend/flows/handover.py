"""Разобранная строка дальше по конвейеру: как её вести (`Intake`), разбор с
передачей откликателю, дочитывание брошенной и догон новых HR после отклика."""

from dataclasses import dataclass, replace

from sqlalchemy import select

from backend.applying.world import AWAITS_APPLICATION
from backend.flows import parse
from backend.flows.dm_backfill import spawn_hr_backfill
from backend.flows.hand_outcome import tell
from backend.flows.linked_article import article_urls
from backend.flows.parse import Judged
from backend.models import Vacancy
from backend.repository.hr_card import LAST_VACANCY_ORDER
from backend.repository.vacancies_common import PARSED_ONLY
from backend.repository.vacancies_new import HAND_MADE, made_by_hand


@dataclass(frozen=True)
class Intake:
    """Как вести разобранную строку: из какого она канала, кто её завёл, можно
    ли её снести как мусор и отдавать ли откликателю.

    Решает это зовущий, а не разбор и не передача: каждый знает, ручается ли он
    за текст и просили ли отклика. По умолчанию — без канала, сносить можно,
    отдавать; заведённую человеком разбор не сносит и так. `tells_window` —
    окно ждёт итога этого разбора: он уходит вестью между разбором и передачей.
    `by_hand` — строку заводит человек, хоть и дорогой автоматики (пост по
    ссылке): событие заведения у неё ручное.
    """

    channel: str | None = None
    allow_delete: bool = True
    hands_over: bool = True
    tells_window: bool = False
    by_hand: bool = False

    def event(self, kind: str, payload: dict) -> tuple[str, dict]:
        """Род и нагрузка события заведения строки.

        У заведённой человеком род один — «заведено вручную»: по нему разбор
        узнаёт, что приговора не выносить. Откуда она пришла, остаётся в
        нагрузке (`via`), и лента карточки называет источник.
        """
        if not self.by_hand:
            return kind, payload
        return HAND_MADE, {"via": kind, **payload}


def hand_made_intake(hands_over: bool, channel: str | None = None) -> Intake:
    """Как вести заведённое человеком из окна: окно ждёт итога, откликателю —
    по переключателю."""
    return Intake(channel=channel, hands_over=hands_over, tells_window=True, by_hand=True)


async def tell_known(pipeline, vacancy_id: int) -> None:
    """Окну — что вакансия уже заведена, с её номером.

    Неразобранную дочитывают её собственным текстом — без сноса и без
    откликателя: окно переходит на неё, а отдавать ли её, решали, когда её
    заводили. Дочитать не вышло — окну не повтор, а молчание модели: строки
    без разбора в списке не видно, и переходить было бы некуда. Ждущую статью
    одной шапкой не судят — её дочитает подбор недоразобранного, а окну
    говорится, что статья ещё не пришла.
    """
    async with pipeline.session_factory() as session:
        row = await session.get(Vacancy, vacancy_id)
        unparsed, text = not row.is_parsed, row.raw_text
    outcome = "duplicate"
    if unparsed and text and article_urls(text):
        outcome = "article"
    elif unparsed and text:
        await pipeline.reload_resources()
        stored = await finish_orphan(pipeline, vacancy_id, text, Intake(allow_delete=False, hands_over=False))
        outcome = "duplicate" if stored else "llm"
    tell(pipeline, outcome, vacancy_id)


async def orphan_intake(pipeline, vacancy_id: int, intake: Intake) -> Intake:
    """Как вести брошенную недоразобранной строку: заведённую человеком — без передачи.

    Отдавать ли её откликателю, человек решал при заведении, и решение это
    жило только в окне. Дочитывают такую строку подбор недоразобранного и все,
    кто наткнулся на её перепост, — обход канала и искатель, — и правило у них
    одно (`finish_orphan`).
    """
    async with pipeline.session_factory() as session:
        by_hand = await made_by_hand(session, vacancy_id)
    return replace(intake, hands_over=False) if by_hand else intake


async def finish_orphan(pipeline, vacancy_id: int, text: str, intake: Intake) -> bool:
    """Дочитать брошенную недоразобранной строку этим текстом и провести дальше;
    ответ — записан ли исход.

    Текст бывает и чужой — перепост из другого источника: разбор идёт по нему
    и с доводами зовущего, а ложится в ту строку — совпадение отпечатков
    ручается, что тексты почти дословны. Полон ли текст, проверяет зовущий:
    дочитывать шапкой без статьи нельзя.
    """
    intake = await orphan_intake(pipeline, vacancy_id, intake)
    return await judge_and_hand_over(pipeline, vacancy_id, text, intake)


async def to_apply(session_factory, vacancy_ids: list[int]) -> list[int]:
    """Что из разобранного поставить в очередь откликов: ждущее отклика после вердикта."""
    if not vacancy_ids:
        return []
    async with session_factory() as session:
        rows = await session.scalars(select(Vacancy.id).where(
            Vacancy.id.in_(vacancy_ids), AWAITS_APPLICATION))
        chosen = set(rows)
    return [vacancy_id for vacancy_id in vacancy_ids if vacancy_id in chosen]


async def new_to_apply(session_factory) -> list[int]:
    """Всё, что ждёт отклика и разобрано, свежие первыми."""
    async with session_factory() as session:
        return list(await session.scalars(
            select(Vacancy.id)
            .where(AWAITS_APPLICATION, PARSED_ONLY)
            .order_by(*LAST_VACANCY_ORDER)
        ))


async def hand_over(pipeline, judged: list[tuple[int, Judged]], *, applies: bool) -> None:
    """Отклик раньше догона: догон, пошедший первым, положил бы наше письмо
    в переписку без вакансии. Сорвавшийся отклик догона не отменяет: новый HR
    уже в базе, и пустая переписка у него — та же беда.

    Откликателя не зовут, если его не просил зовущий (`applies`) или выключен
    автоотклик, а догон остаётся в обоих случаях: догон — не отклик. Режим
    решается здесь, один раз на все разборы; просить ли — у зовущего, и сюда
    признаков строки не читают. Подтверждение передачи не касается: человека
    ждёт уже откликатель."""
    stored = [vacancy_id for vacancy_id, one in judged if one.stored]
    handing = applies and pipeline.rs.auto_apply != "false"
    chosen = await to_apply(pipeline.session_factory, stored) if handing else []
    try:
        if chosen:
            await pipeline.apply(chosen)
    finally:
        for _, one in judged:
            if one.fresh_hr is not None:
                spawn_hr_backfill(pipeline, one.fresh_hr)


async def judge_and_hand_over(pipeline, vacancy_id: int, text: str, intake: Intake) -> bool:
    """Разбор одной вакансии и передача её итога; ответ — записан ли исход."""
    judged = await parse.parse_and_update_vacancy(
        pipeline, vacancy_id, text, intake.channel, allow_delete=intake.allow_delete)
    if intake.tells_window:
        tell(pipeline, "ok" if judged.stored else "llm", vacancy_id)
    await hand_over(pipeline, [(vacancy_id, judged)], applies=intake.hands_over)
    return judged.stored
