"""Следствия действий над каналом, которым нужен поднятый бот.

Предмет — то, что мост делает чужими руками: заводит канал по имени, гонит его
вне очереди, отматывает отметку прочитанного и удаляет. Всё это идёт в
Telegram, поэтому бот подделан.
"""

from tests.dbio import put
from tests.factories import channel_row


async def test_a_name_that_is_not_a_channel_never_reaches_telegram(
    api, ask, with_bot
):
    """Нераспознанное имя отбивают до Telegram, назвав годные виды записи.

    Имя канала вставляют из чего попало — из ссылки, из пересланного письма,
    из адресной строки. Уйди мусор в сеть, ответом был бы отказ Telegram, из
    которого не видно, что чинить именно строку ввода.
    """
    bot = with_bot()

    answer = await ask(api.channels.create, {"input": "не ссылка и не имя"})

    assert answer["fail"] == "denied"
    assert "Поддерживаются форматы" in answer["detail"]
    assert bot.calls == []


async def test_an_empty_name_is_refused_before_the_bot(api, ask, with_bot):
    """Пустое поле отбивают своими словами, а не молчанием."""
    bot = with_bot()

    answer = await ask(api.channels.create, {"input": "   "})

    assert answer["detail"] == "Укажите @username или ссылку на канал."
    assert bot.calls == []


async def test_a_link_arrives_at_the_bot_as_a_bare_name(api, ask, with_bot):
    """Из ссылки до бота доезжает одно имя, без адреса вокруг.

    Telegram спрашивают по имени; отправь ему целый адрес — канал не нашёлся
    бы, хотя человек ввёл верную ссылку.
    """
    bot = with_bot(added=(7, "created"))

    answer = await ask(api.channels.create, {"input": "https://t.me/pyjobs"})

    assert answer["ok"]["channel_id"] == 7
    assert ("add_channel", "pyjobs") in bot.calls


async def test_a_channel_telegram_does_not_know_is_named_in_the_answer(
    api, ask, with_bot
):
    """Про ненайденный канал говорят его же именем.

    Ошибаются обычно в одной букве, и увидеть, каким именем искали, — самый
    короткий путь понять, где опечатка.
    """
    with_bot(added=(None, "invalid"))

    answer = await ask(api.channels.create, {"input": "@pyjobz"})

    assert answer["fail"] == "denied"
    assert "pyjobz" in answer["detail"]


async def test_an_already_known_channel_is_not_an_error(api, ask, with_bot):
    """Второе заведение того же канала — не ошибка, а указание на прежний.

    Человек не помнит, заводил ли; ответь мост отказом — он решил бы, что
    канал недоступен, вместо того чтобы открыть уже готовую карточку.
    """
    with_bot(added=(3, "exists"))

    answer = await ask(api.channels.create, {"input": "@pyjobs"})

    assert answer["ok"]["created"] is False
    assert answer["ok"]["channel_id"] == 3


async def test_a_manual_walk_before_the_bot_is_up_is_refused_by_name(
    api, ask, session_factory
):
    """Ручной обход без бота отбивают словами про бота.

    Обход идёт в Telegram; без него объяснить человеку, почему кнопка не
    сработала, больше нечем.
    """
    channel = channel_row(username="pyjobs")
    await put(session_factory, channel)

    answer = await ask(api.channels.poll_now, channel.id)

    assert answer["detail"] == "Бот ещё не готов."


async def test_a_busy_walk_is_explained(api, ask, with_bot, session_factory):
    """Занятый обход объясняют, а не глотают.

    Место прогона одно на все каналы, и попасть на занятое — обычное дело.
    Промолчи мост — кнопка выглядела бы сломанной.
    """
    with_bot(channel_poll="busy")
    channel = channel_row(username="pyjobs")
    await put(session_factory, channel)

    answer = await ask(api.channels.poll_now, channel.id)

    assert answer["fail"] == "denied"
    assert answer["status"] == "busy"


async def test_an_unknown_walk_outcome_still_answers(
    api, ask, with_bot, session_factory
):
    """Незнакомый исход обхода тоже получает ответ.

    Исходы заводит бэкенд, и новый появится там раньше перевода здесь.
    Промолчи мост — кнопка осталась бы нажатой навсегда.
    """
    with_bot(channel_poll="перегрев")
    channel = channel_row(username="pyjobs")
    await put(session_factory, channel)

    answer = await ask(api.channels.poll_now, channel.id)

    assert answer["fail"] == "denied"
    assert answer["status"] == "перегрев"


async def test_a_finished_walk_answers_plainly(api, ask, with_bot, session_factory):
    """Удавшийся обход отвечает без оговорок, и по этому ответу гаснет ожидание.

    Остальные исходы окно показывает сообщением, а этот — единственный, после
    которого список просто перечитывают. Не приди он, кнопка осталась бы
    нажатой до перезапуска.
    """
    bot = with_bot()
    channel = channel_row(username="pyjobs")
    await put(session_factory, channel)

    answer = await ask(api.channels.poll_now, channel.id)

    assert answer["ok"]["status"] == "ok"
    assert ("poll_channel_now", channel.id) in bot.calls


async def test_a_reset_cursor_reaches_the_bot(api, ask, with_bot, session_factory):
    """Отматывание отметки доходит до бота вместе с номером канала.

    После него канал перечитывают с начала — это единственный способ вернуть
    пропущенные объявления. Не дойди вызов, кнопка отвечала бы успехом, а
    прежние сообщения так и остались бы непрочитанными.
    """
    bot = with_bot()
    channel = channel_row(username="pyjobs")
    await put(session_factory, channel)

    assert "ok" in await ask(api.channels.reset_cursor, channel.id)
    assert ("reset_channel_cursor", channel.id) in bot.calls


async def test_a_reset_cursor_for_a_missing_channel_is_refused(api, ask, with_bot):
    """Отмотать отметку у несуществующего канала не выходит.

    Кнопку жмут из карточки, а карточка могла устареть. Ответь мост успехом —
    человек ждал бы повторного разбора старых сообщений, которого не будет.
    """
    with_bot(cursor_reset=False)

    answer = await ask(api.channels.reset_cursor, 404)

    assert answer["detail"] == "Канал не найден."


async def test_deleting_a_channel_says_how_many_vacancies_lost_their_source(
    api, ask, with_bot, session_factory
):
    """Удаление называет, сколько вакансий осталось без источника.

    Вакансии при этом не удаляются — они просто перестают ссылаться на канал.
    Человеку это число говорит, чего он лишится, ещё до того, как заметит
    пустой столбец источника в списке.
    """
    bot = with_bot(detached=4)
    channel = channel_row(username="pyjobs")
    await put(session_factory, channel)

    answer = await ask(api.channels.delete, channel.id)

    assert answer["ok"]["detached_vacancies"] == 4
    assert ("delete_channel", channel.id) in bot.calls
