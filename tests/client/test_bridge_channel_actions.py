"""Следствия действий над каналом, которым нужен поднятый бот.

Предмет — то, что мост делает чужими руками: заводит канал по имени, гонит его
вне очереди, отматывает отметку прочитанного и удаляет. Всё это идёт в
Telegram, поэтому бот подделан.
"""

import json

from tests.dbio import put
from tests.factories import channel_row


async def test_a_name_that_is_not_a_channel_never_reaches_telegram(
    main_api, watch, with_bot
):
    """Нераспознанное имя отбивают до Telegram, назвав годные виды записи.

    Имя канала вставляют из чего попало — из ссылки, из пересланного письма,
    из адресной строки. Уйди мусор в сеть, ответом был бы отказ Telegram, из
    которого не видно, что чинить именно строку ввода.
    """
    caught = watch(main_api.contacts_channel_action_done)
    bot = with_bot()

    main_api.request_create_channel(json.dumps({"input": "не ссылка и не имя"}))

    answer = await caught.next()
    assert answer["ok"] is False
    assert "Поддерживаются форматы" in answer["error"]
    assert bot.calls == []


async def test_an_empty_name_is_refused_before_the_bot(main_api, watch, with_bot):
    """Пустое поле отбивают своими словами, а не молчанием."""
    caught = watch(main_api.contacts_channel_action_done)
    bot = with_bot()

    main_api.request_create_channel(json.dumps({"input": "   "}))

    assert (await caught.next())["error"] == "Укажите @username или ссылку на канал."
    assert bot.calls == []


async def test_a_link_arrives_at_the_bot_as_a_bare_name(main_api, watch, with_bot):
    """Из ссылки до бота доезжает одно имя, без адреса вокруг.

    Telegram спрашивают по имени; отправь ему целый адрес — канал не нашёлся
    бы, хотя человек ввёл верную ссылку.
    """
    caught = watch(main_api.contacts_channel_action_done)
    bot = with_bot(added=(7, "created"))

    main_api.request_create_channel(json.dumps({"input": "https://t.me/pyjobs"}))

    answer = await caught.next()
    assert answer["ok"] is True
    assert answer["channel_id"] == 7
    assert ("add_channel", "pyjobs") in bot.calls


async def test_a_channel_telegram_does_not_know_is_named_in_the_answer(
    main_api, watch, with_bot
):
    """Про ненайденный канал говорят его же именем.

    Ошибаются обычно в одной букве, и увидеть, каким именем искали, — самый
    короткий путь понять, где опечатка.
    """
    caught = watch(main_api.contacts_channel_action_done)
    with_bot(added=(None, "invalid"))

    main_api.request_create_channel(json.dumps({"input": "@pyjobz"}))

    answer = await caught.next()
    assert answer["ok"] is False
    assert "pyjobz" in answer["error"]


async def test_an_already_known_channel_is_not_an_error(main_api, watch, with_bot):
    """Второе заведение того же канала — не ошибка, а указание на прежний.

    Человек не помнит, заводил ли; ответь мост отказом — он решил бы, что
    канал недоступен, вместо того чтобы открыть уже готовую карточку.
    """
    caught = watch(main_api.contacts_channel_action_done)
    with_bot(added=(3, "exists"))

    main_api.request_create_channel(json.dumps({"input": "@pyjobs"}))

    answer = await caught.next()
    assert answer["ok"] is True
    assert answer["created"] is False
    assert answer["channel_id"] == 3


async def test_a_manual_walk_before_the_bot_is_up_is_refused_by_name(
    main_api, watch, session_factory
):
    """Ручной обход без бота отбивают словами про бота.

    Обход идёт в Telegram; без него объяснить человеку, почему кнопка не
    сработала, больше нечем.
    """
    caught = watch(main_api.contacts_channel_action_done)
    channel = channel_row(username="pyjobs")
    await put(session_factory, channel)

    main_api.request_channel_poll_now(channel.id)

    assert (await caught.next())["error"] == "Бот ещё не готов."


