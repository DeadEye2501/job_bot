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
    """Полных лет между датами. Отрицательным не бывает: место, начатое
    «завтра», — опечатка, а не отрицательный стаж."""
    years = end.year - start.year - ((end.month, end.day) < (start.month, start.day))
    return max(years, 0)


def years_in_it(experiences, today: date) -> int:
    """Сколько лет опыта — от самого раннего места работы до сегодня.

    Считается по началу, а не по сумме сроков: перерывы между местами опытом
    быть не перестают, а вычесть их значило бы спорить с тем, как этот срок
    называют в резюме.
    """
    return full_years(min(e.start_date for e in experiences), today)


def skill_years(experiences, today: date) -> int:
    """Стаж по навыку — от первого места, где он назван, до конца последнего.

    Правило то же, что у общего стажа, кроме конца: навык с прошлой работы
    не растёт до сегодня.
    """
    end = max(e.end_date or today for e in experiences)
    return full_years(min(e.start_date for e in experiences), end)
