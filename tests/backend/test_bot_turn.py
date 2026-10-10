"""Оборот одной задачей: недоразобранное, каналы, агрегаторы — и отклик на наборе этой работы."""

import asyncio

import pytest

from backend.agent.stops import HumanTimeout
from backend.bot import slot, work
from backend.bot.turn import launch_turn
from tests.fakes.agent import work_kit
from tests.waiting import wait_until


@pytest.fixture
def bot_with_turn(make_bot, monkeypatch):
    """Бот, у которого подбор, каналы и агрегаторы пишут своё слово в `order`;
    `channels_hang` вешает каналы, пока их не погасят."""

    async def build(*, channels_hang=False):
        bot = await make_bot()
        order: list[str] = []
        monkeypatch.setattr(work, "_kit", work_kit)

        async def recover():
            order.append("недоразобранные")
            return 0

        async def channels():
            order.append("каналы")
            if channels_hang:
                await asyncio.Event().wait()

        async def seek_all(_bot, kit):
            order.append("агрегаторы")

        bot.ingestion.recover_orphan_vacancies = recover
        bot.ingestion.poll_active_channels = channels
        monkeypatch.setattr("backend.bot.aggregators.seek_all", seek_all)
        return bot, order

    return build


async def test_a_turn_is_one_task_from_channels_to_aggregators(bot_with_turn):
    bot, order = await bot_with_turn()
    task = launch_turn(bot, "turn")
    await task
    assert order == ["недоразобранные", "каналы", "агрегаторы"]
    assert not slot.slot_taken(bot)


async def test_stop_puts_out_the_whole_turn(bot_with_turn):
    bot, order = await bot_with_turn(channels_hang=True)
    task = launch_turn(bot, "turn")
    await wait_until(lambda: "каналы" in order)
    bot.cancel_current_poll()
    await task
    assert "агрегаторы" not in order


async def test_a_busy_slot_launches_no_turn(bot_with_turn, busy_slot):
    bot, order = await bot_with_turn()
    busy_slot(bot)
    assert launch_turn(bot, "turn") is None and order == []


async def test_the_play_button_answers_after_the_whole_turn(bot_with_turn):
    bot, order = await bot_with_turn()
    assert await bot.force_poll_once() == "ok"
    assert order[-1] == "агрегаторы"


@pytest.mark.parametrize(("action", "pipeline_method"), [
    (lambda bot: bot.ui_ingest_pasted_text("текст", None), "ingest_pasted_text"),
    (lambda bot: bot.ui_rerun_vacancy_pipeline(1), "rerun_pipeline_for_vacancy"),
    (lambda bot: bot.poll_channel_now(1), "poll_one_channel"),
])
async def test_a_manual_action_works_with_an_agent_kit(bot_with_turn, action, pipeline_method):
    """Вставка, прогон заново и прогон канала могут дойти до отклика — у них
    тот же набор агента, что у оборота."""
    bot, _ = await bot_with_turn()
    kits = []

    async def look(*_args):
        kits.append(bot.kit)
        return "ok"

    setattr(bot.ingestion, pipeline_method, look)
    assert await action(bot) == "ok"
    assert kits[0] is not None and bot.kit is None


async def test_a_captcha_on_the_channels_is_the_outcome_of_the_play_button(bot_with_turn):
    bot, order = await bot_with_turn()

    async def captcha():
        raise HumanTimeout

    bot.ingestion.poll_active_channels = captcha
    assert await bot.force_poll_once() == "human_timeout"
    assert "агрегаторы" not in order


async def test_a_turn_applies_with_the_kit_of_its_work(bot_with_turn, monkeypatch):
    bot, _ = await bot_with_turn()
    seen = []

    async def applier(kit, ids):
        seen.append((kit, ids))

    monkeypatch.setattr("backend.applying.run.apply_vacancies", applier)

    async def channels():
        await bot.ingestion.apply([7])

    bot.ingestion.poll_active_channels = channels
    await launch_turn(bot, "turn")
    assert seen == [(seen[0][0], [7])] and seen[0][0] is not None
    assert bot.kit is None
