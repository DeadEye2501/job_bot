"""Следствия гашения и включения строки чёрного списка.

Строку не удаляют, а гасят: решение остаётся в истории, но на поведение не
влияет. Обратный ход тоже возможен.
"""

from backend.models import Blacklist
from backend.repository.blacklist import (
    deactivate_blacklist_values,
    set_blacklist_active,
)
from tests.dbio import put
from tests.factories import blacklist_row


async def test_switching_a_missing_row_reports_failure(session):
    """Погасить несуществующую строку нельзя, и вызов об этом сообщает."""
    assert await set_blacklist_active(session, 10_000, False) is False


async def test_the_mark_is_taken_off_every_spelling_of_the_same_subject(
    session, session_factory
):
    """Отметка снимается со всех написаний предмета разом.

    У HR их бывает два сразу — ник и номер учётной записи, — и кнопка
    «убрать из чёрного списка» обязана погасить оба: оставшееся написание
    держало бы отметку дальше, а на экране её было бы нечем снять.
    """
    by_name = blacklist_row("hr", "@maria", active=True)
    by_number = blacklist_row("hr", "user_id:77", active=True)
    await put(session_factory, by_name, by_number)

    taken_off = await deactivate_blacklist_values(
        session, "hr", ["@maria", "user_id:77"]
    )

    assert taken_off == 2
    assert (await session.get(Blacklist, by_name.id)).active is False
    assert (await session.get(Blacklist, by_number.id)).active is False


async def test_a_second_taking_off_reports_that_there_was_nothing_to_take(
    session, session_factory
):
    """Повторное снятие отметки сообщает, что снимать было нечего.

    По этому числу окно и выбирает подсказку: «убран из чёрного списка»
    против «в чёрном списке не было». Погашенная строка лежит на месте и
    видна на экране, но снятой второй раз не считается.
    """
    await put(session_factory, blacklist_row("hr", "@maria", active=False))

    taken_off = await deactivate_blacklist_values(session, "hr", ["@maria"])

    assert taken_off == 0


async def test_taking_the_mark_off_spares_other_kinds_and_other_subjects(
    session, session_factory
):
    """Гасится только свой род и только свои написания.

    То же значение бывает и ником человека, и ником канала, и снятие
    отметки с человека не должно возвращать канал в работу.
    """
    same_value_other_kind = blacklist_row("channel", "@maria", active=True)
    other_subject = blacklist_row("hr", "@olga", active=True)
    await put(session_factory, same_value_other_kind, other_subject)

    taken_off = await deactivate_blacklist_values(session, "hr", ["@maria"])

    assert taken_off == 0
    assert (await session.get(Blacklist, same_value_other_kind.id)).active is True
    assert (await session.get(Blacklist, other_subject.id)).active is True


async def test_a_row_switches_both_ways(session, session_factory):
    """Строка гасится и включается обратно."""
    row = blacklist_row("hr", "@maria", active=True)
    await put(session_factory, row)

    assert await set_blacklist_active(session, row.id, False) is True
    assert (await session.get(Blacklist, row.id)).active is False

    assert await set_blacklist_active(session, row.id, True) is True
    assert (await session.get(Blacklist, row.id)).active is True
