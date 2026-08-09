"""Следствия подсчёта непрочитанных входящих сообщений.

Непрочитанным считается входящее, у которого не проставлено время прочтения и
которое не удалено. Удалённые исключены не для порядка: удалённое, но так и
не прочитанное сообщение раздувало бы счётчик в подвале, а сбросить его с
экрана было бы нечем — строки в переписке уже нет.
"""

from backend.repository.hr_list import list_hrs_with_unread
from backend.repository.messages import count_unread_incoming
from tests.dbio import put
from tests.factories import at, hr_row, message_row


async def test_an_empty_database_has_nothing_unread(session):
    """На пустой базе непрочитанных нет, и это ноль, а не пустота."""
    assert await count_unread_incoming(session) == 0
    assert await list_hrs_with_unread(session) == []


async def test_only_unread_incoming_alive_messages_are_counted(
    session, session_factory
):
    """Считается только входящее, непрочтённое и неудалённое.

    Рядом с подходящим лежит по одному нарушителю каждого из трёх условий:
    отпадёт любое — счётчик изменится.
    """
    hr = hr_row()
    await put(session_factory, hr)
    await put(
        session_factory,
        message_row(hr_id=hr.id, text="подходит", is_incoming=True, read_at=None),
        message_row(hr_id=hr.id, text="прочитано", is_incoming=True, read_at=at(10)),
        message_row(hr_id=hr.id, text="наше", is_incoming=False, read_at=None),
        message_row(
            hr_id=hr.id, text="удалено", is_incoming=True, read_at=None, is_deleted=True
        ),
    )

    assert await count_unread_incoming(session) == 1


async def test_the_count_covers_every_hr_at_once(session, session_factory):
    """Счётчик в подвале складывает непрочитанное по всем собеседникам."""
    first = hr_row(name="Анна")
    second = hr_row(name="Борис")
    await put(session_factory, first, second)
    await put(
        session_factory,
        message_row(hr_id=first.id, is_incoming=True, read_at=None),
        message_row(hr_id=first.id, is_incoming=True, read_at=None),
        message_row(hr_id=second.id, is_incoming=True, read_at=None),
    )

    assert await count_unread_incoming(session) == 3


async def test_the_popup_lists_only_hrs_with_something_unread(
    session, session_factory
):
    """Во всплывающем списке только те, у кого есть непрочитанное."""
    noisy = hr_row(name="Анна")
    quiet = hr_row(name="Борис")
    silent = hr_row(name="Виктор")
    await put(session_factory, noisy, quiet, silent)
    await put(
        session_factory,
        message_row(hr_id=noisy.id, is_incoming=True, read_at=None, sent_at=at(10)),
        message_row(hr_id=quiet.id, is_incoming=True, read_at=at(5), sent_at=at(20)),
    )

    got = await list_hrs_with_unread(session)

    assert [row["name"] for row in got] == ["Анна"]


async def test_the_popup_leads_with_the_freshest_unread(session, session_factory):
    """Во всплывающем списке вперёд идёт тот, чьё непрочитанное свежее.

    Порядок вставки обратен ожидаемому: совпади они — и выдача без
    сортировки прошла бы проверку.
    """
    older = hr_row(name="Борис")
    newer = hr_row(name="Анна")
    await put(session_factory, older, newer)
    await put(
        session_factory,
        message_row(hr_id=older.id, is_incoming=True, read_at=None, sent_at=at(10)),
        message_row(hr_id=newer.id, is_incoming=True, read_at=None, sent_at=at(50)),
    )

    got = await list_hrs_with_unread(session)

    assert [row["name"] for row in got] == ["Анна", "Борис"]


async def test_the_freshest_unread_wins_not_the_freshest_message(
    session, session_factory
):
    """Свежесть меряется по непрочитанному, а не по последнему сообщению вообще.

    У второго собеседника есть более позднее сообщение, но оно прочитано, и
    наверх его это не поднимает.
    """
    plain = hr_row(name="Анна")
    tricky = hr_row(name="Борис")
    await put(session_factory, plain, tricky)
    await put(
        session_factory,
        message_row(hr_id=plain.id, is_incoming=True, read_at=None, sent_at=at(30)),
        message_row(hr_id=tricky.id, is_incoming=True, read_at=None, sent_at=at(10)),
        message_row(hr_id=tricky.id, is_incoming=True, read_at=at(60), sent_at=at(50)),
    )

    got = await list_hrs_with_unread(session)

    assert [row["name"] for row in got] == ["Анна", "Борис"]


async def test_each_row_carries_the_count_the_username_and_the_time(
    session, session_factory
):
    """В строке всплывающего списка едут число, ник и время последнего непрочитанного."""
    hr = hr_row(name="Анна", telegram_username="anna_hr")
    await put(session_factory, hr)
    await put(
        session_factory,
        message_row(hr_id=hr.id, is_incoming=True, read_at=None, sent_at=at(10)),
        message_row(hr_id=hr.id, is_incoming=True, read_at=None, sent_at=at(50)),
        message_row(hr_id=hr.id, is_incoming=True, read_at=at(5), sent_at=at(90)),
    )

    got = await list_hrs_with_unread(session)

    assert got == [
        {
            "hr_id": hr.id,
            "name": "Анна",
            "telegram_username": "anna_hr",
            "unread_count": 2,
            "last_at": at(50).isoformat(),
        }
    ]
