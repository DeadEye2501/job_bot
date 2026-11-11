"""Сопроводительные письма профиля: вкладка Letters читает и пишет их через мост."""

from adapters.telegram import CAPTION_LIMIT
from backend.flows.workspaces import switch_workspace
from tests.dbio import put_other_workspace
from tests.factories import OTHER_WORKSPACE_ID

EMPTY = {"ru": None, "ru_short": None, "en": None, "en_short": None}


async def test_a_profile_without_letters_answers_with_four_blanks(api, ask):
    """Вкладка рисуется тем, что пришло: все четыре поля — даже пустыми — и
    предел короткого письма, подпись Telegram."""
    assert (await ask(api.profile.letters))["ok"] == {"letters": EMPTY, "short_max": CAPTION_LIMIT}


async def test_saved_letters_come_back_trimmed_and_blanks_become_absent(api, ask):
    answer = await ask(api.profile.save_letters, {
        "ru": " Здравствуйте! ", "ru_short": "Коротко", "en": "Hello", "en_short": "   ",
    })
    assert answer["ok"] == {}

    letters = (await ask(api.profile.letters))["ok"]["letters"]

    assert letters == {"ru": "Здравствуйте!", "ru_short": "Коротко", "en": "Hello", "en_short": None}


async def test_letters_are_saved_without_a_filled_profile(api, ask):
    """Письма не ждут анкеты: их пишут и до того, как заполнены имя и почта."""
    await ask(api.profile.save_letters, {**EMPTY, "en": "Hello"})

    assert (await ask(api.profile.letters))["ok"]["letters"]["en"] == "Hello"


async def test_a_second_save_replaces_the_letters(api, ask):
    await ask(api.profile.save_letters, {**EMPTY, "ru": "Первое"})
    await ask(api.profile.save_letters, {**EMPTY, "en": "Second"})

    assert (await ask(api.profile.letters))["ok"]["letters"] == {**EMPTY, "en": "Second"}


async def test_letters_belong_to_the_active_profile(api, ask, session_factory):
    await ask(api.profile.save_letters, {**EMPTY, "ru": "Письмо первого профиля"})
    await put_other_workspace(session_factory)

    await switch_workspace(session_factory, OTHER_WORKSPACE_ID)

    assert (await ask(api.profile.letters))["ok"]["letters"] == EMPTY
