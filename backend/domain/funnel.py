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

# `IN_PROGRESS_STEP`: ступень «В процессе» в шапке статистики — разговор идёт,
#   но ничем ещё не кончился.
#
# С `INVITED` не сводится и лежит рядом нарочно: там отвечают на другой вопрос
# — «позвали ли дальше разговора», — и потому туда входит оффер, а тестовое
# задание не входит. Здесь наоборот: оффер это уже исход, а тестовое — та самая
# середина. Наборы разъезжались молча, и `In Progress` не попадал ни в один: на
# экране под шапкой он горел своей строкой, а счётчик над ним показывал ноль.
IN_PROGRESS_STEP: frozenset[VacancyStatus] = frozenset({
    VacancyStatus.INVITATION,
    VacancyStatus.TEST,
    VacancyStatus.IN_PROGRESS,
})


def percent_or_none(numerator: int, denominator: int) -> int | None:
    """Целая доля от целого, а при пустом целом — пусто, а не ноль.

    Пусто и ноль здесь разное: «откликов не было» и «откликнулись, ответов
    ноль» на экране читаются по-разному, и второе — беда, о которой человеку
    надо знать. Округление до целого: доли ступеней показываются числом без
    дробной части.

    Доли с дробью считает `stats_pipeline`, и своим правилом: у него другой
    договор о виде ответа, а не то же самое в третьем написании.
    """
    if denominator <= 0:
        return None
    return int(round(numerator / denominator * 100))