async def test_a_busy_walk_is_explained(main_api, watch, with_bot, session_factory):
    """Занятый обход объясняют, а не глотают.

    Место прогона одно на все каналы, и попасть на занятое — обычное дело.
    Промолчи мост — кнопка выглядела бы сломанной.
    """
    caught = watch(main_api.contacts_channel_action_done)
    with_bot(channel_poll="busy")
    channel = channel_row(username="pyjobs")
    await put(session_factory, channel)

    main_api.request_channel_poll_now(channel.id)

    answer = await caught.next()
    assert answer["ok"] is False
    assert answer["status"] == "busy"


async def test_an_unknown_walk_outcome_still_answers(
    main_api, watch, with_bot, session_factory
):
    """Незнакомый исход обхода тоже получает ответ.

    Исходы заводит бэкенд, и новый появится там раньше перевода здесь.
    Промолчи мост — кнопка осталась бы нажатой навсегда.
    """
    caught = watch(main_api.contacts_channel_action_done)
    with_bot(channel_poll="перегрев")
    channel = channel_row(username="pyjobs")
    await put(session_factory, channel)

    main_api.request_channel_poll_now(channel.id)

    answer = await caught.next()
    assert answer["ok"] is False
    assert answer["status"] == "перегрев"


async def test_a_finished_walk_answers_plainly(
    main_api, watch, with_bot, session_factory
):
    """Удавшийся обход отвечает без оговорок, и по этому ответу гаснет ожидание.

    Остальные исходы окно показывает сообщением, а этот — единственный, после
    которого список просто перечитывают. Не приди он, кнопка осталась бы
    нажатой до перезапуска.
    """
    caught = watch(main_api.contacts_channel_action_done)
    bot = with_bot()
    channel = channel_row(username="pyjobs")
    await put(session_factory, channel)

    main_api.request_channel_poll_now(channel.id)

    answer = await caught.next()
    assert answer["ok"] is True
    assert answer["status"] == "ok"
    assert ("poll_channel_now", channel.id) in bot.calls


async def test_a_reset_cursor_reaches_the_bot(main_api, watch, with_bot, session_factory):
    """Отматывание отметки доходит до бота вместе с номером канала.

    После него канал перечитывают с начала — это единственный способ вернуть
    пропущенные объявления. Не дойди вызов, кнопка отвечала бы успехом, а
    прежние сообщения так и остались бы непрочитанными.
    """
    caught = watch(main_api.contacts_channel_action_done)
    bot = with_bot()
    channel = channel_row(username="pyjobs")
    await put(session_factory, channel)

    main_api.request_channel_reset_cursor(channel.id)

    assert (await caught.next())["ok"] is True
    assert ("reset_channel_cursor", channel.id) in bot.calls


async def test_a_reset_cursor_for_a_missing_channel_is_refused(
    main_api, watch, with_bot
):
    """Отмотать отметку у несуществующего канала не выходит.

    Кнопку жмут из карточки, а карточка могла устареть. Ответь мост успехом —
    человек ждал бы повторного разбора старых сообщений, которого не будет.
    """
    caught = watch(main_api.contacts_channel_action_done)
    with_bot(cursor_reset=False)

    main_api.request_channel_reset_cursor(404)

    assert (await caught.next())["error"] == "Канал не найден."


async def test_deleting_a_channel_says_how_many_vacancies_lost_their_source(
    main_api, watch, with_bot, session_factory
):
    """Удаление называет, сколько вакансий осталось без источника.

    Вакансии при этом не удаляются — они просто перестают ссылаться на канал.
    Человеку это число говорит, чего он лишится, ещё до того, как заметит
    пустой столбец источника в списке.
    """
    caught = watch(main_api.contacts_channel_action_done)
    bot = with_bot(detached=4)
    channel = channel_row(username="pyjobs")
    await put(session_factory, channel)

    main_api.request_channel_delete(channel.id)

    answer = await caught.next()
    assert answer["ok"] is True
    assert answer["detached_vacancies"] == 4
    assert ("delete_channel", channel.id) in bot.calls
