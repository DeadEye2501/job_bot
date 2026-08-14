"""Следствия переписки: что окно показывает и чем отвечают на отправку.

Предмет отделён от карточки HR: здесь ответ приходит не из базы, а от бота, и
всё, что окно узнаёт про отправку, оно узнаёт из его отказа.
"""

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
    """Вложение приезжает готовым адресом, а не путём в файловой системе.

    Хранится оно относительным путём внутри каталога медиа — окно про этот
    каталог не знает вовсе и показать по такому пути ничего не смогло бы.
    """
    hr = hr_row()
    await put(session_factory, hr)
    await put(
        session_factory,
        message_row(hr_id=hr.id, text="вот резюме", media_path="1/42.jpg"),
    )

    answer = await ask(api.hr.messages, {"hr_id": hr.id})

    row = answer["ok"]["messages"][0]
    assert row["media_path"].startswith("file:///")
    assert row["media_path"].endswith("/1/42.jpg")


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


async def test_a_file_without_a_path_never_reaches_the_bot(
    api, ask, with_bot, session_factory
):
    """Без пути к файлу до бота не доходит ничего.

    Путь выбирает окно, и до моста он может не доехать вовсе. Отправь мост
    отсутствие дальше — Telegram отказал бы уже своими словами, из которых
    не видно, что файла никто не называл.
    """
    bot = with_bot()
    hr = hr_row()
    await put(session_factory, hr)

    answer = await ask(api.hr.send_media, {"hr_id": hr.id})

    assert answer["fail"] == "fields"
    assert bot.calls == []


async def test_a_chosen_file_travels_to_the_bot(api, ask, with_bot, session_factory):
    """Выбранный файл доходит до бота тем самым путём, что назвал человек."""
    bot = with_bot(sent=99)
    hr = hr_row()
    await put(session_factory, hr)

    answer = await ask(api.hr.send_media, {"hr_id": hr.id, "path": "C:/резюме.pdf"})

    assert answer["ok"]["message_id"] == 99
    assert ("send_to_hr_media", hr.id, "C:/резюме.pdf") in bot.calls
