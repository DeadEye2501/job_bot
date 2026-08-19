"""Следствия перечней, с которых бот догоняет пропущенное после простоя.

Перечня два, и они разной ширины. Первый берёт всех, до кого вообще можно
дотянуться в Telegram; второй — только тех, кому мы писали первыми, и с
каждым отдаёт наибольший номер уже полученного сообщения.
"""

from backend.repository.hr_list import list_hrs_for_backfill, list_open_hr_chats
from tests.dbio import put
from tests.factories import hr_row, message_row


async def test_backfill_covers_everyone_reachable_in_telegram(
    session, session_factory
):
    """В догоняющий разбор идут все, у кого есть хоть какой-то признак в Telegram."""
    await put(
        session_factory,
        hr_row(name="по идентификатору", telegram_user_id=111, telegram_username=None),
        hr_row(name="по нику", telegram_user_id=None, telegram_username="maria"),
        hr_row(name="без признаков", telegram_user_id=None, telegram_username=None),
    )

    got = await list_hrs_for_backfill(session)

    assert sorted(hr.name for hr in got) == sorted(["по идентификатору", "по нику"])


async def test_open_chats_need_both_an_id_and_a_letter_from_us(
    session, session_factory
):
    """Открытым считается чат, где есть идентификатор и наше отправленное письмо."""
    both = hr_row(name="и то и другое", telegram_user_id=111)
    no_letter = hr_row(name="письма не было", telegram_user_id=222)
    no_id = hr_row(name="без идентификатора", telegram_user_id=None, telegram_username="x")
    await put(session_factory, both, no_letter, no_id)
    await put(
        session_factory,
        message_row(hr_id=both.id, tg_message_id=5, is_incoming=False),
        message_row(hr_id=no_letter.id, tg_message_id=6, is_incoming=True),
        message_row(hr_id=no_id.id, tg_message_id=7, is_incoming=False),
    )

    got = await list_open_hr_chats(session)

    assert [hr.name for hr, _ in got] == ["и то и другое"]


async def test_open_chats_report_the_highest_incoming_message_number(
    session, session_factory
):
    """С открытым чатом отдаётся наибольший номер уже полученного сообщения.

    Исходящие в счёт не идут — нумерация у них та же, и наше письмо сдвинуло
    бы отметку вперёд, спрятав ответ HR.

    Больший номер вставлен раньше меньшего нарочно: вставь по возрастанию —
    и «наибольший» стал бы неотличим от «последнего вставленного».
    """
    hr = hr_row(telegram_user_id=111)
    silent = hr_row(telegram_user_id=222, name="без входящих")
    await put(session_factory, hr, silent)
    await put(
        session_factory,
        message_row(hr_id=hr.id, tg_message_id=30, is_incoming=True),
        message_row(hr_id=hr.id, tg_message_id=10, is_incoming=True),
        message_row(hr_id=hr.id, tg_message_id=99, is_incoming=False),
        message_row(hr_id=silent.id, tg_message_id=5, is_incoming=False),
    )

    got = dict((h.telegram_user_id, seen) for h, seen in await list_open_hr_chats(session))

    assert got == {111: 30, 222: 0}
