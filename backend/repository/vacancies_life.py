"""События, через которые вакансия проходит от заведения до удаления."""

import logging

from sqlalchemy import and_, delete, func, select, update
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


# Зеркало JS-`_ensureTrailingPeriod` (client/web/main.html). Применяется
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


def _move_status(
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
    session.add(_move_status(vacancy, VacancyStatus.APPLIED, explanation))
    return True


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
    history = _move_status(
        vacancy, new_status, cleaned_explanation, source=StatusHistorySource.USER
    )
    session.add(history)
    await session.flush()
    if history.applied:
        logger.info(
            "vacancy %d: status %s -> %s (manual, applied=%s)",
            vacancy_id,
            previous.value if previous else None,
            new_status.value,
            history.applied,
        )
    else:
        logger.debug(
            "vacancy %d: comment-only history added (status=%s)",
            vacancy_id,
            new_status.value,
        )
    return history


async def update_status_history_explanation(
    session: AsyncSession, history_id: int, explanation: str | None
) -> bool:
    """Replace ``vacancy_status_history.explanation`` для одной записи.

    Зеркалит поведение ``update_vacancy_notes``: empty / whitespace-only
    нормализуется в ``NULL`` (UI рендерит «без комментария» для NULL,
    отличая «удалили коммент» от «забыли набрать»). Returns False если
    history-id не найден. Caller wraps in ``session.begin()``.
    """
    row = await session.get(VacancyStatusHistory, history_id)
    if row is None:
        return False
    row.explanation = _ensure_trailing_period(explanation)
    return True


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
    """
    session.add(TrashEvent(
        source_channel_id=source_channel_id,
        source_msg_id=source_msg_id,
        reason=reason,
    ))


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
    allowed = should_apply_status(previous, classification.status)
    if not allowed:
        # Переход не разрешён state-machine'ом (например, classifier
        # выдал Invitation для уже-Decline вакансии). Раньше тут писали
        # призрачную VacancyStatusHistory с applied=False — она вылезала
        # в timeline отдельной строкой и сбивала с толку. Теперь не
        # пишем ничего: входящий DM уже сохранён как Message выше по
        # стеку, этого аудит-следа достаточно.
        logger.info(
            "vacancy %d: classifier verdict %s blocked by state-machine "
            "(current=%s, msg=%d) — no history row written",
            vacancy_id,
            classification.status.value,
            previous.value if previous else None,
            message_id,
        )
        return
    logger.info(
        "vacancy %d: status %s -> %s (auto, msg=%d)",
        vacancy_id,
        previous.value if previous else None,
        classification.status.value,
        message_id,
    )
    session.add(
        _move_status(
            vacancy,
            classification.status,
            classification.explanation,
            message_id=message_id,
        )
    )


async def mark_ghosted_vacancies(
    session: AsyncSession,
    *,
    timeout_days: int,
) -> list[int]:
    """Сканирует Applied/In Progress вакансии и переводит в Ghosting те,
    у которых HR молчит дольше ``timeout_days``.

    «Молчит» означает: ни одного входящего Message, и сам статус не
    менялся, и вакансия не создавалась в окне последних ``timeout_days``
    дней. Reference timestamp = max(last incoming Message.sent_at,
    last status change в текущий статус, vacancy.created_at).

    Возвращает список vacancy_id, переведённых в Ghosting. Caller
    оборачивает в session.begin() и выполняет commit.
    """
    from datetime import datetime, timedelta, timezone
    from backend.domain.transitions import GHOSTING_ELIGIBLE_FROM

    # SQLite + aiosqlite возвращает наивные datetime'ы даже при
    # DateTime(timezone=True), поэтому для Python-side сравнения с
    # v.created_at / max(sent_at) / max(changed_at) cutoff тоже должен
    # быть naive (UTC по конвенции — server_default=func.now()).
    cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(
        days=timeout_days
    )
    eligible_status_values = [s for s in GHOSTING_ELIGIBLE_FROM]
    # Один round-trip вместо 1+2N: pre-агрегируем последние таймстампы
    # по vacancy_id (для входящих DM) и по (vacancy_id, status) — для
    # status-history. OUTER JOIN потому, что у новых вакансий ещё может
    # не быть ни сообщений, ни истории.
    last_msg_subq = (
        select(
            Message.vacancy_id.label("vid"),
            func.max(Message.sent_at).label("last_msg_at"),
        )
        .where(Message.is_incoming.is_(True))
        .group_by(Message.vacancy_id)
        .subquery()
    )
    last_status_subq = (
        select(
            VacancyStatusHistory.vacancy_id.label("vid"),
            VacancyStatusHistory.status.label("status"),
            func.max(VacancyStatusHistory.changed_at).label("last_status_at"),
        )
        .group_by(
            VacancyStatusHistory.vacancy_id, VacancyStatusHistory.status
        )
        .subquery()
    )
    rows = (
        await session.execute(
            select(
                Vacancy,
                last_msg_subq.c.last_msg_at,
                last_status_subq.c.last_status_at,
            )
            .outerjoin(last_msg_subq, last_msg_subq.c.vid == Vacancy.id)
            .outerjoin(
                last_status_subq,
                and_(
                    last_status_subq.c.vid == Vacancy.id,
                    last_status_subq.c.status == Vacancy.status,
                ),
            )
            .where(Vacancy.status.in_(eligible_status_values))
        )
    ).all()
    if not rows:
        return []

    affected: list[int] = []
    for v, last_msg_at, last_status_at in rows:
        # Берём максимум из доступных временных меток. created_at
        # есть всегда, остальные могут быть None — фильтруем.
        timestamps = [v.created_at]
        if last_msg_at is not None:
            timestamps.append(last_msg_at)
        if last_status_at is not None:
            timestamps.append(last_status_at)
        last_activity = max(timestamps)
        if last_activity >= cutoff:
            continue
        # Перевод в Ghosting ни на какую реплику HR не ссылается: молчание
        # и есть повод, а сообщения, которого не было, у события нет.
        session.add(
            _move_status(
                v,
                VacancyStatus.GHOSTING,
                f"HR не отвечает более {timeout_days} дней — "
                "автоматически помечено как ghosting.",
            )
        )
        affected.append(v.id)
    return affected
