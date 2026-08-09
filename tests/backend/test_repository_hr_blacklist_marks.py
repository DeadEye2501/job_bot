"""Следствия сопоставления HR со строками чёрного списка.

Одного человека в списке можно записать двумя способами — ником или
идентификатором Telegram, — и написание выбирают в момент добавления, когда
известно не всё. Поэтому поиск проверяет оба, а кнопка «добавить» пишет одно.
"""

from backend.repository.hr_card import get_hr_detail, hr_blacklist_candidates, hr_blacklist_preferred_value
from tests.dbio import put
from tests.factories import blacklist_row, hr_row


def test_both_spellings_are_offered_for_lookup():
    """Для поиска предлагаются оба написания сразу."""
    hr = hr_row(telegram_username="maria", telegram_user_id=111)

    assert hr_blacklist_candidates(hr) == ["@maria", "user_id:111"]


def test_a_missing_identifier_drops_its_spelling():
    """Отсутствующий признак своего написания не даёт."""
    assert hr_blacklist_candidates(
        hr_row(telegram_username="maria", telegram_user_id=None)
    ) == ["@maria"]
    assert hr_blacklist_candidates(
        hr_row(telegram_username=None, telegram_user_id=111)
    ) == ["user_id:111"]
    assert hr_blacklist_candidates(
        hr_row(telegram_username=None, telegram_user_id=None)
    ) == []


def test_the_button_writes_the_readable_spelling_when_there_is_one():
    """Кнопка добавления пишет ник, а к идентификатору отступает только без него.

    На экране чёрного списка ник читается, а голое число — нет.
    """
    assert hr_blacklist_preferred_value(
        hr_row(telegram_username="maria", telegram_user_id=111)
    ) == "@maria"
    assert hr_blacklist_preferred_value(
        hr_row(telegram_username=None, telegram_user_id=111)
    ) == "user_id:111"
    assert hr_blacklist_preferred_value(
        hr_row(telegram_username=None, telegram_user_id=None)
    ) is None


async def test_the_card_shows_the_mark_written_under_either_spelling(
    session, session_factory
):
    """Карточка находит отметку, каким бы из двух написаний её ни завели.

    Запись могли добавить, когда у нас был только ник, а идентификатор
    появился позже — и наоборот.
    """
    by_username = hr_row(name="по нику", telegram_username="maria", telegram_user_id=111)
    by_id = hr_row(name="по номеру", telegram_username="olga", telegram_user_id=222)
    await put(session_factory, by_username, by_id)
    await put(
        session_factory,
        blacklist_row("hr", "@maria"),
        blacklist_row("hr", "user_id:222"),
    )

    assert (await get_hr_detail(session, by_username.id)).blacklist_value == "@maria"
    assert (await get_hr_detail(session, by_id.id)).blacklist_value == "user_id:222"


async def test_a_switched_off_mark_does_not_show(session, session_factory):
    """Выключенная отметка в карточке не показывается.

    Строку из списка не удаляют, а гасят: история решений остаётся, но на
    поведение не влияет.
    """
    hr = hr_row(telegram_username="maria", telegram_user_id=111)
    await put(session_factory, hr)
    await put(session_factory, blacklist_row("hr", "@maria", active=False))

    assert (await get_hr_detail(session, hr.id)).blacklist_value is None


async def test_a_mark_of_another_kind_does_not_show(session, session_factory):
    """Отметка другого рода к HR не относится.

    В одной таблице лежат записи и про людей, и про каналы, и про компании;
    совпадение значения между родами возможно.
    """
    hr = hr_row(telegram_username="maria", telegram_user_id=111)
    await put(session_factory, hr)
    await put(session_factory, blacklist_row("channel", "@maria"))

    assert (await get_hr_detail(session, hr.id)).blacklist_value is None


async def test_when_both_spellings_are_listed_the_older_row_wins(
    session, session_factory
):
    """Когда заведены оба написания, показывается заведённое раньше.

    Проверяется направление упорядочивания, а не сам его факт: на двух
    строках база и без сортировки вернула бы их в порядке вставки, и от
    снятия `ORDER BY` тест не покраснеет. Доказать необходимость самой
    сортировки здесь нечем — порядок без неё не определён, но на таком
    наборе совпадает с нужным. Переворот направления ловится.
    """
    hr = hr_row(telegram_username="maria", telegram_user_id=111)
    await put(session_factory, hr)
    await put(
        session_factory,
        blacklist_row("hr", "user_id:111"),
        blacklist_row("hr", "@maria"),
    )

    assert (await get_hr_detail(session, hr.id)).blacklist_value == "user_id:111"
