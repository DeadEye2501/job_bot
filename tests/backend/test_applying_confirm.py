"""Подтверждение отправки у человека: письмо Telegram и почты уходит тем, что
человек оставил в окне, а «Закончить» бросает вакансию без отправки."""

import asyncio
import dataclasses

import pytest

from backend.agent.stops import HumanTimeout
from backend.applying import run
from backend.applying.email import via_email
from backend.applying.result import Dropped
from backend.applying.telegram import via_telegram
from backend.models import Application, Vacancy, VacancyStatus
from tests.backend.fixtures.applying import MAIL, TG
from tests.dbio import all_rows, only_row
from tests.fakes.agent import answering_gate, edited, finished, under_confirmation
from tests.waiting import wait_until

LINK = "https://t.me/jobs/42"


def _silent(payload):
    return None


async def _confirming(kit, answer, *, limit=3600.0):
    """Режим «с подтверждением» и человек у окна; ссылка вакансии — `LINK`."""
    async with kit.pipeline.session_factory() as session:
        for vacancy in await all_rows(kit.pipeline.session_factory, Vacancy):
            (await session.get(Vacancy, vacancy.id)).source_url = LINK
        await session.commit()
    return await under_confirmation(kit, answer, limit)


async def test_a_telegram_letter_goes_and_is_recorded_as_the_person_left_it(telegram_case):
    kit, vacancy, sent = await telegram_case()
    kit, asked = await _confirming(kit, edited({"Текст": "Правленое письмо"}))

    assert await via_telegram(kit, vacancy.id, TG) == "applied"

    ((_, text, _),) = sent
    (row,) = await all_rows(kit.pipeline.session_factory, Application)
    assert text == row.letter == "Правленое письмо"
    ((item,),) = [one["items"] for one in asked]
    assert item["label"] == "Текст" and item["kind"] == "letter" and item["value"] and item["error"] == ""
    # Пустое письмо Telegram не примет: обязательно оно всегда.
    assert item["required"] is True


async def test_the_window_gets_the_link_to_the_vacancy(telegram_case):
    kit, vacancy, _ = await telegram_case()
    kit, asked = await _confirming(kit, edited({}))

    await via_telegram(kit, vacancy.id, TG)

    assert [one["url"] for one in asked] == [LINK]


async def test_finishing_sends_nothing_and_leaves_the_vacancy_new(telegram_case):
    kit, vacancy, sent = await telegram_case()
    kit, _ = await _confirming(kit, finished)

    assert isinstance(await via_telegram(kit, vacancy.id, TG), Dropped)

    assert sent == [] and await all_rows(kit.pipeline.session_factory, Application) == []
    assert (await only_row(kit.pipeline.session_factory, Vacancy)).status is VacancyStatus.NEW


async def test_an_expired_confirmation_drops_the_run_and_sends_nothing(telegram_case):
    kit, vacancy, sent = await telegram_case()
    kit, _ = await _confirming(kit, _silent, limit=0.01)

    with pytest.raises(HumanTimeout):
        await run.apply_chosen(kit, vacancy.id, TG)

    assert sent == []


async def test_a_stop_while_the_letter_waits_sends_nothing(telegram_case):
    kit, vacancy, sent = await telegram_case()
    kit, asked = await _confirming(kit, _silent)
    applying = asyncio.create_task(via_telegram(kit, vacancy.id, TG))
    await wait_until(lambda: asked)

    kit.gate.abort()

    assert isinstance(await asyncio.wait_for(applying, 1), Dropped)
    assert sent == []


async def test_a_mail_goes_with_the_subject_and_body_the_person_left(mail_case):
    kit, vacancy, outbox = await mail_case()
    kit, asked = await _confirming(kit, edited({"Тема": "Новая тема", "Текст": "Новое тело"}))

    assert await via_email(kit, vacancy.id, MAIL) == "applied"

    (mail,) = outbox
    (row,) = await all_rows(kit.pipeline.session_factory, Application)
    assert (mail.subject, mail.body, row.letter) == ("Новая тема", "Новое тело", "Новое тело")
    assert [item["label"] for item in asked[0]["items"]] == ["Тема", "Текст"]


async def test_a_finished_mail_is_not_sent(mail_case):
    kit, vacancy, outbox = await mail_case()
    kit, _ = await _confirming(kit, finished)

    assert isinstance(await via_email(kit, vacancy.id, MAIL), Dropped)
    assert outbox == [] and await all_rows(kit.pipeline.session_factory, Application) == []


async def test_without_mail_settings_the_person_is_not_asked(mail_case):
    """Отправить не с чего — подтверждать нечего: окно не зовётся впустую."""
    kit, vacancy, _ = await mail_case(mail=False)
    kit, asked = await _confirming(kit, finished)

    await via_email(kit, vacancy.id, MAIL)

    assert asked == []


async def test_with_auto_apply_on_nobody_is_asked(telegram_case):
    kit, vacancy, sent = await telegram_case()
    await kit.pipeline.rs.set_app("auto_apply", "true")
    gate, asked = answering_gate(finished)

    assert await via_telegram(dataclasses.replace(kit, gate=gate), vacancy.id, TG) == "applied"

    assert asked == [] and len(sent) == 1
