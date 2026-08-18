"""Что случается с вакансией после того, как её завели.

Само заведение живёт не здесь, а в конвейере (`flows/ingest`): строка
`Vacancy(...)` собирается там и только там. Обещай докстрока «от заведения»,
читатель искал бы запись строки в этом модуле и не нашёл.

Дальше вся её жизнь: переводы статуса с историей, отметки в ленте, отметки о
мусоре, перевод вакансий на другого владельца, удаление. Перечислять их фразой
смысла нет — предмет один, вакансия, и меняется он по-разному.

Соседом стоит `vacancies_ghosting`: там вакансию двигает не сделанное кем-то, а
несделанное — молчание HR дольше срока, — и счёт этого молчания живёт своим
модулем. Общий у них один переход, `move_status`.
"""

import logging

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.domain.transitions import should_apply_status
from backend.models import (
    Message,
    StatusHistorySource,
    TrashEvent,
    Vacancy,
    VacancyEvent,
    VacancyStatus,
    VacancyStatusHistory,
)
from backend.payloads import Classification

logger = logging.getLogger(__name__)


# Зеркало JS-`ended` (client/web/state/vacancy_card.js). Применяется
# ко всем записям `vacancy_status_history.explanation`, чтобы заметки в
# таймлайне рендерились единообразно как "Status: reason." — независимо
# от того, ЛЛМ ли это, ручной ввод или подпись авто-отправки.
def _ensure_trailing_period(s: str | None) -> str | None:
    if s is None:
        return None
    trimmed = s.strip()
    if not trimmed:
        return None
    if trimmed[-1] in ".!?…:":
        return trimmed
    return trimmed + "."


def move_status(
    vacancy: Vacancy,
    new_status: VacancyStatus,
    explanation: str | None,
    *,
    message_id: int | None = None,
    source: StatusHistorySource = StatusHistorySource.SYSTEM,
) -> VacancyStatusHistory:
    """Оформить переход вакансии в ``new_status``.

    Решать, переводить ли, остаётся зовущему — у каждого пути своё условие
    (`force` у отклика, граф переходов у классификатора, срок молчания у
    гашения, воля пользователя у экрана).

    Отметка «применено» снята только там, где статус остался прежним, а это
    бывает у одного пути из четырёх — у экрана, где комментарий пишется и к
    нынешнему статусу. Трём остальным равный переход не достаётся вовсе:
    `should_apply_status` отвергает его первой же строкой, а в «пропала»
    уходят только из «отклик отправлен» и «в работе».

    Строку зовущий кладёт в сессию сам: он же решает, нужен ли ему сразу
    её идентификатор.

    Имя открытое: тем же переходом гасят замолчавшие вакансии, а живёт это
    счётом молчания в `vacancies_ghosting` — предмет там свой.
    """
    previous = vacancy.status
    applied = previous != new_status
    if applied:
        vacancy.status = new_status
    return VacancyStatusHistory(
        vacancy_id=vacancy.id,
        message_id=message_id,
        previous_status=previous,
        status=new_status,
        explanation=_ensure_trailing_period(explanation),
        applied=applied,
        source=source,
    )


async def repoint_vacancies(
    session: AsyncSession, column, *, absorbed_id: int, survivor_id: int | None
) -> int:
    """Переписывает владельца вакансий: с уходящей строки на названную.

    Названная — либо оставшаяся при слиянии, либо `None` при удалении: у
    вакансии нет владельца, и она переживает удаление человека, компании и
    канала. Правило одно, и раньше оно было выписано пятью телами — двумя
    слияниями и тремя удалениями.

    Отметка о мусоре при удалении канала отвязывается **своим** запросом и
    сюда не переводится: это другая таблица, а объявление держит одну —
    вакансии. Второй довод-колонка сделал бы его «переписать владельца у
    чего угодно», то есть чужим оборотом вокруг `update`.

    Возвращает число переехавших — его пишут в журнал: и слияние, и удаление
    необратимы, и по записи потом видно, скольких это задело.
    """
    return (
        await session.execute(
            update(Vacancy).where(column == absorbed_id).values({column: survivor_id})
        )
    ).rowcount or 0


async def mark_vacancy_applied(
    session: AsyncSession, vacancy_id: int, explanation: str | None, *, force: bool
) -> bool:
    """Перевести вакансию в «отклик отправлен» и записать это в историю.

    Липкость статуса уважается: у отказа и у оффера отклик уже ничего не
    решает, и автоматика их не двигает — `force` приходит от нажатия в
    окне, где решает человек.

    Отвечает, состоялся ли перевод. Историю пишет всегда, когда перевод
    состоялся: без неё карточка показывает сменившийся статус без следа
    о том, кто и когда его тронул.

    Транзакцию закрывает зовущий.
    """
    vacancy = await session.get(Vacancy, vacancy_id)
    if vacancy is None or not should_apply_status(
        vacancy.status, VacancyStatus.APPLIED, force=force
    ):
        return False
    session.add(move_status(vacancy, VacancyStatus.APPLIED, explanation))
    return True


