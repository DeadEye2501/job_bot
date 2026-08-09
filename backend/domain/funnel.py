"""Ступени воронки отбора, выраженные наборами статусов вакансии."""

from backend.models import VacancyStatus

# `FIT_EXCLUDE`: статусы, которые НЕ считаются подходящими — либо валидатор
#   отверг как Not Fit, либо это Scam (мы заведомо не будем взаимодействовать
#   с источником).
FIT_EXCLUDE: frozenset[VacancyStatus] = frozenset({
    VacancyStatus.NOT_FIT,
    VacancyStatus.SCAM,
})

# `APPLIED`: что мы реально отправили, либо ответ уже пришёл / заглох.
#   New = подходит, но ещё не отправили.
APPLIED: frozenset[VacancyStatus] = frozenset({
    VacancyStatus.APPLIED,
    VacancyStatus.ANSWERED,
    VacancyStatus.TEST,
    VacancyStatus.INVITATION,
    VacancyStatus.IN_PROGRESS,
    VacancyStatus.OFFER,
    VacancyStatus.DECLINE,
    VacancyStatus.GHOSTING,
})

# `RESPONDED`: получили ответ от работодателя (включая отказ — Decline тоже
#   ответ). Applied = ждём, Ghosting = тишина.
RESPONDED: frozenset[VacancyStatus] = frozenset({
    VacancyStatus.ANSWERED,
    VacancyStatus.TEST,
    VacancyStatus.INVITATION,
    VacancyStatus.IN_PROGRESS,
    VacancyStatus.OFFER,
    VacancyStatus.DECLINE,
})

# `INVITED`: позвали дальше разговора — собеседование и всё, что за ним.
INVITED: frozenset[VacancyStatus] = frozenset({
    VacancyStatus.INVITATION,
    VacancyStatus.IN_PROGRESS,
    VacancyStatus.OFFER,
})
