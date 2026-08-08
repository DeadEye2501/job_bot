"""Следствия объединённого стека разобранной вакансии.

Модель делит навыки на обязательные и желательные — по этому делению считается
оценка. Всем остальным деление не нужно: в колонку базы, в проверку «пустая ли
вакансия» и в теги карточки идёт один общий список.

Список отдаётся новый, а не вид на исходные. Разбор уезжает дальше по конвейеру
и живёт до записи в базу; случайная правка у потребителя иначе меняла бы то,
по чему уже посчитана оценка.
"""

from tests.factories import parsed_vacancy


def test_the_two_lists_come_out_as_one():
    """Обязательные и желательные навыки выдаются одним списком."""
    parsed = parsed_vacancy(
        stack_required=["Python", "Docker"], stack_preferred=["Redis"]
    )

    assert parsed.stack == ["Python", "Docker", "Redis"]


def test_the_required_ones_come_first():
    """Обязательные идут первыми: в карточке они и важнее."""
    parsed = parsed_vacancy(stack_required=["Python"], stack_preferred=["Redis"])

    assert parsed.stack[0] == "Python"


def test_a_vacancy_without_skills_yields_an_empty_list():
    """Вакансия без навыков даёт пустой список, а не отсутствие.

    Проверка «пустая ли вакансия» и запись в колонку перебирают его
    как список; отсутствие уронило бы обе.
    """
    assert parsed_vacancy(stack_required=[], stack_preferred=[]).stack == []


def test_changing_the_result_does_not_touch_the_original():
    """Правка выданного списка исходные не меняет.

    Разбор живёт до самой записи в базу, и по исходным спискам уже
    посчитана оценка — сдвинуть их задним числом значило бы рассогласовать
    оценку с тегами.
    """
    parsed = parsed_vacancy(stack_required=["Python"], stack_preferred=["Redis"])

    parsed.stack.append("выдумка")

    assert parsed.stack_required == ["Python"]
    assert parsed.stack_preferred == ["Redis"]
    assert parsed.stack == ["Python", "Redis"]
