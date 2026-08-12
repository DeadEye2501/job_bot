"""Следствия сохранения входящего сообщения.

Всё, что пришло вместе с сообщением, — вложение, привязка к вакансии, время
отправки — записывается как есть: разбор этих полей случился выше по стеку, и
переспросить Telegram будет нечем.
"""

from backend.payloads import IncomingMessage
from backend.repository.messages import save_incoming_message
from tests.dbio import put
from tests.factories import at, hr_row, vacancy_row


async def test_an_incoming_message_is_stored_with_all_it_carries(
    session, session_factory
):
    """Входящее сохраняется со всем, что при нём пришло."""
    hr = hr_row()
    await put(session_factory, hr)
    vacancy = vacancy_row(hr_id=hr.id)
    await put(session_factory, vacancy)

    saved = await save_incoming_message(
        session,
        IncomingMessage(
            hr_id=hr.id,
            vacancy_id=vacancy.id,
            text="приглашаем на созвон",
            tg_message_id=42,
            received_at=at(10),
            media_kind="document",
            media_path="cv/answer.pdf",
            media_name="Тестовое.pdf",
        ),
    )

    assert saved.is_incoming is True
    assert saved.hr_id == hr.id
    assert saved.vacancy_id == vacancy.id
    assert saved.text == "приглашаем на созвон"
    assert saved.tg_message_id == 42
    assert saved.sent_at == at(10)
    assert saved.media_kind == "document"
    assert saved.media_path == "cv/answer.pdf"
    assert saved.media_name == "Тестовое.pdf"


async def test_a_message_without_media_or_vacancy_is_stored_too(
    session, session_factory
):
    """Сообщение без вложения и без вакансии сохраняется с пустотами."""
    hr = hr_row()
    await put(session_factory, hr)

    saved = await save_incoming_message(
        session,
        IncomingMessage(
            hr_id=hr.id,
            vacancy_id=None,
            text="просто текст",
            tg_message_id=1,
            received_at=at(10),
        ),
    )

    assert saved.vacancy_id is None
    assert saved.media_kind is None
    assert saved.media_path is None
    assert saved.media_name is None
