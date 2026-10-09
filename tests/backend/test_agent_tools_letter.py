"""Письмо для отклика: пишет приложение или сверяется письмо агента; две отбивки — предел."""

from backend.agent.tools_letter import letter_tools
from tests.dbio import put
from tests.factories import vacancy_row
from tests.fakes.agent import apply_job, kit_for, tool
from tests.fakes.llm import CHAT, chat_json, factcheck_answer, provider


def _written(body: str, subject: str = "Отклик"):
    return chat_json({"subject": subject, "body": body})


async def _letter(make_pipeline, session_factory, answers, *, writer="app"):
    vacancy = vacancy_row(title="Инженер", raw_text="Текст вакансии")
    await put(session_factory, vacancy)
    pipeline = await make_pipeline()
    pipeline.lm_client = provider({CHAT: answers})
    job = apply_job(vacancy.id, letter_writer=writer)
    return job, pipeline.lm_client, tool(letter_tools(kit_for(pipeline), job), "letter")


async def test_the_app_writes_the_letter_with_its_subject(make_pipeline, session_factory):
    job, client, letter = await _letter(
        make_pipeline, session_factory, [_written("Готов работать."), factcheck_answer("ok")]
    )

    answer = await letter(language="русский")

    assert answer == "Тема: Отклик\n\nПисьмо:\nГотов работать."


async def test_a_rejected_app_letter_comes_back_as_remarks(make_pipeline, session_factory):
    job, client, letter = await _letter(
        make_pipeline, session_factory, [_written("Первое."), factcheck_answer("reject", ["выдумано"])]
    )

    answer = await letter(language="русский")

    assert answer.startswith("письмо не написано") and "выдумано" in answer


async def test_the_agents_own_letter_is_checked(make_pipeline, session_factory):
    job, client, letter = await _letter(
        make_pipeline, session_factory, [factcheck_answer("ok")], writer="agent"
    )

    answer = await letter(language="русский", subject="Отклик", body="Готов работать.")

    assert answer == "письмо принято"


async def test_a_rejected_agent_letter_comes_back_as_remarks(make_pipeline, session_factory):
    job, client, letter = await _letter(
        make_pipeline, session_factory, [factcheck_answer("reject", ["выдуман стаж"])], writer="agent"
    )

    answer = await letter(language="русский", subject="Отклик", body="Десять лет опыта.")

    assert "выдуман стаж" in answer


async def test_the_agent_must_bring_its_letter(make_pipeline, session_factory):
    job, client, letter = await _letter(make_pipeline, session_factory, [], writer="agent")

    answer = await letter(language="русский")

    assert "body" in answer and client.sent == []


async def test_after_two_rejections_the_model_is_not_asked_again(make_pipeline, session_factory):
    rejected = factcheck_answer("reject", ["выдумано"])
    job, client, letter = await _letter(
        make_pipeline, session_factory, [rejected, rejected], writer="agent"
    )
    await letter(language="русский", subject="S", body="Первое.")
    await letter(language="русский", subject="S", body="Второе.")

    answer = await letter(language="русский", subject="S", body="Третье.")

    assert answer.startswith("отбито дважды") and len(client.sent) == 2
