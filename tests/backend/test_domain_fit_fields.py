"""Следствия заслонов по полям-перечислениям: грейд и формат работы.

Обе стороны здесь — перечисления: у вакансии разобранное поле, у кандидата
список принимаемых значений. Сравнить их модель не нужна, а её ответ на таком
сравнении бывает неверным — за это сравнение и забрали у неё.
"""

from backend.domain.fit_fields import grade_refusal, work_format_refusal


def test_a_grade_the_candidate_does_not_take_is_refused_by_its_own_name():
    """Грейд вне списка принимаемых отвергается, и назван требованием вакансии.

    Обоснование говорит о вакансии, а не о кандидате: человек свои грейды
    знает, ему нужно понять, чего требует объявление.
    """
    assert grade_refusal("junior", ["middle", "senior"]) == "Требуется грейд junior."


def test_an_accepted_grade_is_no_blocker():
    """Грейд из списка принимаемых заслона не поднимает."""
    assert grade_refusal("senior", ["middle", "senior"]) is None


def test_a_grade_nobody_limited_is_no_blocker():
    """Пустой список принимаемых грейдов значит «любой годится»."""
    assert grade_refusal("junior", []) is None


def test_a_vacancy_without_a_grade_is_no_blocker():
    """Не названный в объявлении грейд заслона не поднимает.

    Отсутствие грейда — не «неподходящий грейд»: половина постов его не
    называет вовсе, и отсев по молчанию выкосил бы их все.
    """
    assert grade_refusal(None, ["senior"]) is None


def test_a_grade_outside_the_known_list_is_no_blocker():
    """Незнакомое значение грейда заслона не поднимает.

    Разбор мог отдать что угодно, и отказ по неразобранному слову был бы
    отказом по нашей же ошибке.
    """
    assert grade_refusal("intern", ["senior"]) is None


def test_a_work_format_the_candidate_does_not_take_is_named_in_russian():
    """Формат вне списка принимаемых отвергается и назван по-русски.

    Строка едет в окно как есть, и «office» человек читает хуже, чем «офис».
    """
    assert work_format_refusal("office", ["remote"]) == "Формат работы — офис."


def test_an_accepted_work_format_is_no_blocker():
    """Формат из списка принимаемых заслона не поднимает."""
    assert work_format_refusal("remote", ["remote", "hybrid"]) is None


def test_a_vacancy_without_a_work_format_is_no_blocker():
    """Не названный в объявлении формат заслона не поднимает."""
    assert work_format_refusal(None, ["remote"]) is None


def test_a_format_nobody_limited_is_no_blocker():
    """Пустой список принимаемых форматов значит «любой годится»."""
    assert work_format_refusal("office", []) is None
