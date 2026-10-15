"""Заполнение резюме: агент заполняет, следом — перечень резюме и отметка заполненного."""

import logging

import pytest

from backend.agent.jobs import Source
from backend.flows.resume_fill import fill
from backend.models import Aggregator, ProfileLanguage
from tests.dbio import only_row, put, resume_marks
from tests.factories import profile_row
from tests.factories_aggregators import aggregator_resume_row, aggregator_row
from tests.fakes.agent import finish_step, resumes_step, scripted_kit

FIRST = "https://hh.ru/resume/1"
SECOND = "https://hh.ru/resume/2"
THIRD = "https://hh.ru/resume/3"
FOURTH = "https://hh.ru/resume/4"
FIRST_EDITOR = "https://hh.ru/resume/1/edit"


async def _site(session_factory):
    site = aggregator_row(is_logged_in=True, can_add_resume=True)
    await put(session_factory, site)
    first = aggregator_resume_row(site.id, title="Швея", url=FIRST, editor_url=FIRST_EDITOR)
    await put(session_factory, first,
              aggregator_resume_row(site.id, title="Повар", url=SECOND, editor_url=SECOND + "/edit",
                                    position=1, is_chosen=True))
    return site, first


async def _marks(session_factory, aggregator_id):
    return dict(await resume_marks(session_factory, aggregator_id))


async def test_an_overwritten_resume_is_scanned_and_becomes_the_chosen_one(
    make_pipeline, session_factory
):
    site, first = await _site(session_factory)
    kit = scripted_kit(await make_pipeline(), [
        finish_step(), resumes_step([("Швея-закройщица", FIRST), ("Повар", SECOND)]),
    ])

    assert await fill(kit, Source.of(site), first.id) == "ok"

    assert await _marks(session_factory, site.id) == {"Швея-закройщица": True, "Повар": False}


async def test_a_created_resume_is_found_by_its_new_link_and_chosen(make_pipeline, session_factory):
    site, _ = await _site(session_factory)
    kit = scripted_kit(await make_pipeline(), [
        finish_step(),
        resumes_step([("Швея", FIRST), ("Повар", SECOND), ("Кондитер", "https://hh.ru/resume/3")]),
    ])

    assert await fill(kit, Source.of(site), None) == "ok"

    assert await _marks(session_factory, site.id) == {"Швея": False, "Повар": False, "Кондитер": True}


async def test_missing_required_data_leaves_the_mark_and_skips_the_scan(
    make_pipeline, session_factory
):
    site, first = await _site(session_factory)

    async def missing(tools):
        await tools["report_required_missing"](labels=["Гражданство"])

    kit = scripted_kit(await make_pipeline(), [missing])

    assert await fill(kit, Source.of(site), first.id) == "required_missing"

    assert await _marks(session_factory, site.id) == {"Швея": False, "Повар": True}
    assert len(kit.run_session.plans) == 1


async def test_a_fill_the_agent_could_not_finish_marks_nothing_and_says_so(
    make_pipeline, session_factory
):
    """Застрявший агент говорит «не вышло», а не «готово»: окно не покажет
    «Резюме заполнено» на полузаполненном резюме, отметка не сдвинется."""
    site, first = await _site(session_factory)
    kit = scripted_kit(await make_pipeline(), [finish_step("failed")])

    assert await fill(kit, Source.of(site), first.id) == "error"

    assert await _marks(session_factory, site.id) == {"Швея": False, "Повар": True}
    assert len(kit.run_session.plans) == 1


async def test_the_fill_leaves_a_short_summary_in_the_log(make_pipeline, session_factory, caplog):
    site, first = await _site(session_factory)
    kit = scripted_kit(await make_pipeline(), [finish_step(), resumes_step([("Швея", FIRST)])])

    with caplog.at_level(logging.INFO):
        await fill(kit, Source.of(site), first.id)

    assert any("страниц" in record.getMessage() for record in caplog.records)


async def test_the_fill_works_in_the_profile_of_its_site_able_to_save(make_pipeline, session_factory):
    site, first = await _site(session_factory)
    seen = []

    async def filling(tools):
        seen.append((kit.browser.calls[-1], kit.browser.sending))
        await tools["finish"](result="done")

    kit = scripted_kit(await make_pipeline(), [filling, resumes_step([("Швея", FIRST)])])

    await fill(kit, Source.of(site), first.id)

    assert seen == [(("profile", site.id), True)]
    assert FIRST_EDITOR in kit.run_session.plans[0].task


