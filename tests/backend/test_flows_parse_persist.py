"""Что остаётся в базе после разбора объявления.

Разобранные поля, компания и HR записываются в любом случае — даже у
непригодной вакансии. Пользователь смотрит её карточку и решает сам, а ссылки
на компанию и HR должны работать одинаково у любой строки.

Стек и оценка держатся парой. Повторный разбор иногда не вытаскивает навыки
вовсе — модель не всегда одинакова, — и записав пустой стек с нулевой оценкой,
карточка показала бы ноль баллов рядом с прежними тегами. Поэтому пустой
разбор стек не затирает.

Разбор сам не откликается: отклик — дело откликателя, которому отбор передаёт
вакансию после вердикта (`flows/handover`).
"""

import logging
from dataclasses import replace

from backend.flows import parse

from backend.models import HR, Company, Vacancy, VacancyEvent, VacancyStatus
from backend.payloads import FitValidation
from tests.dbio import all_rows, only_row, put
from tests.factories import app_setting_row, company_row, parsed_vacancy


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
    assert saved.location == "Тверь"
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
    assert saved.salary_currency == "$"


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


async def test_the_halves_of_the_stack_reach_the_score_the_right_way_round(
    parsing, session_factory
):
    """Обязательная половина считается строже желательной и после разбора.

    Половины уезжают в подсчёт двумя соседними доводами одного вида, и
    перепутать их местами — правка на два слова. Балл при этом останется
    числом, порог — пройденным, и весь набор — зелёным; узнается подмена
    только по чужим баллам на живых вакансиях. Здесь она видна сразу:
    знакомый навык уровня 3 требованием стоит трёх баллов, пожеланием —
    двух.
    """
    pipeline, vacancy = parsing
    pipeline.parsed = parsed_vacancy(
        title="Python-разработчик",
        description="Ищем в команду",
        stack_required=["Python"],
        stack_preferred=["Rust"],
    )

    await parse.parse_and_update_vacancy(
        pipeline, vacancy.id, "текст", "jobs", allow_delete=False
    )

    saved = await only_row(session_factory, Vacancy)
    assert saved.score == 3


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


async def test_the_company_arbiter_is_asked_with_the_base_left_free(
    parsing, session_factory, monkeypatch
):
    """Пока арбитр компаний думает, база остаётся открытой для записи.

    Ответа модели ждут до трёх минут. Спроси её посреди начатой сделки — и всё
    это время в базу не пишет больше никто: входящее письмо HR, пришедшее в
    этот миг, не запишется вовсе, а человек увидит переписку без него.
    """
    pipeline, vacancy = parsing
    await put(session_factory, company_row(name="Акме Софт"))
    pipeline.parsed = replace(pipeline.parsed, company_name="Акме Софтвер")
    written: list[str] = []

    async def arbiter(client, model, ask):
        async with session_factory() as another:
            another.add(app_setting_row("чужая запись", "пока думает арбитр"))
            await another.commit()
        written.append(ask.parsed_name)
        return None, "не та компания"

    monkeypatch.setattr("backend.llm.company.dedupe_company_with_llm", arbiter)

    await parse.parse_and_update_vacancy(
        pipeline, vacancy.id, "текст", "jobs", allow_delete=False
    )

    assert written == ["Акме Софтвер"]


async def test_a_write_that_failed_is_not_reported_as_a_finished_parse(
    parsing, monkeypatch, caplog
):
    """Провал записи не выдаётся за удавшийся разбор.

    Окно говорит на это «Вакансия разобрана заново», человек закрывает
    карточку — а в базе не изменилось ничего. Тем же ответом отвечает и
    удавшаяся запись вакансии без собеседника, и различить их снаружи нечем.
    """
    pipeline, vacancy = parsing

    async def no_room(*args, **kwargs):
        raise RuntimeError("на диске нет места")

    monkeypatch.setattr("backend.flows.parse_write.add_vacancy_event", no_room)

    with caplog.at_level(logging.ERROR, logger="backend.flows.parse_write"):
        done = await parse.parse_and_update_vacancy(
            pipeline, vacancy.id, "текст", "jobs", allow_delete=False
        )

    assert done.stored is False


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
