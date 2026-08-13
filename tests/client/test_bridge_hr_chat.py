"""Следствия слотов переписки: что окно показывает и чем отвечает на отправку.

Предмет отделён от карточки HR: здесь ответ приходит не из базы, а от бота, и
всё, что окно узнаёт про отправку, оно узнаёт из его отказа.
"""

import json

import pytest
from PySide6.QtWidgets import QFileDialog

from tests.dbio import put
from tests.factories import hr_row, message_row, unread_probe


@pytest.fixture
def chosen_file(monkeypatch):
    """Отвечает за человека в диалоге выбора файла.

    Диалог — статический вызов Qt, поднимающий настоящее окно; подменяется он
    целиком, иначе прогон встал бы на первом же тесте, ожидая нажатия.
    """

    def _choose(path: str) -> None:
        monkeypatch.setattr(
            QFileDialog, "getOpenFileName", lambda *a, **k: (path, "")
        )

    return _choose


async def test_the_chat_tells_ours_from_theirs(main_api, watch, session_factory):
    """В переписке видно, чьё сообщение: своё или собеседника.

    По этому признаку окно рисует их по разным сторонам. Пропади он — беседа
    превратилась бы в один столбец реплик без автора.
    """
    caught = watch(main_api.contacts_hr_messages_loaded)
    hr = hr_row()
    await put(session_factory, hr)
    await put(
        session_factory,
        message_row(hr_id=hr.id, text="здравствуйте", is_incoming=True),
        message_row(hr_id=hr.id, text="добрый день", is_incoming=False),
    )

    main_api.request_contacts_hr_messages(json.dumps({"hr_id": hr.id}))

    said = {row["text"]: row["is_incoming"] for row in (await caught.next())["messages"]}
    assert said == {"здравствуйте": True, "добрый день": False}


async def test_an_attachment_arrives_as_an_address_the_window_can_open(
    main_api, watch, session_factory
):
    """Вложение приезжает готовым адресом, а не путём в файловой системе.

    Хранится оно относительным путём внутри каталога медиа — окно про этот
    каталог не знает вовсе и показать по такому пути ничего не смогло бы.
    """
    caught = watch(main_api.contacts_hr_messages_loaded)
    hr = hr_row()
    await put(session_factory, hr)
    await put(
        session_factory,
        message_row(hr_id=hr.id, text="вот резюме", media_path="1/42.jpg"),
    )

    main_api.request_contacts_hr_messages(json.dumps({"hr_id": hr.id}))

    row = (await caught.next())["messages"][0]
    assert row["media_path"].startswith("file:///")
    assert row["media_path"].endswith("/1/42.jpg")


async def test_only_chats_with_unread_incoming_are_listed(
    main_api, watch, session_factory
):
    """В непрочитанное попадает только то, что и правда ждёт ответа.

    Своё, уже прочитанное и удалённое туда не идёт: счётчик над списком —
    единственное, что зовёт человека открыть переписку, и завышенный он
    отправляет его искать несуществующее письмо.
    """
    caught = watch(main_api.unread_chats_loaded)
    hr = hr_row(name="Мария")
    await put(session_factory, hr)
    await put(session_factory, *unread_probe(hr.id))

    main_api.request_unread_chats()

    chats = (await caught.next())["chats"]
    assert [row["name"] for row in chats] == ["Мария"]
    assert chats[0]["unread_count"] == 1


async def test_marking_read_before_the_bot_is_up_is_refused(
    main_api, watch, session_factory
):
    """Отметку о прочтении без бота отбивают словами про бота.

    Отметка уходит в Telegram, а не только в базу: собеседник должен увидеть,
    что письмо прочитано. Без бота этого сделать нечем.
    """
    caught = watch(main_api.contacts_hr_action_done)
    hr = hr_row()
    await put(session_factory, hr)

    main_api.contacts_mark_hr_read(hr.id)

    answer = await caught.next()
    assert answer["ok"] is False
    assert answer["error"] == "Бот ещё не запущен."


