"""Граф разрешённых авто-переходов статуса вакансии, вместе с условиями
ухода в Ghosting по таймеру — они часть той же ветки графа."""

from backend.models import VacancyStatus

# Единый state-machine для авто-переходов статуса вакансии. Источник
# правды — docs/Статусы.md. Применяется ко ВСЕМ авто-источникам
# (LLM-классификация HR-реплая, авто-отправка отклика). Ручная смена
# статуса юзером через UI (`change_vacancy_status`) граф игнорирует —
# юзер вправе выставить любой статус из любого.
#
# Терминалы (пустое множество) — auto-классификация для них вообще не
# вызывается: `process_dm` гейтит до похода в LLM, экономя токены и не
# засоряя timeline призрачными `applied=False` строками.
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

    Используется в `process_dm` для отсечения вызова LLM-классификатора
    на терминальных вакансиях (Offer/Decline/Scam/Not Fit) — экономит
    LLM-токены и предотвращает запись призрачных строк в
    vacancy_status_history.
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


def should_apply_status(
    current: VacancyStatus,
    new: VacancyStatus,
    *,
    force: bool = False,
) -> bool:
    """Гейт авто-перехода статуса. Используется во ВСЕХ
    auto-источниках смены статуса (LLM-классификатор HR-реплая,
    `Bot.send`).

    Ручную UI-смену статуса (`change_vacancy_status`) граф НЕ покрывает —
    она работает напрямую, юзер вправе выставить любой статус.

    `force=True` — особый режим для кнопки «Отправить отклик»: разрешает
    переход NEW/NOT_FIT → APPLIED поверх графа. Остальные комбинации
    при force=True подчиняются графу — нельзя случайным кликом «Отправить»
    затереть Decline/Offer/Ghosting/Scam/In Progress в Applied. Manual-UI
    смена статуса для этого имеет отдельный путь.

    Переход в тот же самый статус отдельной охраны не имеет: петель в графе
    нет, и такой переход отсеивается последней строкой наравне с любым
    другим неразрешённым. Охрана поверх графа объявила бы этот запрет
    дважды, и заведённая когда-нибудь петля осталась бы недостижимой —
    молча и в обе стороны.
    """
    if (
        force
        and new == VacancyStatus.APPLIED
        and current in (VacancyStatus.NEW, VacancyStatus.NOT_FIT)
    ):
        return True
    return new in ALLOWED_AUTO_TRANSITIONS[current]
