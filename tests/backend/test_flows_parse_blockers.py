"""Порядок заслонов пригодности: сперва бесплатные, потом платные.

Грейд и формат работы решает код: обе стороны названы перечислениями, и
сравнивать их модели незачем. Стоят они перед зовами к модели, потому что
первый отказ прекращает остальные проверки, а зов стоит времени и токенов.

Смысловое остаётся модели и разведено по отдельным зовам — роль, языки,
место, предпочтения. Зов не может ошибиться о том, чего ему не давали: слитые в
один, шесть критериев путались между собой.
"""

from dataclasses import replace

from backend.flows import parse
from backend.llm.candidate import CandidateProfile
from backend.models import Vacancy, VacancyStatus
from backend.payloads import FitValidation
from tests.dbio import only_row


async def test_a_grade_the_candidate_does_not_take_is_refused_without_the_model(
    parsing, session_factory
):
    """Неподходящий грейд отвергает код, не спрашивая модель вовсе.

    Сравнение здесь механическое, а зов к модели стоит времени: на канале в
    полтысячи постов лишний зов на каждом — это часы.
    """
    pipeline, vacancy = parsing
    pipeline.profile_cache = CandidateProfile(grades=["senior"])
    pipeline.parsed = replace(pipeline.parsed, grade="junior")

    await parse.parse_and_update_vacancy(pipeline, vacancy.id, "текст", "jobs")

    saved = await only_row(session_factory, Vacancy)
    assert saved.status is VacancyStatus.NOT_FIT
    assert saved.skip_reason == "Требуется грейд junior."
    assert pipeline.fit_asked == []


async def test_a_work_format_the_candidate_does_not_take_is_refused_without_the_model(
    parsing, session_factory
):
    """Неподходящий формат работы отвергает код — тем же правилом, что грейд."""
    pipeline, vacancy = parsing
    pipeline.profile_cache = CandidateProfile(work_formats=["remote"])
    pipeline.parsed = replace(pipeline.parsed, remote="office")

    await parse.parse_and_update_vacancy(pipeline, vacancy.id, "текст", "jobs")

    saved = await only_row(session_factory, Vacancy)
    assert saved.status is VacancyStatus.NOT_FIT
    assert saved.skip_reason == "Формат работы — офис."
    assert pipeline.fit_asked == []


async def test_the_office_in_the_candidates_own_city_is_no_blocker(
    parsing, session_factory
):
    """Офис в городе кандидата вакансию не отвергает.

    Локация перестала быть отдельным критерием: сама по себе она не значит
    ничего, пока формат работы человека устраивает. Прежде вакансия «гибрид,
    офис в городе кандидата» получала отказ по локации — при кандидате,
    который в этом городе и живёт.
    """
    pipeline, vacancy = parsing
    pipeline.profile_cache = CandidateProfile(
        location="Тверская область/Тверь", work_formats=["remote", "hybrid"]
    )
    pipeline.parsed = replace(
        pipeline.parsed, remote="hybrid", location="Тверская область/Тверь"
    )

    await parse.parse_and_update_vacancy(pipeline, vacancy.id, "текст", "jobs")

    saved = await only_row(session_factory, Vacancy)
    assert saved.status is VacancyStatus.NEW
    assert saved.skip_reason is None


async def test_a_vacancy_is_not_deleted_by_a_verdict_nobody_asked_for(
    parsing, session_factory
):
    """Ответ «мусор» от зова о пригодности вакансию не удаляет.

    Жанр поста решён раньше и отдельным зовом: он сказал «вакансия». Ответь
    после этого зов о роли «мусор» — прежде строка была бы удалена при
    обычном сборе, то есть пост исчез бы по слову того, кого о жанре не
    спрашивали, и вернуть его нечем: курсор канала ушёл вперёд.
    """
    pipeline, vacancy = parsing
    pipeline.verdict_by["роль"] = FitValidation(
        verdict="trash", reason="это реклама курсов"
    )

    await parse.parse_and_update_vacancy(
        pipeline, vacancy.id, "текст", "jobs", allow_delete=True
    )

    saved = await only_row(session_factory, Vacancy)
    assert saved.status is VacancyStatus.NOT_FIT
    assert saved.skip_reason == "llm: это реклама курсов"


async def test_every_fit_question_is_asked_when_nothing_blocks(parsing):
    """Прошедшую вакансию спрашивают обо всём: роль, языки, место, предпочтения."""
    pipeline, vacancy = parsing

    await parse.parse_and_update_vacancy(pipeline, vacancy.id, "текст", "jobs")

    assert pipeline.fit_asked == ["роль", "языки", "место", "предпочтения"]


async def test_a_refusal_from_the_second_question_stops_the_third(
    parsing, session_factory
):
    """Отказ второго зова прекращает третий, а не проходит мимо.

    Прекращает остальные именно отказ, а не порядковый номер зова: без этой
    проверки цепочка, обрывающаяся только на первом, выглядела бы такой же
    зелёной.
    """
    pipeline, vacancy = parsing
    pipeline.verdict_by["языки"] = FitValidation(
        verdict="reject", reason="Требуется немецкий язык на уровне C1."
    )

    await parse.parse_and_update_vacancy(pipeline, vacancy.id, "текст", "jobs")

    assert pipeline.fit_asked == ["роль", "языки"]
    saved = await only_row(session_factory, Vacancy)
    assert saved.skip_reason == "llm: Требуется немецкий язык на уровне C1."


async def test_the_first_refusal_stops_the_questions_that_follow(
    parsing, session_factory
):
    """Отказ первого зова прекращает остальные: платить за них уже незачем."""
    pipeline, vacancy = parsing
    pipeline.verdict = FitValidation(
        verdict="reject", reason="Основная роль вакансии — SMM-менеджер."
    )

    await parse.parse_and_update_vacancy(pipeline, vacancy.id, "текст", "jobs")

    assert pipeline.fit_asked == ["роль"]
    saved = await only_row(session_factory, Vacancy)
    assert saved.skip_reason == "llm: Основная роль вакансии — SMM-менеджер."
