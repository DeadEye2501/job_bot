"""Граф разрешённых авто-переходов статуса вакансии, вместе с условиями
ухода в Ghosting по таймеру — они часть той же ветки графа."""

from backend.models import VacancyStatus

# Единый state-machine для авто-переходов статуса вакансии. Источник
# правды — docs/Статусы.md. Применяется к переходам по чужому ходу
# (LLM-классификация HR-реплая); отклик двигает статус своим правилом,
# `APPLY_MOVES_FROM`. Ручная смена
# статуса юзером через UI (`change_vacancy_status`) граф игнорирует —
# юзер вправе выставить любой статус из любого.
#
# Терминалы (пустое множество) — auto-классификация для них вообще не
# вызывается: заслон `flows/auto_gate` отбивает их до похода в LLM, экономя
# токены и не засоряя timeline призрачными `applied=False` строками. Он же
# закрывает и `New`: выход оттуда один, в `Applied`, и делает его отправка,
# а не письмо собеседника.
#
# Test/Invitation — короткие транзитные статусы: «мяч у меня». Как
# только этап завершён, вакансия идёт в In Progress (ожидание фидбека
# от HR). Поэтому повторный Invitation/Test после Test/Invitation в
# графе НЕТ — он возможен только из In Progress.
#
# Ghosting — отдельный таймер-механизм (см. mark_ghosted_vacancies +
# GHOSTING_TIMEOUT_DAYS), не auto-результат HR-реплая. Из Ghosting
# выход разрешён, если HR вдруг ответил — оживаем в
# Answered/Invitation/Test/Offer/Decline.
ALLOWED_AUTO_TRANSITIONS: dict[VacancyStatus, frozenset[VacancyStatus]] = {
    VacancyStatus.NEW: frozenset({VacancyStatus.APPLIED}),
    VacancyStatus.APPLIED: frozenset(
        {
            VacancyStatus.ANSWERED,
            VacancyStatus.INVITATION,
            VacancyStatus.TEST,
            VacancyStatus.OFFER,
            VacancyStatus.DECLINE,
            VacancyStatus.GHOSTING,
        }
    ),
    VacancyStatus.ANSWERED: frozenset(
        {
            VacancyStatus.INVITATION,
            VacancyStatus.TEST,
            VacancyStatus.OFFER,
            VacancyStatus.DECLINE,
        }
    ),
    VacancyStatus.INVITATION: frozenset(
        {
            VacancyStatus.IN_PROGRESS,
            VacancyStatus.OFFER,
            VacancyStatus.DECLINE,
        }
    ),
    VacancyStatus.TEST: frozenset(
        {
            VacancyStatus.IN_PROGRESS,
            VacancyStatus.OFFER,
            VacancyStatus.DECLINE,
        }
    ),
    VacancyStatus.IN_PROGRESS: frozenset(
        {
            VacancyStatus.INVITATION,
            VacancyStatus.TEST,
            VacancyStatus.OFFER,
            VacancyStatus.DECLINE,
            VacancyStatus.GHOSTING,
        }
    ),
    VacancyStatus.GHOSTING: frozenset(
        {
            VacancyStatus.ANSWERED,
            VacancyStatus.INVITATION,
            VacancyStatus.TEST,
            VacancyStatus.OFFER,
            VacancyStatus.DECLINE,
        }
    ),
    VacancyStatus.OFFER: frozenset(),
    VacancyStatus.DECLINE: frozenset(),
    VacancyStatus.SCAM: frozenset(),
    VacancyStatus.NOT_FIT: frozenset(),
}


def is_terminal_for_auto(status: VacancyStatus) -> bool:
    """True если из ``status`` нет ни одного разрешённого авто-перехода.

    Спрашивает об этом заслон `flows/auto_gate`, а через него — приём письма
    и отложенный разбор: обращение к модели на терминальной вакансии
    (Offer/Decline/Scam/Not Fit) стоило бы денег и оставляло бы призрачные
    строки в vacancy_status_history.
    """
    return not ALLOWED_AUTO_TRANSITIONS[status]


# Сколько дней молчания HR'а считать ghosting'ом. Применимо к
# Applied и In Progress (в них «мяч на стороне HR»). Для остальных
# статусов timer не запускается (Test/Invitation = мяч у меня;
# Answered = промежуточная фаза, переход в Ghosting прямо из неё
# не предусмотрен графом).
GHOSTING_TIMEOUT_DAYS = 14

# Из каких статусов вакансия может уйти в Ghosting по таймеру.
# Должно быть подмножеством состояний, у которых GHOSTING есть в
# ALLOWED_AUTO_TRANSITIONS. Хардкод этого подмножества здесь —
# защита от случайного расхождения: если кто-то добавит Ghosting в
# graph для нового from-state, ему придётся явно также включить
# его в этот сет.
GHOSTING_ELIGIBLE_FROM: frozenset[VacancyStatus] = frozenset(
    {VacancyStatus.APPLIED, VacancyStatus.IN_PROGRESS}
)


# Откуда отклик проводит вакансию в Applied: отклика ещё не было или с
# вакансией попрощались. Дальше по воронке отклик — реплика переписки, и
# статус он не трогает. Кто откликнулся, правило не знает.
APPLY_MOVES_FROM: frozenset[VacancyStatus] = frozenset(
    {
        VacancyStatus.NEW,
        VacancyStatus.NOT_FIT,
        VacancyStatus.SCAM,
        VacancyStatus.GHOSTING,
        VacancyStatus.DECLINE,
    }
)


def should_apply_status(current: VacancyStatus, new: VacancyStatus) -> bool:
    """Гейт авто-перехода по графу: ответ HR и таймер молчания.

    Ручную смену статуса с экрана (`change_vacancy_status`) граф не
    покрывает: человек вправе выставить любой статус из любого.
    """
    return new in ALLOWED_AUTO_TRANSITIONS[current]
