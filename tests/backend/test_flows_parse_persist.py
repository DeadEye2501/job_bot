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

import pytest

from backend.models import (
    HR,
    Company,
    Profile,
    Vacancy,
    VacancyEvent,
    VacancyStatus,
)
from backend.payloads import FitValidation
from tests.dbio import all_rows, only_row, put
from tests.factories import parsed_vacancy, profile_row, profile_skill_row, vacancy_row
from tests.fakes.telegram import FakeTelegramClient, photo, user


@pytest.fixture
async def parsing(make_pipeline, session_factory, monkeypatch):
    """Конвейер с подставным разбором, готовый писать в базу."""
    await put(session_factory, vacancy_row(title=None, is_parsed=False, raw_text="текст"))
    vacancy = await only_row(session_factory, Vacancy)

    client = FakeTelegramClient(
        users={
            "maria": user(
                id=777,
                username="maria",
                first_name="Мария",
                photo=photo(small_file_id="кар"),
            )
        },
        avatar=b"\x89PNG",
    )
    pipeline = await make_pipeline(client)
    pipeline.parsed = parsed_vacancy(
        title="Python-разработчик",
        description="Ищем в команду",
        stack_required=["Python"],
        grade="middle",
        salary="200000",
        remote="remote",
        location="Ереван",
    )
    pipeline.verdict = FitValidation(verdict="fit", reason=None)

    async def parse_vacancy(text, client_, model, **kwargs):
        return pipeline.parsed

    async def validate_vacancy_fit(parsed, text, client_, model, **kwargs):
        return pipeline.verdict

    await put(session_factory, profile_row())
    profile = await only_row(session_factory, Profile)
    await put(session_factory, profile_skill_row(profile.id, "Python"))
    await pipeline._reload_resources()
    await pipeline._rs.set_app("scoring_threshold", "1")

    # Отправка подменена по умолчанию: предмет файла — что легло в базу, а
    # настоящая ушла бы сочинять письмо в языковую модель.
    pipeline.sent_for = []

    async def try_auto_send(hr, parsed, vacancy_id):
        pipeline.sent_for.append(vacancy_id)
        return True, "sent"

    pipeline._try_auto_send = try_auto_send

    monkeypatch.setattr("backend.flows.parse_vacancy", parse_vacancy)
    monkeypatch.setattr("backend.flows.validate_vacancy_fit", validate_vacancy_fit)
    return pipeline, vacancy


async def test_the_parsed_fields_land_in_the_row(parsing, session_factory):
    """Разобранные поля записываются в строку вакансии."""
    pipeline, vacancy = parsing

    await pipeline._parse_and_update_vacancy(
        vacancy.id, "текст", "jobs", allow_delete=False
    )

    saved = await only_row(session_factory, Vacancy)
    assert saved.title == "Python-разработчик"
    assert saved.description == "Ищем в команду"
    assert saved.grade == "middle"
    assert saved.salary == "200000"
    assert saved.remote == "remote"
    assert saved.location == "Ереван"
    assert saved.is_parsed is True


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

    await pipeline._parse_and_update_vacancy(
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
    await pipeline._parse_and_update_vacancy(
        vacancy.id, "текст", "jobs", allow_delete=False
    )
    before = await only_row(session_factory, Vacancy)
    # Разбор без навыков, но не пустышка: два сигнала из пяти есть, и
    # объявление доходит до обычной записи, а не до пути пустышки.
    pipeline.parsed = parsed_vacancy(
        title="Python-разработчик", description="Ищем", salary="200000"
    )

    await pipeline._parse_and_update_vacancy(
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

    await pipeline._parse_and_update_vacancy(
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

    await pipeline._parse_and_update_vacancy(
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

    await pipeline._parse_and_update_vacancy(
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

    await pipeline._parse_and_update_vacancy(
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
    await pipeline._rs.set_app("auto_apply", "true")

    await pipeline._parse_and_update_vacancy(
        vacancy.id, "текст", "jobs", allow_delete=False
    )

    assert pipeline.sent_for == [vacancy.id]


async def test_auto_apply_switched_off_sends_nothing(parsing):
    """С выключенной автоотправкой отклик сам не уходит."""
    pipeline, vacancy = parsing
    pipeline.parsed = parsed_vacancy(
        title="Python-разработчик", stack_required=["Python"], hr_contact="@maria"
    )
    await pipeline._rs.set_app("auto_apply", "false")

    await pipeline._parse_and_update_vacancy(
        vacancy.id, "текст", "jobs", allow_delete=False
    )

    assert pipeline.sent_for == []


async def test_an_unfit_vacancy_gets_no_application(parsing):
    """Непригодной вакансии отклик не уходит даже при включённой автоотправке."""
    pipeline, vacancy = parsing
    pipeline.verdict = FitValidation(verdict="reject", reason="нужен C++")
    pipeline.parsed = parsed_vacancy(
        title="Python-разработчик", stack_required=["Python"], hr_contact="@maria"
    )
    await pipeline._rs.set_app("auto_apply", "true")

    await pipeline._parse_and_update_vacancy(
        vacancy.id, "текст", "jobs", allow_delete=False
    )

    assert pipeline.sent_for == []


async def test_a_vacancy_without_an_hr_gets_no_application(parsing):
    """Вакансии без разысканного HR отклик не уходит: писать некому."""
    pipeline, vacancy = parsing
    await pipeline._rs.set_app("auto_apply", "true")

    await pipeline._parse_and_update_vacancy(
        vacancy.id, "текст", "jobs", allow_delete=False
    )

    assert pipeline.sent_for == []


@pytest.mark.parametrize(
    ("outcome", "reason"),
    [
        pytest.param(True, "sent", id="ушло"),
        pytest.param(False, "cv_missing", id="не ушло"),
    ],
)
async def test_every_attempt_is_recorded_in_the_timeline(
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
    await pipeline._rs.set_app("auto_apply", "true")

    async def try_auto_send(hr, parsed, vacancy_id):
        return outcome, reason

    pipeline._try_auto_send = try_auto_send

    await pipeline._parse_and_update_vacancy(
        vacancy.id, "текст", "jobs", allow_delete=False
    )

    event = next(
        e
        for e in await all_rows(session_factory, VacancyEvent)
        if e.kind == "auto_send"
    )
    assert event.payload == {"ok": outcome, "reason": reason}


async def test_a_vanished_vacancy_is_left_alone(parsing, session_factory):
    """По исчезнувшей вакансии ничего не записывается и не падает.

    Пользователь мог удалить её из окна, пока шёл разбор.
    """
    pipeline, _ = parsing

    await pipeline._parse_and_update_vacancy(
        404, "текст", "jobs", allow_delete=False
    )

    assert await all_rows(session_factory, VacancyEvent) == []


async def test_the_window_hears_about_both_lists(parsing):
    """Окно узнаёт и о вакансиях, и о контактах."""
    pipeline, vacancy = parsing
    heard: list[str] = []
    pipeline.on_contacts_changed = lambda: heard.append("контакты")
    pipeline.on_vacancies_changed = lambda: heard.append("вакансии")

    await pipeline._parse_and_update_vacancy(
        vacancy.id, "текст", "jobs", allow_delete=False
    )

    assert heard == ["контакты", "вакансии"]