async def test_marking_read_reaches_the_bot(main_api, watch, with_bot, session_factory):
    """Отметка доходит до бота вместе с номером собеседника."""
    caught = watch(main_api.contacts_hr_action_done)
    bot = with_bot(read=3)
    hr = hr_row()
    await put(session_factory, hr)

    main_api.contacts_mark_hr_read(hr.id)

    answer = await caught.next()
    assert answer["updated"] == 3
    assert ("mark_hr_chat_read", hr.id) in bot.calls


async def test_an_empty_message_never_reaches_the_bot(
    main_api, watch, with_bot, session_factory
):
    """Пустое сообщение отбивают до бота, а не после.

    Дойди оно — Telegram отказал бы сам, но отказ пришёл бы в переписку
    поломкой, а не понятной причиной, и в чате осталась бы дыра.
    """
    caught = watch(main_api.contacts_hr_action_done)
    bot = with_bot()
    hr = hr_row()
    await put(session_factory, hr)

    main_api.contacts_send_hr_message(json.dumps({"hr_id": hr.id, "text": "   "}))

    assert (await caught.next())["error"] == "Пустое сообщение."
    assert bot.calls == []


async def test_a_sent_message_comes_back_with_its_number(
    main_api, watch, with_bot, session_factory
):
    """Отправленное возвращается номером записи.

    По нему окно находит только что появившийся пузырь в переписке — иначе
    отправленное показалось бы лишь после следующего обновления списка.
    """
    caught = watch(main_api.contacts_hr_action_done)
    with_bot(sent=77)
    hr = hr_row()
    await put(session_factory, hr)

    main_api.contacts_send_hr_message(
        json.dumps({"hr_id": hr.id, "text": "добрый день"})
    )

    answer = await caught.next()
    assert answer["ok"] is True
    assert answer["message_id"] == 77


async def test_a_refusal_from_the_bot_is_repeated_word_for_word(
    main_api, watch, with_bot, session_factory
):
    """Заслон отправки доезжает до окна своими словами.

    Причин отказа несколько — выключенный бот, чёрный список, отсутствие
    ника, — и чинятся они по-разному. Замени мост их на «не удалось», человек
    не понял бы, где чинить.
    """
    caught = watch(main_api.contacts_hr_action_done)
    with_bot(refusal="Бот выключен. Включите DM Only или Full.")
    hr = hr_row()
    await put(session_factory, hr)

    main_api.contacts_send_hr_message(json.dumps({"hr_id": hr.id, "text": "привет"}))

    answer = await caught.next()
    assert answer["ok"] is False
    assert answer["error"] == "Бот выключен. Включите DM Only или Full."
    assert answer["action"] == "send_message"


async def test_a_cancelled_file_choice_says_nothing(
    main_api, watch, with_bot, chosen_file, session_factory
):
    """Передумавшему выбирать файл не отвечают вовсе.

    Закрытое окно выбора — не ошибка, а обычный отказ от намерения. Ответь
    мост отказом, человек получал бы сообщение о поломке всякий раз, когда
    просто передумал.
    """
    caught = watch(main_api.contacts_hr_action_done)
    bot = with_bot()
    chosen_file("")
    hr = hr_row()
    await put(session_factory, hr)

    main_api.contacts_pick_and_send_hr_media(hr.id)

    assert await caught.silent()
    assert bot.calls == []


async def test_a_chosen_file_travels_to_the_bot(
    main_api, watch, with_bot, chosen_file, session_factory
):
    """Выбранный файл доходит до бота тем самым путём, что назвал человек."""
    caught = watch(main_api.contacts_hr_action_done)
    bot = with_bot(sent=99)
    chosen_file("C:/резюме.pdf")
    hr = hr_row()
    await put(session_factory, hr)

    main_api.contacts_pick_and_send_hr_media(hr.id)

    assert (await caught.next())["message_id"] == 99
    assert ("send_to_hr_media", hr.id, "C:/резюме.pdf") in bot.calls
