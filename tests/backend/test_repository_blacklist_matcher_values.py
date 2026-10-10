"""Следствия отбора значений, по которым отсеивают вакансии.

Отбор почти не различает рода: одно и то же слово из имени компании и из
текста вакансии отсеивает одинаково. Погашенные строки в отбор не идут.
"""

from backend.repository.blacklist_marks import load_active_blacklist_patterns
from tests.dbio import put
from tests.factories import blacklist_row, hr_row


async def test_only_active_values_reach_the_matcher(session, session_factory):
    """В отбор попадают значения только включённых строк.

    Отбор ключевых слов не различает рода: одно и то же слово из имени
    компании и из текста вакансии отсеивает одинаково.
    """
    await put(
        session_factory,
        blacklist_row("keyword", "казино", active=True),
        blacklist_row("hr", "@maria", active=True),
        blacklist_row("keyword", "передумал", active=False),
    )

    assert sorted(await load_active_blacklist_patterns(session)) == sorted(
        ["казино", "@maria"]
    )


async def test_a_marked_person_is_sifted_out_by_their_nickname(
    session, session_factory
):
    """Отмеченного человека отсеивают и по нику, хотя строка стоит на номере.

    Кнопка «в чёрный список» пишет несменяемый номер учётной записи, а он в
    тексте объявления не встречается никогда. Ник встречается: объявление, под
    которым назван отсеянный рекрутёр, отсеивается по нему — иначе отметка
    гасит только письма, а посты идут как ни в чём не бывало.

    Ник берётся нынешний, из карточки: сменится — отсев поедет за ним сам.
    """
    hr = hr_row(telegram_username="maria", telegram_user_id=111)
    await put(session_factory, hr)
    await put(session_factory, blacklist_row("hr", "user_id:111", active=True))

    assert "@maria" in await load_active_blacklist_patterns(session)


async def test_an_unmarked_person_lends_their_nickname_to_no_one(
    session, session_factory
):
    """Ник неотмеченного в отсев не идёт — ни своей строкой, ни чужой.

    Погашенная отметка равна её отсутствию: снятая с человека, она не должна
    продолжать отсеивать посты его именем.
    """
    await put(session_factory, hr_row(telegram_username="anna", telegram_user_id=222))
    await put(session_factory, blacklist_row("hr", "user_id:222", active=False))

    assert "@anna" not in await load_active_blacklist_patterns(session)