async def test_the_resume_is_written_in_the_language_of_the_person(make_pipeline, session_factory):
    """Резюме пишется на языке человека — первом родном из анкеты, — а не на
    языке сайта."""
    site, first = await _site(session_factory)
    person = profile_row()
    await put(session_factory, person)
    await put(session_factory,
              ProfileLanguage(profile_id=person.id, language="Английский", level="C1"),
              ProfileLanguage(profile_id=person.id, language="Армянский", level="native"))
    kit = scripted_kit(await make_pipeline(), [finish_step(), resumes_step([("Швея", FIRST)])])

    await fill(kit, Source.of(site), first.id)

    assert "Армянский" in kit.run_session.plans[0].task


async def test_a_resume_relinked_by_the_overwrite_is_found_as_the_only_new_link(
    make_pipeline, session_factory
):
    site, first = await _site(session_factory)
    kit = scripted_kit(await make_pipeline(), [
        finish_step(), resumes_step([("Швея", "https://hh.ru/resume/9"), ("Повар", SECOND)]),
    ])

    assert await fill(kit, Source.of(site), first.id) == "ok"

    assert await _marks(session_factory, site.id) == {"Швея": True, "Повар": False}


@pytest.mark.parametrize(
    ("overwrite", "after", "outcome"),
    [
        pytest.param(True, [("Швея", FIRST), ("Повар", SECOND), ("Кондитер", THIRD)], "extra_resume",
                     id="перезапись завела новое"),
        pytest.param(True, [("Повар", SECOND)], "resume_lost", id="перезаписанное пропало без замены"),
        pytest.param(False, [("Швея", FIRST), ("Повар", SECOND)], "not_created", id="новое не появилось"),
        pytest.param(False, [("Швея", FIRST), ("Повар", SECOND), ("Кондитер", THIRD), ("Пекарь", FOURTH)],
                     "many_created", id="новых два"),
    ],
)
async def test_a_list_that_does_not_match_the_button_is_an_error_and_marks_nothing(
    make_pipeline, session_factory, overwrite, after, outcome
):
    """Список после работы не сошёлся с нажатым — ошибка, и отметка остаётся
    у прежнего резюме: откликаться не тем хуже, чем не откликаться."""
    site, first = await _site(session_factory)
    kit = scripted_kit(await make_pipeline(), [finish_step(), resumes_step(after)])

    assert await fill(kit, Source.of(site), first.id if overwrite else None) == outcome

    assert {title for title, chosen in (await resume_marks(session_factory, site.id)) if chosen} == {"Повар"}


async def test_overwriting_a_resume_without_its_editor_is_refused_before_the_agent(
    make_pipeline, session_factory
):
    """Без адреса правки агенту пришлось бы искать её по сайту — так он и
    приходил к созданию нового резюме вместо правки."""
    site = aggregator_row(is_logged_in=True)
    await put(session_factory, site)
    bare = aggregator_resume_row(site.id, title="Швея", url=FIRST)
    await put(session_factory, bare)
    kit = scripted_kit(await make_pipeline(), [])

    assert await fill(kit, Source.of(site), bare.id) == "no_editor"
    assert kit.run_session.plans == []


async def test_a_creation_the_site_refuses_marks_the_site_and_scans_nothing(
    make_pipeline, session_factory
):
    site, _ = await _site(session_factory)

    async def impossible(tools):
        await tools["report_no_new_resume"](reason="одно резюме на аккаунт")
        await tools["finish"](result="done")

    kit = scripted_kit(await make_pipeline(), [impossible])

    assert await fill(kit, Source.of(site), None) == "no_new_resume"
    assert (await only_row(session_factory, Aggregator)).can_add_resume is False
    assert len(kit.run_session.plans) == 1


async def test_overwriting_a_resume_the_site_does_not_have_is_refused_before_the_agent(
    make_pipeline, session_factory
):
    site, _ = await _site(session_factory)
    kit = scripted_kit(await make_pipeline(), [])

    assert await fill(kit, Source.of(site), 999) == "no_resume"
    assert kit.run_session.plans == []
