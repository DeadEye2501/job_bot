"""Следствия того, что репозиторий делает с уже сохранённой строкой переписки.

Сама она приходит из Telegram один раз, а меняется потом дважды: правкой, о
которой сервер сообщает отдельно, и надгробием при удалении. Обе перемены
видит окно, и обе поэтому отвечают ещё и на вопрос «кого перерисовывать»:
число задетых строк и номера их хозяев.
"""

from backend.models import Message
from backend.repository.messages import (
    hr_ids_of_live_messages,
    overwrite_message_text,
    tombstone_messages,
)
from tests.dbio import all_rows, only_row, put
from tests.factories import hr_row, message_row


async def test_an_overwritten_row_carries_the_new_text_and_the_mark(
    session, session_factory
):
    """Правка кладёт в строку новый текст и метку «изменено».

    Без метки окно показало бы новую редакцию как исходную, и пользователь
    решал бы по тексту, которого собеседник не писал.
    """
    hr = hr_row()
    await put(session_factory, hr)
    await put(
        session_factory,
        message_row(hr_id=hr.id, is_incoming=True, tg_message_id=10, text="старая"),
    )

    done = await overwrite_message_text(
        session, hr.id, 10, is_incoming=True, text="новая"
    )
    await session.commit()

    assert done == 1
    saved = await only_row(session_factory, Message)
    assert saved.text == "новая"
    assert saved.is_edited is True


async def test_a_row_of_the_other_direction_keeps_its_text(session, session_factory):
    """Правка входящего не задевает своё сообщение с тем же номером.

    Схема двух таких строк не запрещает (`uq_message_hr_tgid_dir`), и писатель
    обязан отбирать по всем трём частям адреса: сложись они рядом, правка
    входящего показала бы в окне чужой текст под нашей галочкой.
    """
    hr = hr_row()
    await put(session_factory, hr)
    await put(
        session_factory,
        message_row(hr_id=hr.id, is_incoming=True, tg_message_id=10, text="входящее"),
        message_row(hr_id=hr.id, is_incoming=False, tg_message_id=10, text="своё"),
    )

    await overwrite_message_text(session, hr.id, 10, is_incoming=True, text="новая")
    await session.commit()

    by_direction = {m.is_incoming: m for m in await all_rows(session_factory, Message)}
    assert by_direction[True].text == "новая"
    assert by_direction[False].text == "своё"


async def test_the_owner_of_a_live_row_is_named(session, session_factory):
    """У живой строки хозяин называется — его окно и надо перерисовать."""
    hr = hr_row()
    await put(session_factory, hr)
    await put(
        session_factory,
        message_row(hr_id=hr.id, is_incoming=True, tg_message_id=10),
    )

    assert await hr_ids_of_live_messages(
        session, Message.tg_message_id.in_([10])
    ) == {hr.id}


async def test_an_already_buried_row_names_nobody(session, session_factory):
    """Уже похороненная строка хозяина не называет.

    Одну и ту же строку накрывают оба пути — оповещение об удалении и догон
    переписки, вычисляющий удалённое сам. Назови её хозяина вторично, и окно
    перерисовало бы переписку, в которой ничего не изменилось.
    """
    hr = hr_row()
    await put(session_factory, hr)
    await put(
        session_factory,
        message_row(hr_id=hr.id, is_incoming=True, tg_message_id=10),
    )
    await tombstone_messages(session, Message.tg_message_id.in_([10]))
    await session.commit()

    assert await hr_ids_of_live_messages(
        session, Message.tg_message_id.in_([10])
    ) == set()


async def test_a_row_without_an_owner_names_nobody(session, session_factory):
    """Строка без хозяина в ответ не идёт: перерисовывать нечего.

    Такие строки заводит догон переписки до того, как HR опознан; будить по
    ним нечьё окно, а `None` в наборе номеров уронил бы зовущего.
    """
    await put(
        session_factory,
        message_row(hr_id=None, is_incoming=True, tg_message_id=10),
    )

    assert await hr_ids_of_live_messages(
        session, Message.tg_message_id.in_([10])
    ) == set()
