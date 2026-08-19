"""Смена статуса вакансии: решение, запись, история.

Поле `vacancy.status` пишется только отсюда. Раньше это было не так — разбор
объявления ставил статус своей строкой, и заметить это по коду было нечем:
заслон переходов проверялся тестами графа, а путь записи мимо графа ими не
покрывался вовсе.

Наружу торчат поводы, а не статусы: отклик ушёл, HR ответил, HR молчит,
объявление разобрано, человек выбрал руками. Что из повода следует и позволен
ли переход, решает модуль; сам перевод пишет `_move_status`, и он закрытый.
Рядом живёт работа с самими строками истории — прочитать последнюю, переписать
пояснение: предмет у них тот же, и порознь им жить негде.

Граф переходов (`domain/transitions`) писан автоматике, а не всякому поводу, и
это не послабление отдельным из них. Автоматический переход случается по
чужому ходу — пришло письмо, вышел срок молчания, — и там граф спрашивают
всегда. Повод от прямого нажатия человека судят другие правила: он и есть
решение, и спрашивать у графа разрешения на него не у чего.
"""

import logging
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.domain.transitions import should_apply_status
from backend.models import (
    StatusHistorySource,
    Vacancy,
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


@dataclass(frozen=True, slots=True)
class _Signature:
    """Подпись перехода: чем объяснён, по чьей воле и на какое письмо ссылается.

    Три значения об одном — о том, как переход выглядит в истории, — и в одну
    её строку они и ложатся, все три сразу.

    Умолчания названы по самому частому случаю: переход от автоматики, ни на
    какое письмо не ссылающийся. Двум путям из четырёх хватает их целиком.
    """

    explanation: str | None = None
    message_id: int | None = None
    source: StatusHistorySource = StatusHistorySource.SYSTEM


def _move_status(
    vacancy: Vacancy,
    new_status: VacancyStatus,
    sign: _Signature,
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
        message_id=sign.message_id,
        previous_status=previous,
        status=new_status,
        explanation=_ensure_trailing_period(sign.explanation),
        applied=applied,
        source=sign.source,
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
    session.add(
        _move_status(vacancy, VacancyStatus.APPLIED, _Signature(explanation))
    )
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

    Строку пишет не `_move_status`, хотя рядом, и собирает её своим телом: тот
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
    history = _move_status(
        vacancy,
        new_status,
        _Signature(cleaned_explanation, source=StatusHistorySource.USER),
    )
    session.add(history)
    await session.flush()
    _log_manual_change(history, vacancy_id, previous, new_status)
    return history


async def update_status_history_explanation(
    session: AsyncSession, history_id: int, explanation: str | None
) -> VacancyStatusHistory | None:
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
        _move_status(
            vacancy,
            classification.status,
            _Signature(classification.explanation, message_id=message_id),
        )
    )


def apply_silence(
    session: AsyncSession, vacancy: Vacancy, timeout_days: int
) -> None:
    """Погасить вакансию, у которой HR молчит дольше срока.

    Граф здесь не спрашивается, и это прежнее решение, а не послабление:
    кандидатов отбирают запросом, суженным до статусов, из которых уход в
    Ghosting разрешён (`GHOSTING_ELIGIBLE_FROM`), и повторной проверке
    нечего было бы добавить. Перевод ни на какое письмо не ссылается:
    молчание и есть повод, а сообщения, которого не было, у события нет.

    Транзакцию закрывает зовущий — он же перебирает замолчавшие строки.
    """
    session.add(
        _move_status(
            vacancy,
            VacancyStatus.GHOSTING,
            _Signature(
                f"HR не отвечает более {timeout_days} дней — "
                "автоматически помечено как ghosting."
            ),
        )
    )


def apply_parse_outcome(vacancy: Vacancy, new_status: VacancyStatus) -> None:
    """Поставить статус, вынесенный разбором объявления.

    Единственный повод, который двигает статус без строки в истории: разбор
    ставит начальный статус, а не переходит из одного в другой. Автоматике
    этого хватает — она разбирает только те строки, которых разбор ещё не
    касался. Из любого статуса, включая отказ и оффер, вакансию сбрасывает
    прогон заново, а он идёт от нажатия человека, и графа не спрашивает по
    той же причине, что и ручная смена.

    След остаётся другой: у первого разбора — строка ленты «разобрано», у
    повторного — ещё и запись «Прогон заново» (`record_rerun`), которая
    ложится позже, когда виден весь исход прогона.

    Сессии не просит: строку вакансии зовущий уже держит и пишет её вместе с
    остальными полями разбора, одной сделкой.
    """
    vacancy.status = new_status
