"""Что остаётся в базе после разбора объявления.

Разобранные поля, компания и HR записываются в любом случае — даже у
непригодной вакансии. Пользователь смотрит её карточку и решает сам, а ссылки
на компанию и HR должны работать одинаково у любой строки.

Стек и оценка держатся парой. Повторный разбор иногда не вытаскивает навыки
вовсе — модель не всегда одинакова, — и записав пустой стек с нулевой оценкой,
карточка показала бы ноль баллов рядом с прежними тегами. Поэтому пустой
разбор стек не затирает.

Отклик уходит сам только у прошедшей всё вакансии и только если пользователь
включил автоотправку. Попытка записывается в ленту в любом случае: иначе,
глядя через месяц на новую вакансию с резолвленным HR, не понять, почему
отклик не ушёл.
"""

import logging
from dataclasses import replace

from backend.flows import parse
from backend.flows import apply
import pytest

from backend.models import HR, Company, Currency, Vacancy, VacancyEvent, VacancyStatus
from backend.payloads import FitValidation
from tests.dbio import all_rows, only_row
from tests.factories import parsed_vacancy


async def test_the_parsed_fields_land_in_the_row(parsing, session_factory):
    """Разобранные поля записываются в строку вакансии."""
    pipeline, vacancy = parsing

    await parse.parse_and_update_vacancy(pipeline, 
        vacancy.id, "текст", "jobs", allow_delete=False
    )

    saved = await only_row(session_factory, Vacancy)
    assert saved.title == "Python-разработчик"
    assert saved.description == "Ищем в команду"
    assert saved.grade == "middle"
    assert saved.salary == "200000"
    assert saved.salary_min == 200000
    assert saved.salary_max == 200000
    assert saved.remote == "remote"
    assert saved.location == "Ереван"
    assert saved.is_parsed is True


async def test_the_currency_of_the_salary_lands_in_the_row(parsing, session_factory):
    """Валюта из строки зарплаты доезжает до базы и читается обратно.

    Колонка перечислением: чужое значение не пустит сама база, а вот
    несовпадение имён перечисления с тем, что в схеме, видно только здесь.
    """
    pipeline, vacancy = parsing
    pipeline.parsed = replace(pipeline.parsed, salary="от 3000 до 5000 $")

    await parse.parse_and_update_vacancy(
        pipeline, vacancy.id, "текст", "jobs", allow_delete=False
    )

    saved = await only_row(session_factory, Vacancy)
    assert (saved.salary_min, saved.salary_max) == (3000, 5000)
    assert saved.salary_currency is Currency.USD


async def test_an_extra_way_to_apply_is_kept_in_the_notes(parsing, session_factory):
    """Не-телеграмный способ отклика сохраняется в заметках.

    Иногда в объявлении вместо контакта дана почта или форма; без этого
    пользователь остался бы с вакансией, на которую нечем ответить.
    """
    pipeline, vacancy = parsing
    pipeline.parsed = parsed_vacancy(
        title="Python-разработчик",
        stack_required=["Python"],
        other_contact="jobs@example.com",
    )

    await parse.parse_and_update_vacancy(pipeline, 
        vacancy.id, "текст", "jobs", allow_delete=False
    )

    assert (await only_row(session_factory, Vacancy)).notes == (
        "Контакты: jobs@example.com"
    )


async def test_a_reparse_without_skills_keeps_the_old_stack(
    parsing, session_factory
):
    """Повторный разбор без навыков прежний стек не затирает.

    Модель не всегда одинакова, и записав пустой стек с нулевой оценкой,
    карточка показала бы ноль баллов рядом с прежними тегами.
    """
    pipeline, vacancy = parsing
    await parse.parse_and_update_vacancy(pipeline, 
        vacancy.id, "текст", "jobs", allow_delete=False
    )
    before = await only_row(session_factory, Vacancy)
    # Разбор без навыков, но не пустышка: два сигнала из пяти есть, и
    # объявление доходит до обычной записи, а не до пути пустышки.
    pipeline.parsed = parsed_vacancy(
        title="Python-разработчик", description="Ищем", salary="200000"
    )

    await parse.parse_and_update_vacancy(pipeline, 
        vacancy.id, "текст", "jobs", allow_delete=False
    )

    saved = await only_row(session_factory, Vacancy)
    assert saved.stack == before.stack
    assert saved.score == before.score