async def last_status_history_id(
    session: AsyncSession, vacancy_id: int
) -> int | None:
    """Последняя строка истории вакансии; пусто — истории ещё нет.

    Нужна снимком «до»: по нему потом видно, объяснил ли смену статуса
    кто-то другой, пока шла долгая работа.
    """
    return await session.scalar(
        select(func.max(VacancyStatusHistory.id)).where(
            VacancyStatusHistory.vacancy_id == vacancy_id
        )
    )


async def record_rerun(
    session: AsyncSession,
    vacancy_id: int,
    previous: VacancyStatus,
    last_history: int | None,
) -> None:
    """Отметить в истории вакансии, что её разобрали заново.

    Строку пишет не `move_status`, хотя рядом, и собирает её своим телом: тот
    двигает статус и заводит запись об этом, а здесь статус уже сдвинут —
    разбор ставит его прямо, как у только что заведённой строки. Без этой
    записи история обрывалась бы на прежнем статусе, а шапка карточки
    показывала бы новый, и связать их было бы нечем. Общая сборка строки обоим
    не годится: полей у неё семь, и довод на каждое — это уже не помощник, а
    второй конструктор.

    Записи не будет в двух случаях. Статус не менялся — рассказывать нечего.
    Или переход уже объяснён строкой, легшей за время прогона: самоотклик
    внутри разбора переводит вакансию в «отклик отправлен» и пишет об этом
    сам, и вторая строка о том же переходе показала бы его в ленте дважды.

    Транзакцию закрывает зовущий.
    """
    vacancy = await session.get(Vacancy, vacancy_id)
    if vacancy is None or vacancy.status == previous:
        return
    if await last_status_history_id(session, vacancy_id) != last_history:
        return
    session.add(
        VacancyStatusHistory(
            vacancy_id=vacancy_id,
            previous_status=previous,
            status=vacancy.status,
            explanation=_ensure_trailing_period("Прогон заново"),
            applied=True,
            source=StatusHistorySource.SYSTEM,
        )
    )


def _log_status_change(vacancy_id: int, previous, new_status, detail: str) -> None:
    """Строка журнала о смене статуса — одна на ручную правку и на разбор.

    Отличаются они только хвостом в скобках, и порознь эти две строки
    разъезжались бы молча: их читают вперемешку, отвечая на вопрос «почему
    вакансия оказалась здесь».
    """
    logger.info(
        "vacancy %d: status %s -> %s (%s)",
        vacancy_id,
        previous.value if previous else None,
        new_status.value,
        detail,
    )


def _log_manual_change(
    history: VacancyStatusHistory, vacancy_id: int, previous, new_status
) -> None:
    """След ручной правки — своим уровнем у смены статуса и у заметки.

    Смена статуса — событие, о котором спрашивают потом («почему вакансия
    в отказе»), и она пишется громко. Заметка без смены статуса громкой
    строки не заслуживает: её видно в самой ленте карточки.
    """
    if history.applied:
        _log_status_change(
            vacancy_id, previous, new_status, f"manual, applied={history.applied}"
        )
    else:
        logger.debug(
            "vacancy %d: comment-only history added (status=%s)",
            vacancy_id,
            new_status.value,
        )


async def change_vacancy_status(
    session: AsyncSession,
    vacancy_id: int,
    new_status: VacancyStatus,
    explanation: str | None,
) -> VacancyStatusHistory | None:
    """Manual status change from the UI.

    Overrides stickiness unconditionally — every UI call is by definition
    explicit, so sticky statuses (Offer, Decline, Not Fit…) move on user
    request. Use ``apply_classification`` for the auto-classifier path
    that *should* respect stickiness.

    No-op short-circuit: if the status is unchanged AND the explanation
    is empty/whitespace, no row is written and ``None`` is returned —
    avoids history pollution from accidental "Применить" clicks. Returns
    ``None`` also if the vacancy doesn't exist.

    Caller wraps in ``session.begin()``.
    """
    vacancy = await session.get(Vacancy, vacancy_id)
    if vacancy is None:
        return None
    previous = vacancy.status
    cleaned_explanation = _ensure_trailing_period(explanation)
    if previous == new_status and cleaned_explanation is None:
        return None
    history = move_status(
        vacancy, new_status, cleaned_explanation, source=StatusHistorySource.USER
    )
    session.add(history)
    await session.flush()
    _log_manual_change(history, vacancy_id, previous, new_status)
    return history


