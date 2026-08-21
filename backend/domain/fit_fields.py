"""Пригодность по полям-перечислениям: что решается о вакансии без модели.

Грейд и формат работы названы перечислениями с обеих сторон — у вакансии это
разобранное поле, у кандидата список принимаемых значений, — и сравнение их
не требует ни смысла текста, ни модели. У модели это сравнение и забрали:
видя все критерии разом, она путала их между собой, а стоил каждый её ответ
целого зова.

Обоснование пишется требованием вакансии, той же формой, что требуется от
модели: человек свои настройки знает, ему нужно понять, чего хочет объявление.
"""

from backend.domain.taxonomy import GRADES, WORK_FORMATS, WORK_FORMAT_LABELS_RU


def _blocked(
    value: str | None, accepted: list[str] | None, known: tuple[str, ...]
) -> str | None:
    """Значение вакансии, которого нет среди принимаемых; пусто — заслона нет.

    Молчание с любой стороны заслона не поднимает, и обе причины разные.
    Пустой список принимаемых значит «кандидат не ограничивал» — заслон
    выключен. Не названное в объявлении поле значит «неизвестно»: половина
    постов грейда и формата не называет вовсе, и отказ по молчанию выкосил
    бы их все.

    Значение вне замкнутого перечня тоже пропускается: его придумал разбор, и
    отказ по нему был бы отказом по нашей же ошибке.
    """
    if not accepted or not value:
        return None
    named = value.strip().lower()
    if named not in known:
        return None
    taken = {one.strip().lower() for one in accepted if one}
    return None if named in taken else named


def grade_refusal(grade: str | None, accepted: list[str] | None) -> str | None:
    """Отказ по грейду вакансии; пусто — грейд не мешает.

    Грейд остаётся написанным по-английски: тем же словом он назван и в
    объявлении, и в анкете, а перевод развёл бы их написания.
    """
    blocked = _blocked(grade, accepted, GRADES)
    return None if blocked is None else f"Требуется грейд {blocked}."


def work_format_refusal(remote: str | None, accepted: list[str] | None) -> str | None:
    """Отказ по формату работы; пусто — формат не мешает.

    Формат называется по-русски: строка едет в окно как есть, и «office»
    человек читает хуже, чем «офис».
    """
    blocked = _blocked(remote, accepted, WORK_FORMATS)
    if blocked is None:
        return None
    return f"Формат работы — {WORK_FORMAT_LABELS_RU[blocked]}."