async def test_the_company_is_created_and_linked(parsing, session_factory):
    """Компания заводится и привязывается к вакансии."""
    pipeline, vacancy = parsing
    pipeline.parsed = parsed_vacancy(
        title="Python-разработчик", stack_required=["Python"], company_name="Контур"
    )

    await parse.parse_and_update_vacancy(pipeline, 
        vacancy.id, "текст", "jobs", allow_delete=False
    )

    company = await only_row(session_factory, Company)
    saved = await only_row(session_factory, Vacancy)
    assert saved.company_name == "Контур"
    assert saved.company_id == company.id


async def test_the_hr_is_resolved_and_linked(parsing, session_factory):
    """HR разыскивается в Telegram и привязывается вместе с аватаром."""
    pipeline, vacancy = parsing
    pipeline.parsed = parsed_vacancy(
        title="Python-разработчик", stack_required=["Python"], hr_contact="@maria"
    )

    await parse.parse_and_update_vacancy(pipeline, 
        vacancy.id, "текст", "jobs", allow_delete=False
    )

    hr = await only_row(session_factory, HR)
    assert (await only_row(session_factory, Vacancy)).hr_id == hr.id
    assert hr.avatar == b"\x89PNG"


async def test_an_unfit_vacancy_keeps_its_company_and_hr(parsing, session_factory):
    """Непригодная вакансия компанию и HR всё равно сохраняет.

    Пользователь смотрит её карточку и решает сам; ссылки на компанию и
    HR должны работать одинаково у любой строки.
    """
    pipeline, vacancy = parsing
    pipeline.verdict = FitValidation(verdict="reject", reason="нужен C++")
    pipeline.parsed = parsed_vacancy(
        title="Python-разработчик",
        stack_required=["Python"],
        company_name="Контур",
        hr_contact="@maria",
    )

    await parse.parse_and_update_vacancy(pipeline, 
        vacancy.id, "текст", "jobs", allow_delete=False
    )

    saved = await only_row(session_factory, Vacancy)
    assert saved.status is VacancyStatus.NOT_FIT
    assert saved.company_id is not None
    assert saved.hr_id is not None


async def test_the_timeline_records_what_was_filled(parsing, session_factory):
    """В ленте вакансии записано, что именно удалось заполнить.

    По ней потом видно, чего в объявлении не было, а что не вытащила
    модель.
    """
    pipeline, vacancy = parsing

    await parse.parse_and_update_vacancy(pipeline, 
        vacancy.id, "текст", "jobs", allow_delete=False
    )

    event = next(
        e for e in await all_rows(session_factory, VacancyEvent) if e.kind == "parsed"
    )
    assert event.payload["status"] == VacancyStatus.NEW.value
    assert event.payload["skip_reason"] is None
    assert set(event.payload["fields_filled"]) == {
        "title",
        "description",
        "stack",
        "grade",
        "salary",
        "remote",
        "location",
    }


async def test_a_fitting_vacancy_gets_an_application_sent(parsing, session_factory):
    """Прошедшей всё вакансии отклик уходит сам."""
    pipeline, vacancy = parsing
    pipeline.parsed = parsed_vacancy(
        title="Python-разработчик", stack_required=["Python"], hr_contact="@maria"
    )
    await pipeline.rs.set_app("auto_apply", "true")

    await parse.parse_and_update_vacancy(pipeline, 
        vacancy.id, "текст", "jobs", allow_delete=False
    )

    assert pipeline.asked_to_send == [vacancy.id]