async def update_status_history_explanation(
    session: AsyncSession, history_id: int, explanation: str | None
) -> bool:
    """Replace ``vacancy_status_history.explanation`` для одной записи.

    Зеркалит поведение ``update_vacancy_notes``: empty / whitespace-only
    нормализуется в ``NULL`` (UI рендерит «без комментария» для NULL,
    отличая «удалили коммент» от «забыли набрать»). Отдаётся сама запись, а
    не признак «записали»: окно принимает ответ за исходное состояние поля, и
    знать ему надо, что именно легло — здесь к пояснению ещё и дописывается
    точка. `None` значит «такой записи нет». Caller wraps in
    ``session.begin()``.
    """
    row = await session.get(VacancyStatusHistory, history_id)
    if row is None:
        return None
    row.explanation = _ensure_trailing_period(explanation)
    return row


async def record_trash_event(
    session: AsyncSession,
    *,
    source_channel_id: int | None,
    source_msg_id: int | None,
    reason: str | None,
) -> None:
    """Записать факт «пост из канала классифицирован как trash».
    Используется ДО удаления Vacancy-ряда (в auto-ingest режиме), чтобы
    трекать «сколько мусора прислал канал» — иначе после delete этой
    информации в БД не остаётся. Caller оборачивает в session.begin().

    Один пост — одна отметка. Тот же пост приходит на разбор второй раз после
    сброса курсора канала, и без этой проверки числа «сколько мусора прислал
    канал» росли бы от каждого сброса, ничего нового не узнав.
    """
    if source_msg_id is not None and await _trash_noted(
        session, source_channel_id, source_msg_id
    ):
        return
    session.add(TrashEvent(
        source_channel_id=source_channel_id,
        source_msg_id=source_msg_id,
        reason=reason,
    ))


async def _trash_noted(
    session: AsyncSession, source_channel_id: int | None, source_msg_id: int
) -> bool:
    """Отмечен ли этот пост мусором раньше."""
    return (
        await session.scalar(
            select(TrashEvent.id).where(
                TrashEvent.source_channel_id == source_channel_id,
                TrashEvent.source_msg_id == source_msg_id,
            ).limit(1)
        )
    ) is not None


async def delete_vacancy(session: AsyncSession, vacancy_id: int) -> bool:
    """Hard-delete a vacancy + its history + its events.

    ``message.vacancy_id`` is nullified rather than deleted so the chat
    history stays intact (the user might still want to see the conversation
    with the HR after the vacancy was wiped). Returns False if the vacancy
    doesn't exist.

    Caller wraps in ``session.begin()``.
    """
    vacancy = await session.get(Vacancy, vacancy_id)
    if vacancy is None:
        return False
    await session.execute(
        update(Message)
        .where(Message.vacancy_id == vacancy_id)
        .values(vacancy_id=None)
    )
    await session.execute(
        delete(VacancyStatusHistory).where(
            VacancyStatusHistory.vacancy_id == vacancy_id
        )
    )
    await session.execute(
        delete(VacancyEvent).where(VacancyEvent.vacancy_id == vacancy_id)
    )
    await session.delete(vacancy)
    await session.flush()
    logger.info(
        "Deleted vacancy %d (msgs detached, history+events purged)", vacancy_id
    )
    return True


async def add_vacancy_event(
    session: AsyncSession,
    vacancy_id: int,
    kind: str,
    payload: dict | None = None,
) -> VacancyEvent:
    """Append a non-status event to the timeline (parsed, ingested, rerun, ...).

    Status changes go to ``vacancy_status_history`` instead. Caller wraps
    in ``session.begin()``.
    """
    event = VacancyEvent(
        vacancy_id=vacancy_id,
        kind=kind,
        payload=(payload or None),
    )
    session.add(event)
    await session.flush()
    return event


def _log_blocked_verdict(
    vacancy_id: int, previous, classification: Classification, message_id: int
) -> None:
    """След вердикта, который не пустил заслон переходов.

    Так бывает, когда разбор присылает «приглашение» на вакансию, уже
    стоящую в отказе. В ленту такой вердикт не пишется вовсе: раньше туда
    клали переход с признаком «не применён», он вылезал отдельной строкой и
    сбивал с толку. Входящее письмо уже сохранено выше по стеку — этого
    следа хватает.
    """
    logger.info(
        "vacancy %d: classifier verdict %s blocked by state-machine "
        "(current=%s, msg=%d) — no history row written",
        vacancy_id,
        classification.status.value,
        previous.value if previous else None,
        message_id,
    )


async def apply_classification(
    session: AsyncSession,
    vacancy_id: int,
    message_id: int,
    classification: Classification,
) -> None:
    vacancy = await session.get(Vacancy, vacancy_id)
    if vacancy is None:
        logger.warning("apply_classification: vacancy %s not found", vacancy_id)
        return
    previous = vacancy.status
    if not should_apply_status(previous, classification.status):
        _log_blocked_verdict(vacancy_id, previous, classification, message_id)
        return
    _log_status_change(
        vacancy_id, previous, classification.status, f"auto, msg={message_id}"
    )
    session.add(
        move_status(
            vacancy,
            classification.status,
            classification.explanation,
            message_id=message_id,
        )
    )
