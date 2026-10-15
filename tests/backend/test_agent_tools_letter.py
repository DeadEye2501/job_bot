"""Письмо для отклика: пишет приложение или сверяется письмо агента; две отбивки — предел."""

import pytest

from backend.agent.tools_letter import letter_tools
from backend.models import ProfileLanguage
from tests.dbio import put
from tests.factories import profile_row, vacancy_row
from tests.fakes.agent import apply_job, kit_for, tool
from tests.fakes.llm import CHAT, letter_answer, factcheck_answer, messages_of, provider


async def _letter(make_pipeline, session_factory, answers, *, writer="app", language=None):
    vacancy = vacancy_row(title="Инженер", raw_text="Текст вакансии", language=language)
    await put(session_factory, vacancy)
    pipeline = await make_pipeline()
    pipeline.lm_client = provider({CHAT: answers})
    job = apply_job(vacancy.id, letter_writer=writer)
    return job, pipeline.lm_client, tool(letter_tools(kit_for(pipeline), job), "letter")


async def test_the_app_writes_the_letter_with_its_subject(make_pipeline, session_factory):
    job, client, letter = await _letter(
        make_pipeline, session_factory, [letter_answer("Готов работать."), factcheck_answer("ok")]
    )

    answer = await letter()

    assert answer == "Тема: Отклик\n\nПисьмо:\nГотов работать."


@pytest.mark.parametrize(
    ("vacancy_language", "expected"),
    [
        pytest.param("Español", "Español", id="язык вакансии известен"),
        pytest.param(None, "Қазақша", id="неизвестен — язык человека"),
    ],
)
async def test_the_letter_language_is_decided_by_the_app(
    make_pipeline, session_factory, vacancy_language, expected
):
    """Язык письма решает приложение, а не агент: язык вакансии, а неизвестен
    он — родной язык человека."""
    person = profile_row()
    await put(session_factory, person)
    await put(session_factory, ProfileLanguage(profile_id=person.id, language="Қазақша", level="native"))
    job, client, letter = await _letter(
        make_pipeline, session_factory, [letter_answer("Готов работать."), factcheck_answer("ok")],
        language=vacancy_language,
    )

    await letter()

    assert f"Язык письма и темы: {expected}." in messages_of(client.sent[0])["system"]


async def test_a_rejected_app_letter_comes_back_as_remarks(make_pipeline, session_factory):
    job, client, letter = await _letter(
        make_pipeline, session_factory, [letter_answer("Первое."), factcheck_answer("reject", ["выдумано"])]
    )

    answer = await letter()

    assert answer.startswith("письмо не написано") and "выдумано" in answer


async def test_the_agents_own_letter_is_checked(make_pipeline, session_factory):
    job, client, letter = await _letter(
        make_pipeline, session_factory, [factcheck_answer("ok")], writer="agent"
    )

    answer = await letter(subject="Отклик", body="Готов работать.")

    assert answer == "письмо принято"


async def test_a_rejected_agent_letter_comes_back_as_remarks(make_pipeline, session_factory):
    job, client, letter = await _letter(
        make_pipeline, session_factory, [factcheck_answer("reject", ["выдуман стаж"])], writer="agent"
    )

    answer = await letter(subject="Отклик", body="Десять лет опыта.")

    assert "выдуман стаж" in answer


async def test_the_agent_must_bring_its_letter(make_pipeline, session_factory):
    job, client, letter = await _letter(make_pipeline, session_factory, [], writer="agent")

    answer = await letter()

    assert "body" in answer and client.sent == []


async def test_after_two_rejections_the_model_is_not_asked_again(make_pipeline, session_factory):
    rejected = factcheck_answer("reject", ["выдумано"])
    job, client, letter = await _letter(
        make_pipeline, session_factory, [rejected, rejected], writer="agent"
    )
    await letter(subject="S", body="Первое.")
    await letter(subject="S", body="Второе.")

    answer = await letter(subject="S", body="Третье.")

    assert answer.startswith("отбито дважды") and len(client.sent) == 2