async def test_auto_apply_switched_off_sends_nothing(parsing):
    """С выключенной автоотправкой отклик сам не уходит."""
    pipeline, vacancy = parsing
    pipeline.parsed = parsed_vacancy(
        title="Python-разработчик", stack_required=["Python"], hr_contact="@maria"
    )
    await pipeline.rs.set_app("auto_apply", "false")

    await parse.parse_and_update_vacancy(pipeline, 
        vacancy.id, "текст", "jobs", allow_delete=False
    )

    assert pipeline.asked_to_send == []


async def test_an_unfit_vacancy_gets_no_application(parsing):
    """Непригодной вакансии отклик не уходит даже при включённой автоотправке."""
    pipeline, vacancy = parsing
    pipeline.verdict = FitValidation(verdict="reject", reason="нужен C++")
    pipeline.parsed = parsed_vacancy(
        title="Python-разработчик", stack_required=["Python"], hr_contact="@maria"
    )
    await pipeline.rs.set_app("auto_apply", "true")

    await parse.parse_and_update_vacancy(pipeline, 
        vacancy.id, "текст", "jobs", allow_delete=False
    )

    assert pipeline.asked_to_send == []


async def test_a_vacancy_without_an_hr_gets_no_application(parsing):
    """Вакансии без разысканного HR отклик не уходит: писать некому."""
    pipeline, vacancy = parsing
    await pipeline.rs.set_app("auto_apply", "true")

    await parse.parse_and_update_vacancy(pipeline, 
        vacancy.id, "текст", "jobs", allow_delete=False
    )

    assert pipeline.asked_to_send == []


@pytest.mark.parametrize(
    ("outcome", "reason"),
    [
        pytest.param(True, "sent", id="ушло"),
        pytest.param(False, "cv_missing", id="не ушло"),
    ],
)
async def test_every_attempt_is_recorded_in_the_timeline(monkeypatch, 
    parsing, session_factory, outcome, reason
):
    """Каждая попытка отправки записывается в ленту, чем бы ни кончилась.

    Иначе, глядя через месяц на новую вакансию с разысканным HR,
    пользователь не поймёт, почему отклик так и не ушёл.
    """
    pipeline, vacancy = parsing
    pipeline.parsed = parsed_vacancy(
        title="Python-разработчик", stack_required=["Python"], hr_contact="@maria"
    )
    await pipeline.rs.set_app("auto_apply", "true")

    async def try_auto_send(pipeline, hr, parsed, vacancy_id):
        return outcome, reason

    monkeypatch.setattr(apply, "try_auto_send", try_auto_send)

    await parse.parse_and_update_vacancy(pipeline, 
        vacancy.id, "текст", "jobs", allow_delete=False
    )

    event = next(
        e
        for e in await all_rows(session_factory, VacancyEvent)
        if e.kind == "auto_send"
    )
    assert event.payload == {"ok": outcome, "reason": reason}


async def test_a_vanished_vacancy_is_left_alone(parsing, session_factory, caplog):
    """По исчезнувшей вакансии ничего не записывается — и не через поломку.

    Пользователь мог удалить её из окна, пока шёл разбор. Пустая лента одна
    охрану не стережёт: сними `if v is None`, и следующая строка бросит на
    `None`, широкий перехват отчитается тем же ответом, а строк не появится
    и в этом случае. Различает две дороги только журнал.
    """
    pipeline, _ = parsing

    with caplog.at_level(logging.ERROR, logger="backend.flows.parse_write"):
        await parse.parse_and_update_vacancy(
            pipeline, 404, "текст", "jobs", allow_delete=False
        )

    assert await all_rows(session_factory, VacancyEvent) == []
    assert [r for r in caplog.records if r.name == "backend.flows.parse_write"] == []


async def test_the_window_hears_about_both_lists(parsing):
    """Окно узнаёт и о вакансиях, и о контактах."""
    pipeline, vacancy = parsing
    heard: list[str] = []
    pipeline.on_contacts_changed = lambda: heard.append("контакты")
    pipeline.on_vacancies_changed = lambda: heard.append("вакансии")

    await parse.parse_and_update_vacancy(pipeline, 
        vacancy.id, "текст", "jobs", allow_delete=False
    )

    assert heard == ["контакты", "вакансии"]
