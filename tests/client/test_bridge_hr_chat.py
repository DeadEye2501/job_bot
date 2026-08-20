"""Следствия переписки: что окно показывает и чем отвечают на отправку.

Предмет отделён от карточки HR: карточка — это запись о человеке, а здесь
письма. Показанное берётся из базы, а вот отправленное уходит боту, и всё, что
окно узнаёт про отправку, оно узнаёт из его ответа.
"""

from tests.client.conftest import WindowThatPicks
from tests.dbio import put
from tests.factories import hr_row, message_row, unread_probe


async def test_the_chat_tells_ours_from_theirs(api, ask, session_factory):
    """В переписке видно, чьё сообщение: своё или собеседника.

    По этому признаку окно рисует их по разным сторонам. Пропади он — беседа
    превратилась бы в один столбец реплик без автора.
    """
    hr = hr_row()
    await put(session_factory, hr)
    await put(
        session_factory,
        message_row(hr_id=hr.id, text="здравствуйте", is_incoming=True),
        message_row(hr_id=hr.id, text="добрый день", is_incoming=False),
    )

    answer = await ask(api.hr.messages, {"hr_id": hr.id})

    said = {row["text"]: row["is_incoming"] for row in answer["ok"]["messages"]}
    assert said == {"здравствуйте": True, "добрый день": False}


async def test_an_attachment_arrives_as_an_address_the_window_can_open(
    api, ask, session_factory
):
    """Вложение приезжает адресом той же раздачи, что отдала саму страницу.

    Хранится оно относительным путём внутри каталога медиа — окно про этот
    каталог не знает вовсе и показать по такому пути ничего не смогло бы.
    Адрес именно http'шный: снимок, вставленный в страницу как `file://`,
    Chromium не загружает — правила происхождения запрещают такой подресурс.
    """
    hr = hr_row()
    await put(session_factory, hr)
    await put(
        session_factory,
        message_row(hr_id=hr.id, text="вот резюме", media_path="1/42.jpg"),
    )

    answer = await ask(api.hr.messages, {"hr_id": hr.id})

    row = answer["ok"]["messages"][0]
    assert row["media_path"] == "/media/1/42.jpg"


async def test_only_chats_with_unread_incoming_are_listed(
    api, ask, session_factory
):
    """В непрочитанное попадает только то, что и правда ждёт ответа.

    Своё, уже прочитанное и удалённое туда не идёт: счётчик над списком —
    единственное, что зовёт человека открыть переписку, и завышенный он
    отправляет его искать несуществующее письмо.
    """
    hr = hr_row(name="Мария")
    await put(session_factory, hr)
    await put(session_factory, *unread_probe(hr.id))

    answer = await ask(api.system.unread_chats)

    chats = answer["ok"]["chats"]
    assert [row["name"] for row in chats] == ["Мария"]
    assert chats[0]["unread_count"] == 1


async def test_marking_read_before_the_bot_is_up_is_refused(api, ask, session_factory):
    """Отметку о прочтении без бота отбивают словами про бота.

    Отметка уходит в Telegram, а не только в базу: собеседник должен увидеть,
    что письмо прочитано. Без бота этого сделать нечем.
    """
    hr = hr_row()
    await put(session_factory, hr)

    answer = await ask(api.hr.mark_read, hr.id)

    assert answer["fail"] == "denied"
    assert answer["detail"] == "Бот ещё не готов."


async def test_marking_read_reaches_the_bot(api, ask, with_bot, session_factory):
    """Отметка доходит до бота вместе с номером собеседника."""
    bot = with_bot(read=3)
    hr = hr_row()
    await put(session_factory, hr)

    answer = await ask(api.hr.mark_read, hr.id)

    assert answer["ok"]["updated"] == 3
    assert ("mark_hr_chat_read", hr.id) in bot.calls


async def test_an_empty_message_never_reaches_the_bot(
    api, ask, with_bot, session_factory
):
    """Пустое сообщение отбивают до бота, а не после.

    Дойди оно — Telegram отказал бы сам, но отказ пришёл бы в переписку
    поломкой, а не понятной причиной, и в чате осталась бы дыра.
    """
    bot = with_bot()
    hr = hr_row()
    await put(session_factory, hr)

    answer = await ask(api.hr.send_message, {"hr_id": hr.id, "text": "   "})

    assert answer["detail"] == "Пустое сообщение."
    assert bot.calls == []


async def test_a_sent_message_comes_back_with_its_number(
    api, ask, with_bot, session_factory
):
    """Отправленное возвращается номером записи.

    По нему окно находит только что появившийся пузырь в переписке — иначе
    отправленное показалось бы лишь после следующего обновления списка.
    """
    with_bot(sent=77)
    hr = hr_row()
    await put(session_factory, hr)

    answer = await ask(api.hr.send_message, {"hr_id": hr.id, "text": "добрый день"})

    assert answer["ok"]["message_id"] == 77


async def test_a_refusal_from_the_bot_is_repeated_word_for_word(
    api, ask, with_bot, session_factory
):
    """Заслон отправки доезжает до окна своими словами.

    Причин отказа несколько — выключенный бот, чёрный список, отсутствие
    ника, — и чинятся они по-разному. Замени мост их на «не удалось», человек
    не понял бы, где чинить.
    """
    with_bot(refusal="Бот выключен. Включите DM Only или Full.")
    hr = hr_row()
    await put(session_factory, hr)

    answer = await ask(api.hr.send_message, {"hr_id": hr.id, "text": "привет"})

    assert answer["fail"] == "denied"
    assert answer["detail"] == "Бот выключен. Включите DM Only или Full."
    assert answer["action"] == "send_message"


async def test_a_closed_dialog_sends_nothing(api, ask, with_bot, hub, session_factory):
    """Закрытый диалог отказом не считается и до бота не доходит.

    Человек передумал — ничего не сломалось. Отзовись мост отказом, окно
    показало бы красную плашку на обычное «нет, не сейчас».
    """
    bot = with_bot()
    hr = hr_row()
    await put(session_factory, hr)
    hub.window = WindowThatPicks(None)

    answer = await ask(api.hr.pick_media, hr.id)

    assert answer["ok"]["cancelled"] is True
    assert bot.calls == []


async def test_the_file_named_in_the_dialog_travels_to_the_bot(
    api, ask, with_bot, hub, session_factory
):
    """Выбранный в диалоге файл уходит боту тем самым путём.

    Путь называет диалог окна, а не страница: этим он и заслонён — до бота не
    доедет то, чего человек не выбирал.
    """
    bot = with_bot(sent=77)
    hr = hr_row()
    await put(session_factory, hr)
    hub.window = WindowThatPicks(["C:/договор.pdf"])

    answer = await ask(api.hr.pick_media, hr.id)

    assert answer["ok"]["message_id"] == 77
    assert ("send_to_hr_media", hr.id, "C:/договор.pdf") in bot.calls
