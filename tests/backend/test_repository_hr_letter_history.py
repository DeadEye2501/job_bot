"""Следствия подсчёта писем, отправленных HR за последнее время.

По счётчику решают, что слать: полный отклик с резюме, если это первое письмо
за окно, или короткое напоминание, если уже писали.
"""

from backend.repository.hr_identify import count_recent_outgoing_with_vacancy_for_hr
from tests.dbio import put
from tests.factories import days_ago, hr_row, message_row, vacancy_row


async def test_letters_without_a_vacancy_are_not_counted(session, session_factory):
    """Считаются только письма по вакансии: ручная переписка в счёт не идёт."""
    hr = hr_row()
    await put(session_factory, hr)
    vacancy = vacancy_row(hr_id=hr.id)
    await put(session_factory, vacancy)
    await put(
        session_factory,
        message_row(
            hr_id=hr.id, vacancy_id=vacancy.id, tg_message_id=1,
            is_incoming=False, sent_at=days_ago(1),
        ),
        message_row(
            hr_id=hr.id, vacancy_id=None, tg_message_id=2,
            is_incoming=False, sent_at=days_ago(1),
        ),
        message_row(
            hr_id=hr.id, vacancy_id=vacancy.id, tg_message_id=3,
            is_incoming=True, sent_at=days_ago(1),
        ),
    )

    assert await count_recent_outgoing_with_vacancy_for_hr(
        session, hr.id, window_days=14, other_than=0
    ) == 1


async def test_letters_older_than_the_window_are_not_counted(
    session, session_factory
):
    """Письма старше окна в счёт не идут: по счётчику решают, слать ли полный отклик."""
    hr = hr_row()
    await put(session_factory, hr)
    vacancy = vacancy_row(hr_id=hr.id)
    await put(session_factory, vacancy)
    await put(
        session_factory,
        message_row(
            hr_id=hr.id, vacancy_id=vacancy.id, tg_message_id=1,
            is_incoming=False, sent_at=days_ago(3),
        ),
        message_row(
            hr_id=hr.id, vacancy_id=vacancy.id, tg_message_id=2,
            is_incoming=False, sent_at=days_ago(40),
        ),
    )

    assert await count_recent_outgoing_with_vacancy_for_hr(
        session, hr.id, window_days=14, other_than=0
    ) == 1
    assert await count_recent_outgoing_with_vacancy_for_hr(
        session, hr.id, window_days=60, other_than=0
    ) == 2


async def test_the_window_is_counted_from_today_by_whole_days(
    session, session_factory
):
    """Граница окна отмеряется от сегодняшнего дня, а не от начала переписки.

    Письмо тринадцатидневной давности в окно из четырнадцати дней попадает,
    пятнадцатидневное — нет. Сместись отсчёт хоть на сутки, и HR получил бы
    полный отклик вместо короткого напоминания — или наоборот.
    """
    hr = hr_row()
    await put(session_factory, hr)
    vacancy = vacancy_row(hr_id=hr.id)
    await put(session_factory, vacancy)
    await put(
        session_factory,
        message_row(
            hr_id=hr.id, vacancy_id=vacancy.id, tg_message_id=1,
            is_incoming=False, sent_at=days_ago(13),
        ),
        message_row(
            hr_id=hr.id, vacancy_id=vacancy.id, tg_message_id=2,
            is_incoming=False, sent_at=days_ago(15),
        ),
    )

    assert await count_recent_outgoing_with_vacancy_for_hr(
        session, hr.id, window_days=14, other_than=0
    ) == 1


async def test_an_hr_we_never_wrote_to_has_a_count_of_zero(session, session_factory):
    """У HR без переписки счётчик равен нулю, а не пустоте."""
    hr = hr_row()
    await put(session_factory, hr)

    assert await count_recent_outgoing_with_vacancy_for_hr(
        session, hr.id, window_days=14, other_than=0
    ) == 0
