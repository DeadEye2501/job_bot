"""Следствия сбора подсказок для окна добавления в чёрный список.

Окно предлагает выбрать из уже известного, чтобы значение записалось ровно в
том виде, в каком его потом будут искать: набранное руками написание не
совпало бы. У ключевых слов подсказок нет — их вводят свободно.
"""

import pytest

from backend.repository import list_blacklist_candidates
from tests.dbio import put
from tests.factories import channel_row, company_row, hr_row


@pytest.mark.parametrize(
    "kind", ["keyword", "выдумка", ""], ids=["ключевое слово", "неизвестный род", "пусто"]
)
async def test_some_kinds_have_nothing_to_suggest(session, session_factory, kind):
    """У ключевых слов и незнакомых родов подсказок нет."""
    await put(
        session_factory,
        hr_row(telegram_username="maria"),
        company_row(name="Контур"),
        channel_row(username="pyjobs"),
    )

    assert await list_blacklist_candidates(session, kind) == []


async def test_an_hr_without_any_identifier_is_not_suggested(
    session, session_factory
):
    """HR без единого признака в подсказки не идёт — записывать нечего."""
    await put(
        session_factory,
        hr_row(name="С ником", telegram_username="maria", telegram_user_id=None),
        hr_row(name="С номером", telegram_username=None, telegram_user_id=111),
        hr_row(name="Ни с чем", telegram_username=None, telegram_user_id=None),
    )

    got = await list_blacklist_candidates(session, "hr")

    assert [c["label"] for c in got] == ["С ником", "С номером"]


async def test_an_hr_suggestion_shows_the_name_and_hides_the_value_below(
    session, session_factory
):
    """У HR с именем подписью идёт значение, а безымянный назван самим значением."""
    await put(
        session_factory,
        hr_row(name="Мария", telegram_username="maria", telegram_user_id=111),
        hr_row(name=None, telegram_username="olga", telegram_user_id=222),
    )

    got = {c["label"]: c for c in await list_blacklist_candidates(session, "hr")}

    assert got["Мария"] == {"value": "@maria", "label": "Мария", "sub": "@maria"}
    assert got["@olga"] == {"value": "@olga", "label": "@olga", "sub": None}


async def test_hr_suggestions_are_sorted_by_label_ignoring_case(
    session, session_factory
):
    """Подсказки по людям упорядочены по подписи, без учёта регистра.

    Порядок заведения обратен ожидаемому, и регистр разный: сравнение по
    кодам символов поставило бы заглавные впереди строчных.
    """
    await put(
        session_factory,
        hr_row(name="яна", telegram_username="ya"),
        hr_row(name="Борис", telegram_username="bo"),
        hr_row(name="анна", telegram_username="an"),
    )

    got = await list_blacklist_candidates(session, "hr")

    assert [c["label"] for c in got] == ["анна", "Борис", "яна"]


async def test_channel_suggestions_are_sorted_by_label_ignoring_case(
    session, session_factory
):
    """Подсказки по каналам упорядочены по подписи, без учёта регистра.

    Порядок у каналов свой, отдельный от порядка у людей: это два разных
    списка в коде, и проверка одного о втором ничего не говорит. Порядок
    заведения обратен ожидаемому, регистр разный — сравнение по кодам
    символов поставило бы заглавные впереди строчных.
    """
    await put(
        session_factory,
        channel_row(username="ya", title="яндекс"),
        channel_row(username="bo", title="Бэкенд"),
        channel_row(username="an", title="аналитика"),
    )

    got = await list_blacklist_candidates(session, "channel")

    assert [c["label"] for c in got] == ["аналитика", "Бэкенд", "яндекс"]


async def test_every_company_is_suggested_by_its_name(session, session_factory):
    """Компании предлагаются все подряд, значением идёт имя, подписью — сайт."""
    await put(
        session_factory,
        company_row(name="Ромашка", website="https://romashka.ru"),
        company_row(name="Контур", website=None),
    )

    got = await list_blacklist_candidates(session, "company")

    assert got == [
        {"value": "Контур", "label": "Контур", "sub": None},
        {"value": "Ромашка", "label": "Ромашка", "sub": "https://romashka.ru"},
    ]


async def test_a_channel_without_a_username_is_not_suggested(
    session, session_factory
):
    """Канал без ника в подсказки не идёт — записывать нечего."""
    await put(
        session_factory,
        channel_row(username="pyjobs", title="Питон"),
        channel_row(username=None, title="Закрытый"),
    )

    got = await list_blacklist_candidates(session, "channel")

    assert [c["label"] for c in got] == ["Питон"]


async def test_a_channel_suggestion_shows_the_title_and_hides_the_value_below(
    session, session_factory
):
    """У канала с заголовком подписью идёт ник, а безымянный назван ником."""
    await put(
        session_factory,
        channel_row(username="pyjobs", title="Питон"),
        channel_row(username="jsjobs", title=None),
    )

    got = {c["label"]: c for c in await list_blacklist_candidates(session, "channel")}

    assert got["Питон"] == {"value": "@pyjobs", "label": "Питон", "sub": "@pyjobs"}
    assert got["@jsjobs"] == {"value": "@jsjobs", "label": "@jsjobs", "sub": None}
