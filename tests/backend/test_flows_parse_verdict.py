"""Какой приговор получает объявление после разбора.

Порядок отсева выстроен от дешёвого к дорогому. Пустышка — мем, обрывок,
рекламная строчка — отсеивается сразу, до всякой проверки на пригодность: за
неё платить обращением к модели незачем. Дальше идут чёрный список и оценка по
навыкам, и только уцелевшее уходит к проверяльщику.

Проверяльщик, не давший ответа, приравнивается к отказу. Сомнение здесь решается
в пользу бездействия: откликнуться на вакансию, о которой ничего не известно,
хуже, чем не откликнуться.

Удаление разрешено только при обычном сборе. При повторном прогоне тот же
приговор оставляет карточку с пометкой: пользователь просил перечитать
вакансию, а не выбросить её.
"""

from backend.models import TrashEvent, Vacancy, VacancyStatus
from backend.payloads import FitValidation
from tests.dbio import all_rows, only_row


async def test_a_fitting_vacancy_stays_new(parsing, session_factory):
    """Прошедшая всё вакансия остаётся новой и ждёт отклика."""
    pipeline, vacancy = parsing

    await pipeline._parse_and_update_vacancy(vacancy.id, "текст", "jobs")

    saved = await only_row(session_factory, Vacancy)
    assert saved.status is VacancyStatus.NEW
    assert saved.skip_reason is None


async def test_an_empty_post_is_thrown_out_on_ingest(parsing, session_factory):
    """Пустышка при обычном сборе выбрасывается, оставив отметку.

    Мемы и обрывки приходят потоком; держать их в списке вакансий
    значило бы утопить в них настоящие.
    """
    pipeline, vacancy = parsing
    pipeline.parsed = None

    await pipeline._parse_and_update_vacancy(vacancy.id, "текст", "jobs", allow_delete=True)

    assert await all_rows(session_factory, Vacancy) == []
    mark = await only_row(session_factory, TrashEvent)
    assert mark.reason == "empty: no meaningful fields"


async def test_an_empty_post_is_only_marked_on_a_rerun(parsing, session_factory):
    """Пустышка при повторном прогоне остаётся карточкой с пометкой.

    Кнопку нажал пользователь; молча удалить вакансию у него из-под рук
    — не то, о чём он просил.
    """
    pipeline, vacancy = parsing
    pipeline.parsed = None

    await pipeline._parse_and_update_vacancy(vacancy.id, "текст", "jobs", allow_delete=False)

    saved = await only_row(session_factory, Vacancy)
    assert saved.status is VacancyStatus.NOT_FIT
    assert saved.skip_reason == "empty: no meaningful fields"


async def test_an_empty_post_never_reaches_the_validator(parsing):
    """Пустышка до проверки пригодности не доходит.

    Она отсеивается раньше нарочно: платить обращением к модели за мем
    незачем.
    """
    pipeline, vacancy = parsing
    pipeline.parsed = None

    await pipeline._parse_and_update_vacancy(vacancy.id, "текст", "jobs", allow_delete=False)

    assert pipeline.validated is False


async def test_a_blacklisted_post_is_marked_unfit(parsing, session_factory):
    """Объявление, попавшее под чёрный список, помечается непригодным."""
    pipeline, vacancy = parsing
    pipeline._blacklist_patterns = ["казино"]

    await pipeline._parse_and_update_vacancy(
        vacancy.id, "Ищем в казино", "jobs", allow_delete=False
    )

    saved = await only_row(session_factory, Vacancy)
    assert saved.status is VacancyStatus.NOT_FIT
    assert "казино" in (saved.skip_reason or "")


async def test_the_blacklist_reads_the_whole_post(parsing, session_factory):
    """Чёрный список читает весь текст, а не его начало.

    Разбор обрезает объявление под предел модели; образец за обрезкой
    иначе не сработал бы вовсе.
    """
    pipeline, vacancy = parsing
    pipeline._blacklist_patterns = ["казино"]
    long_tail = "а" * 7000 + " казино"

    await pipeline._parse_and_update_vacancy(
        vacancy.id, long_tail, "jobs", allow_delete=False
    )

    assert (await only_row(session_factory, Vacancy)).status is VacancyStatus.NOT_FIT


async def test_a_blacklisted_post_never_reaches_the_validator(parsing):
    """Отсеянное чёрным списком до проверки пригодности не доходит."""
    pipeline, vacancy = parsing
    pipeline._blacklist_patterns = ["казино"]

    await pipeline._parse_and_update_vacancy(
        vacancy.id, "Ищем в казино", "jobs", allow_delete=False
    )

    assert pipeline.validated is False


async def test_a_rejected_vacancy_carries_the_reason(parsing, session_factory):
    """Отклонённая проверяльщиком вакансия несёт его причину.

    Пользователь читает её в карточке и решает, согласен ли; без
    причины отказ выглядит произволом.
    """
    pipeline, vacancy = parsing
    pipeline.verdict = FitValidation(verdict="reject", reason="нужен C++")

    await pipeline._parse_and_update_vacancy(vacancy.id, "текст", "jobs")

    saved = await only_row(session_factory, Vacancy)
    assert saved.status is VacancyStatus.NOT_FIT
    assert saved.skip_reason == "llm: нужен C++"


async def test_a_validator_without_an_answer_means_unfit(parsing, session_factory):
    """Проверяльщик без ответа приравнивается к отказу.

    Модель работает на машине пользователя и отваливается обычным
    делом; откликнуться, ничего не зная о вакансии, хуже, чем нет.
    """
    pipeline, vacancy = parsing
    pipeline.verdict = None

    await pipeline._parse_and_update_vacancy(vacancy.id, "текст", "jobs")

    saved = await only_row(session_factory, Vacancy)
    assert saved.status is VacancyStatus.NOT_FIT
    assert saved.skip_reason == "llm: validation unavailable"


async def test_trash_from_the_validator_is_thrown_out_on_ingest(
    parsing, session_factory
):
    """Признанное мусором при обычном сборе выбрасывается с отметкой."""
    pipeline, vacancy = parsing
    pipeline.verdict = FitValidation(verdict="trash", reason="это реклама курсов")

    await pipeline._parse_and_update_vacancy(vacancy.id, "текст", "jobs", allow_delete=True)

    assert await all_rows(session_factory, Vacancy) == []
    assert (await only_row(session_factory, TrashEvent)).reason == (
        "trash: это реклама курсов"
    )


async def test_trash_from_the_validator_is_only_marked_on_a_rerun(
    parsing, session_factory
):
    """Признанное мусором при повторном прогоне остаётся карточкой."""
    pipeline, vacancy = parsing
    pipeline.verdict = FitValidation(verdict="trash", reason="это реклама курсов")

    await pipeline._parse_and_update_vacancy(
        vacancy.id, "текст", "jobs", allow_delete=False
    )

    saved = await only_row(session_factory, Vacancy)
    assert saved.status is VacancyStatus.NOT_FIT
    assert saved.skip_reason == "trash: это реклама курсов"


async def test_a_low_score_is_not_sent_to_the_validator(parsing, session_factory):
    """Вакансия, не набравшая порога, до проверяльщика не доходит.

    Оценка по навыкам дешёвая и считается на месте; тратить обращение к
    модели на заведомо чужую вакансию незачем.
    """
    pipeline, vacancy = parsing
    await pipeline._rs.set_app("scoring_threshold", "100")

    await pipeline._parse_and_update_vacancy(vacancy.id, "текст", "jobs", allow_delete=False)

    assert pipeline.validated is False
    assert (await only_row(session_factory, Vacancy)).status is VacancyStatus.NOT_FIT
