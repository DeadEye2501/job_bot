"""Откликатель пишет отклик только на свою вакансию и только своим способом."""

from backend.agent.jobs import Applied, ApplyJob
from backend.agent.tools_applier import applier_tools
from backend.models import Application, Screening
from tests.dbio import all_rows, put
from tests.factories import vacancy_row
from tests.fakes.agent import apply_job, kit_for, tool


def _job(vacancy_id, **over) -> ApplyJob:
    """Отклик кнопкой агрегатора — способ, о котором большинство проверок этого файла."""
    return apply_job(vacancy_id, **{"method": "aggregator", "target": "https://site.test/vacancy/1", **over})


async def test_a_recorded_application_ends_the_session(make_pipeline, session_factory):
    vacancy = vacancy_row()
    await put(session_factory, vacancy)
    job = _job(vacancy.id)

    await tool(applier_tools(kit_for(await make_pipeline()), job), "record_application")(
        via="aggregator", target="https://site.test/vacancy/1",
        screening=[{"from_us": False, "text": "В"}, {"from_us": True, "text": "О"}],
    )

    (row,) = await all_rows(session_factory, Application)
    assert job.outcome == Applied(row.id)


async def test_a_form_way_cannot_be_recorded_as_the_aggregator(make_pipeline, session_factory):
    vacancy = vacancy_row()
    await put(session_factory, vacancy)
    job = _job(vacancy.id, method="form", target="https://company.test/apply")

    answer = await tool(applier_tools(kit_for(await make_pipeline()), job), "record_application")(
        via="aggregator", target="https://site.test/vacancy/1"
    )

    assert job.outcome is None and "не пишется" in answer
    assert await all_rows(session_factory, Application) == []


async def test_the_form_way_records_a_form_application(make_pipeline, session_factory):
    vacancy = vacancy_row()
    await put(session_factory, vacancy)
    job = _job(vacancy.id, method="form", target="https://company.test/apply")

    await tool(applier_tools(kit_for(await make_pipeline()), job), "record_application")(
        via="form", target="https://company.test/apply", letter="Письмо"
    )

    (row,) = await all_rows(session_factory, Application)
    assert (row.via.value, row.letter) == ("form", "Письмо")
    assert job.outcome == Applied(row.id)


async def test_an_aggregator_button_that_led_to_a_form_is_recorded_as_a_form(
    make_pipeline, session_factory
):
    vacancy = vacancy_row()
    await put(session_factory, vacancy)
    job = _job(vacancy.id, aggregator_id=None)

    await tool(applier_tools(kit_for(await make_pipeline()), job), "record_application")(
        via="form", target="https://company.test/apply"
    )

    (row,) = await all_rows(session_factory, Application)
    assert (row.via.value, row.target) == ("form", "https://company.test/apply")


async def test_already_applied_is_recorded_without_a_letter(make_pipeline, session_factory):
    vacancy = vacancy_row()
    await put(session_factory, vacancy)
    job = _job(vacancy.id)

    await tool(applier_tools(kit_for(await make_pipeline()), job), "record_application")(
        via="aggregator", target="https://site.test/vacancy/1", letter="лишнее",
        already_applied=True,
    )

    (row,) = await all_rows(session_factory, Application)
    assert row.letter is None


async def test_questions_after_the_record_join_the_same_application(make_pipeline, session_factory):
    """Страница подтверждения бывает с другим адресом — её вопросы ложатся в тот же отклик."""
    vacancy = vacancy_row()
    await put(session_factory, vacancy)
    job = _job(vacancy.id)
    record = tool(applier_tools(kit_for(await make_pipeline()), job), "record_application")
    await record(via="aggregator", target="https://site.test/vacancy/1",
                 screening=[{"from_us": False, "text": "Опыт?"}])

    await record(via="aggregator", target="https://site.test/vacancy/1/done",
                 screening=[{"from_us": False, "text": "Город?"}])

    assert len(await all_rows(session_factory, Application)) == 1
    assert [s.text for s in await all_rows(session_factory, Screening)] == ["Опыт?", "Город?"]


async def test_the_vacancy_tool_describes_its_own_vacancy(make_pipeline, session_factory):
    vacancy = vacancy_row(company_name="Компания-Б")
    await put(session_factory, vacancy)

    brief = await tool(applier_tools(kit_for(await make_pipeline()), _job(vacancy.id)), "vacancy")()

    assert "Компания-Б" in brief
