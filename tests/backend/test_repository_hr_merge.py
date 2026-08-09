"""Следствия слияния двух записей об одном человеке.

Один HR заводится дважды легко: сперва руками по нику с экрана контактов,
потом сам собой при первом входящем сообщении. Слияние необратимо, и главное
его правило — учётная запись Telegram и переписка едут вместе одним целым:
переписка без учётной записи, из которой она пришла, смысла не имеет.
"""

import pytest
from sqlalchemy import select

from backend.models import HR, Message, Vacancy
from backend.repository.hr_card import merge_hr
from tests.dbio import put
from tests.factories import hr_row, message_row, vacancy_row


async def test_merging_a_record_into_itself_is_refused(session, session_factory):
    """Слить запись саму с собой нельзя: это стёрло бы её без остатка."""
    hr = hr_row()
    await put(session_factory, hr)

    with pytest.raises(ValueError, match="absorbed_id == survivor_id"):
        await merge_hr(session, absorbed_id=hr.id, survivor_id=hr.id)


async def test_merging_with_a_missing_record_is_refused(session, session_factory):
    """Слияние с несуществующей записью не проходит молча."""
    hr = hr_row()
    await put(session_factory, hr)

    with pytest.raises(ValueError, match="not found"):
        await merge_hr(session, absorbed_id=hr.id, survivor_id=10_000)


async def test_vacancies_of_both_records_end_up_on_the_survivor(
    session, session_factory
):
    """Вакансии обеих записей достаются оставшейся, а поглощённая исчезает."""
    absorbed = hr_row(name="дубль")
    survivor = hr_row(name="основной")
    await put(session_factory, absorbed, survivor)
    await put(
        session_factory,
        vacancy_row(title="от дубля", hr_id=absorbed.id),
        vacancy_row(title="от основного", hr_id=survivor.id),
    )

    await merge_hr(session, absorbed_id=absorbed.id, survivor_id=survivor.id)

    rows = (await session.scalars(select(Vacancy))).all()
    assert {v.title: v.hr_id for v in rows} == {
        "от дубля": survivor.id,
        "от основного": survivor.id,
    }
    assert (await session.scalars(select(HR.name))).all() == ["основной"]


async def test_a_survivor_with_its_own_account_keeps_it_and_drops_the_other_chat(
    session, session_factory
):
    """У оставшейся есть своя учётная запись — чужая переписка стирается вместе с чужой.

    Переписка привязана к учётной записи, из которой пришла. Перенести её на
    другую значило бы показать пользователю чужой разговор как свой.
    """
    absorbed = hr_row(name="дубль", telegram_user_id=222, telegram_username="dubl")
    survivor = hr_row(name="основной", telegram_user_id=111, telegram_username="main")
    await put(session_factory, absorbed, survivor)
    await put(
        session_factory,
        message_row(text="из чужого чата", hr_id=absorbed.id),
        message_row(text="из своего чата", hr_id=survivor.id),
    )

    await merge_hr(session, absorbed_id=absorbed.id, survivor_id=survivor.id)

    rows = (await session.scalars(select(Message))).all()
    assert [m.text for m in rows] == ["из своего чата"]
    kept = await session.get(HR, survivor.id)
    assert kept.telegram_user_id == 111
    assert kept.telegram_username == "main"


async def test_a_survivor_without_an_account_adopts_the_other_one_with_its_chat(
    session, session_factory
):
    """У оставшейся учётной записи нет — она забирает чужую вместе с перепиской.

    Ровно этот случай и есть обычный: сперва человека завели руками по нику,
    потом он написал, и бот создал вторую запись уже с идентификатором.

    Заодно здесь видно, что ник учётной записью не считается: у оставшейся
    он есть, а переписка всё равно переезжает. Ник без идентификатора — это
    подсказка, введённая руками, а не связь с Telegram.
    """
    absorbed = hr_row(name="из телеграма", telegram_user_id=222, telegram_username="dubl")
    survivor = hr_row(name="заведён руками", telegram_user_id=None, telegram_username="hand")
    await put(session_factory, absorbed, survivor)
    await put(session_factory, message_row(text="переехало", hr_id=absorbed.id))

    await merge_hr(session, absorbed_id=absorbed.id, survivor_id=survivor.id)

    rows = (await session.scalars(select(Message))).all()
    assert [(m.text, m.hr_id) for m in rows] == [("переехало", survivor.id)]
    kept = await session.get(HR, survivor.id)
    assert kept.telegram_user_id == 222
    assert kept.telegram_username == "dubl"


async def test_a_name_is_taken_only_when_the_survivor_has_none(
    session, session_factory
):
    """Имя забирается у поглощённой, только если у оставшейся его нет."""
    absorbed = hr_row(name="из телеграма")
    survivor = hr_row(name=None)
    await put(session_factory, absorbed, survivor)

    await merge_hr(session, absorbed_id=absorbed.id, survivor_id=survivor.id)

    assert (await session.get(HR, survivor.id)).name == "из телеграма"


async def test_an_existing_name_is_not_overwritten(session, session_factory):
    """Имя, введённое пользователем, чужим не затирается."""
    absorbed = hr_row(name="из телеграма")
    survivor = hr_row(name="как я записал")
    await put(session_factory, absorbed, survivor)

    await merge_hr(session, absorbed_id=absorbed.id, survivor_id=survivor.id)

    assert (await session.get(HR, survivor.id)).name == "как я записал"


async def test_notes_of_both_records_are_kept(session, session_factory):
    """Заметки обеих записей склеиваются: слияние необратимо, и терять нечего."""
    absorbed = hr_row(name="дубль", notes="звонил в среду")
    survivor = hr_row(name="основной", notes="просил резюме")
    await put(session_factory, absorbed, survivor)

    await merge_hr(session, absorbed_id=absorbed.id, survivor_id=survivor.id)

    assert (await session.get(HR, survivor.id)).notes == (
        "просил резюме\n---\nзвонил в среду"
    )


async def test_a_single_note_survives_without_a_separator(session, session_factory):
    """Одна заметка на двоих остаётся как есть, без разделителя."""
    absorbed = hr_row(name="дубль", notes="звонил в среду")
    survivor = hr_row(name="основной", notes=None)
    await put(session_factory, absorbed, survivor)

    await merge_hr(session, absorbed_id=absorbed.id, survivor_id=survivor.id)

    assert (await session.get(HR, survivor.id)).notes == "звонил в среду"


async def test_two_empty_notes_stay_empty(session, session_factory):
    """Из двух пустых заметок не рождается разделитель."""
    absorbed = hr_row(name="дубль", notes="   ")
    survivor = hr_row(name="основной", notes=None)
    await put(session_factory, absorbed, survivor)

    await merge_hr(session, absorbed_id=absorbed.id, survivor_id=survivor.id)

    assert (await session.get(HR, survivor.id)).notes is None
