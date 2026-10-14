"""Работа с набором агента в месте прогона: остановки, которые снимают её целиком."""

from backend.agent.stops import ResumeMissing
from backend.bot import work
from tests.fakes.agent import work_kit


async def test_a_missing_resume_stops_the_work_and_names_the_site(make_bot, monkeypatch):
    bot = await make_bot()
    notes = []
    bot.on_round_note = notes.append
    monkeypatch.setattr(work, "_kit", work_kit)

    async def apply(kit):
        raise ResumeMissing("site.test")

    assert await work.in_slot(bot, apply, "apply") == "resume_missing"
    assert notes == ["Выбранное резюме не найдено на site.test — пересканируйте резюме."]
