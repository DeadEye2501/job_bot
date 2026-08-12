"""Следствия правки значения и причины у строки чёрного списка.

Правка различает «не трогать» и «стереть» — у каждого поля своя метка «не
задано». Значение стереть нельзя: оно и есть предмет записи, а пустое ни с
чем не совпадёт и на экране выглядит незаполненной заготовкой.
"""

import pytest

from backend.models import Blacklist
from backend.repository.blacklist import BlacklistUpdateError, update_blacklist
from tests.dbio import put
from tests.factories import blacklist_row


async def test_editing_a_missing_row_reports_failure(session):
    """Править несуществующую строку нельзя, и вызов об этом сообщает."""
    assert await update_blacklist(session, 10_000, value="@x") is False


async def test_an_unnamed_field_is_left_untouched(session, session_factory):
    """Не названное в вызове поле остаётся прежним — и это верно для обоих.

    Проверяются оба направления: правка одной причины не трогает значение и
    правка одного значения не трогает причину. С одним направлением метку
    «не задано» у второго поля можно было бы выбросить незаметно.
    """
    by_reason = blacklist_row("hr", "@maria", reason="грубит")
    by_value = blacklist_row("hr", "@olga", reason="тоже грубит")
    await put(session_factory, by_reason, by_value)

    assert await update_blacklist(session, by_reason.id, reason="передумал") is True
    assert await update_blacklist(session, by_value.id, value="@olga_new") is True

    kept_value = await session.get(Blacklist, by_reason.id)
    assert kept_value.value == "@maria"
    assert kept_value.reason == "передумал"

    kept_reason = await session.get(Blacklist, by_value.id)
    assert kept_reason.value == "@olga_new"
    assert kept_reason.reason == "тоже грубит"


async def test_an_emptied_reason_becomes_absence(session, session_factory):
    """Стёртая причина становится отсутствием, а не пустой строкой."""
    row = blacklist_row("hr", "@maria", reason="грубит")
    await put(session_factory, row)

    await update_blacklist(session, row.id, reason="   ")

    assert (await session.get(Blacklist, row.id)).reason is None


async def test_a_reason_that_came_as_a_number_does_not_break_the_edit(
    session, session_factory
):
    """Причина, пришедшая не строкой, правку не роняет.

    Нагрузку из окна составляет не наш код, и в текстовом поле оттуда
    приходит что угодно. Так же это читают правка карточки HR и правка
    компании — там правило стоит по четырём местам, — а здесь пятое
    написание падало на первом же таком значении, унося с собой всю правку.
    """
    row = blacklist_row("hr", "@maria", reason="грубит")
    await put(session_factory, row)

    assert await update_blacklist(session, row.id, reason=42) is True

    assert (await session.get(Blacklist, row.id)).reason == "42"


async def test_an_emptied_value_is_refused(session, session_factory):
    """Стереть значение правкой нельзя — оно и есть предмет записи."""
    row = blacklist_row("hr", "@maria")
    await put(session_factory, row)

    with pytest.raises(BlacklistUpdateError, match="Значение"):
        await update_blacklist(session, row.id, value="   ")

    assert (await session.get(Blacklist, row.id)).value == "@maria"
