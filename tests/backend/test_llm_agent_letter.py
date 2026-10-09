"""Письмо вне Telegram: пишет чат-модель, проверяет сверка фактов."""

from backend.llm.agent_letter import Letter, LetterAsk, check_letter, write_letter
from backend.llm.rules import ATTRIBUTION_RULES, FACT_KINDS, GENDER_RULE
from tests.fakes.llm import CHAT, letter_answer, data_block, factcheck_answer, messages_of, provider


def _ask(**over) -> LetterAsk:
    fields = dict(profile_text="Анкета", title="Заголовок", vacancy_text="Текст",
                  language="английский", limit=None)
    fields.update(over)
    return LetterAsk(**fields)


async def test_a_checked_letter_comes_back_with_its_subject():
    client = provider({CHAT: [letter_answer("Текст письма.", "Тема"), factcheck_answer("ok")]})

    letter, issues = await write_letter(_ask(), client, "m")

    assert letter == Letter("Тема", "Текст письма.") and issues == []


async def test_the_language_and_the_vacancy_reach_the_model():
    client = provider({CHAT: [letter_answer("B.", "Тема"), factcheck_answer("ok")]})

    await write_letter(_ask(language="испанский", vacancy_text="Особый текст"), client, "m")

    assert "испанский" in messages_of(client.sent[0])["system"]
    assert "Особый текст" in data_block(client.sent[0])


async def test_the_writer_hears_what_the_check_holds_against_it():
    """Сочинитель знает тот же перечень фактов, что и сверка, и правило голоса — один раз."""
    client = provider({CHAT: [letter_answer("B.", "Тема"), factcheck_answer("ok")]})

    await write_letter(_ask(), client, "m")

    system = messages_of(client.sent[0])["system"]
    assert FACT_KINDS in system and ATTRIBUTION_RULES in system
    assert system.count(GENDER_RULE) == 1


async def test_a_rejected_letter_comes_back_empty_with_the_reasons():
    """Повтор не здесь: его делает откликатель, позвав letter ещё раз."""
    client = provider({CHAT: [letter_answer("Первое.", "Тема"), factcheck_answer("reject", ["выдумано"])]})

    letter, issues = await write_letter(_ask(), client, "m")

    assert letter is None and issues == ["выдумано"]
    assert len(client.sent) == 2


async def test_a_letter_longer_than_the_field_is_not_checked_at_all():
    client = provider({CHAT: [letter_answer("слово " * 50, "Тема")]})

    letter, issues = await write_letter(_ask(limit=100), client, "m")

    assert letter is None and issues == ["длиннее поля: 299 знаков из 100"]
    assert len(client.sent) == 1


async def test_a_zero_limit_means_no_limit():
    client = provider({CHAT: [letter_answer("слово " * 50, "Тема"), factcheck_answer("ok")]})

    letter, _ = await write_letter(_ask(limit=0), client, "m")

    assert letter is not None


async def test_a_placeholder_in_the_subject_is_not_taken():
    client = provider({CHAT: [letter_answer("Текст.", "Отклик на <название>")]})

    letter, issues = await write_letter(_ask(), client, "m")

    assert letter is None and issues == ["в теме или письме осталась заглушка"]


async def test_a_long_dash_is_turned_into_a_short_one():
    client = provider({CHAT: [letter_answer("Опыт — пять лет.", "Тема"), factcheck_answer("ok")]})

    letter, _ = await write_letter(_ask(), client, "m")

    assert "—" not in letter.body


async def test_a_ready_letter_is_checked_with_its_subject():
    client = provider({CHAT: [factcheck_answer("reject", ["выдумано"])]})

    ok, issues = await check_letter(_ask(), Letter("Тема-X", "Тело-Y"), client, "m")

    assert (ok, issues) == (False, ["выдумано"])
    assert "Тема-X" in data_block(client.sent[0]) and "Тело-Y" in data_block(client.sent[0])


async def test_a_ready_letter_longer_than_the_field_is_refused_without_the_model():
    client = provider({CHAT: []})

    ok, issues = await check_letter(_ask(limit=5), Letter("Т", "Длинное тело"), client, "m")

    assert (ok, issues) == (False, ["длиннее поля: 12 знаков из 5"])
