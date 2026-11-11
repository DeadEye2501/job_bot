"""Письмо для отклика: пишет приложение или сверяется письмо агента; две отбивки — предел."""

from backend.agent.tools_letter import letter_tools
from tests.dbio import put
from backend.models import CoverLetter
from tests.factories import TEST_WORKSPACE_ID, vacancy_row
from tests.fakes.agent import apply_job, kit_for, tool
from tests.fakes.llm import CHAT, letter_answer, factcheck_answer, messages_of, provider


async def _letter(make_pipeline, session_factory, answers, *, writer="app", language="Русский"):
    vacancy = vacancy_row(title="Инженер", raw_text="Текст вакансии")
    await put(session_factory, vacancy)
    pipeline = await make_pipeline()
    pipeline.lm_client = provider({CHAT: answers})
    job = apply_job(vacancy.id, letter_writer=writer, language=language)
    return job, pipeline.lm_client, tool(letter_tools(kit_for(pipeline), job), "letter")


async def test_the_app_writes_the_letter_with_its_subject(make_pipeline, session_factory):
    job, client, letter = await _letter(
        make_pipeline, session_factory, [letter_answer("Готов работать."), factcheck_answer("ok")]
    )

    answer = await letter()

    assert answer == "Тема: Отклик\n\nПисьмо:\nГотов работать."


async def test_the_letter_is_written_in_the_language_of_the_apply(make_pipeline, session_factory):
    """Язык письма — тот, что решён для отклика один раз и назван агенту
    заданием, а не решаемый инструментом заново."""
    job, client, letter = await _letter(
        make_pipeline, session_factory, [letter_answer("Готов работать."), factcheck_answer("ok")],
        language="Español",
    )

    await letter()

    assert "Язык письма и темы: Español." in messages_of(client.sent[0])["system"]


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


async def _ready(session_factory) -> None:
    await put(session_factory, CoverLetter(workspace_id=TEST_WORKSPACE_ID, app="Полное письмо", app_short="Кратко"))


async def test_a_ready_letter_goes_instead_of_the_apps_one(make_pipeline, session_factory):
    job, client, letter = await _letter(make_pipeline, session_factory, [])
    await _ready(session_factory)

    answer = await letter()

    assert answer.endswith("\nПолное письмо") and client.sent == []


async def test_a_ready_letter_goes_even_when_the_agent_writes_letters(make_pipeline, session_factory):
    job, client, letter = await _letter(make_pipeline, session_factory, [], writer="agent")
    await _ready(session_factory)

    answer = await letter()

    assert answer.endswith("\nПолное письмо") and client.sent == []


async def test_a_field_too_short_for_the_full_letter_gets_the_short_one(make_pipeline, session_factory):
    job, client, letter = await _letter(make_pipeline, session_factory, [])
    await _ready(session_factory)

    answer = await letter(limit=10)

    assert answer.endswith("\nКратко")


async def test_the_agents_own_letter_is_checked_even_with_a_ready_one_at_hand(make_pipeline, session_factory):
    """Принесённое агентом письмо идёт на сверку: готовое под предел поля уже
    не влезло, и отдать его теперь, без предела, значило бы отдать длинное."""
    job, client, letter = await _letter(make_pipeline, session_factory, [factcheck_answer("ok")], writer="agent")
    await _ready(session_factory)

    answer = await letter(subject="Отклик", body="Готов работать.")

    assert answer == "письмо принято"
