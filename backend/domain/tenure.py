"""Сроки мест работы: период и стаж, общий и по навыку."""

from datetime import date


def place_period(place) -> str:
    """Период места работы: «ММ.ГГГГ — ММ.ГГГГ» или «— настоящее время».

    Одна строка на все анкеты: письмо в Telegram и агент видят даты одинаково.
    """
    end = place.end_date.strftime("%m.%Y") if place.end_date else "настоящее время"
    return f"{place.start_date.strftime('%m.%Y')} — {end}"


def years_text(years: int) -> str:
    """Стаж словами — одной записью у анкеты агента и у блока письма. Меньше
    года — словами: «0+ г.» модель пересказала бы как «0+ годами опыта»."""
    return f"{years}+ г." if years else "меньше года"


def full_years(start: date, end: date) -> int:
    """Полных лет между датами. Отрицательным не бывает: дата рождения
    «завтра» — опечатка, а не отрицательный возраст."""
    years = end.year - start.year - ((end.month, end.day) < (start.month, start.day))
    return max(years, 0)


def _month_number(day: date) -> int:
    return day.year * 12 + day.month


def worked_years(experiences, today: date) -> int:
    """Полных лет в сумме месяцев, отработанных на данных местах.

    Месяцы считаются целиком с обоих концов: импорт резюме пишет конец места
    первым числом месяца, окно — любым днём, и «01.2020 — 12.2020» в обоих
    случаях — год. Перерывы не считаются, пересекающиеся места — один раз.
    Срок не идёт дальше сегодняшнего месяца: будущее стажем ещё не стало.
    Место, кончающееся раньше начала, — опечатка ввода — ничего не даёт.
    """
    spans = sorted(
        (_month_number(e.start_date), _month_number(min(e.end_date or today, today)))
        for e in experiences
    )
    months, counted_to = 0, 0
    for start, end in spans:
        start = max(start, counted_to + 1)
        if end >= start:
            months += end - start + 1
            counted_to = end
    return months // 12
