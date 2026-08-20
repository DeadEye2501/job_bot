"""Следствия действий над каналом, которым нужен поднятый бот.

Предмет — то, что мост делает чужими руками: заводит канал по имени, гонит его
вне очереди, отматывает отметку прочитанного и удаляет. Всё это идёт в
Telegram, поэтому бот подделан.
"""

from backend.models import TelegramChannel, Vacancy
from tests.dbio import only_row, put
from tests.factories import channel_row, vacancy_row


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


async def test_a_busy_walk_is_explained(api, ask, with_bot, told, session_factory):
    """Занятый обход объясняют, а не глотают.

    Место прогона одно на все каналы, и попасть на занятое — обычное дело.
    Промолчи мост — кнопка выглядела бы сломанной.
    """
    with_bot(channel_poll="busy")
    channel = channel_row(username="pyjobs")
    await put(session_factory, channel)

    await ask(api.channels.poll_now, channel.id)

    assert await told() == {
        "message": "Уже идёт другой цикл, попробуйте позже.",
        "danger": True,
    }


async def test_an_unknown_walk_outcome_still_answers(
    api, ask, with_bot, told, session_factory
):
    """Незнакомый исход обхода тоже получает ответ.

    Исходы заводит бэкенд, и новый появится там раньше перевода здесь.
    Промолчи мост — человек остался бы без ответа вовсе.
    """
    with_bot(channel_poll="перегрев")
    channel = channel_row(username="pyjobs")
    await put(session_factory, channel)

    await ask(api.channels.poll_now, channel.id)

    said = await told()
    assert said["danger"] is True
    assert said["message"] == "Не удалось прогнать канал — см. логи."


async def test_a_walk_answers_before_it_walks(
    api, ask, with_bot, told, session_factory
):
    """Ответ приходит сразу, а исход — вестью, когда обход кончится.

    Обход канала — это до пяти обращений к модели на каждый новый пост.
    Дождись мост его конца, окно висело бы всё это время, а человек не знал бы,
    нажалась ли кнопка вообще.
    """
    bot = with_bot()
    channel = channel_row(username="pyjobs")
    await put(session_factory, channel)

    answer = await ask(api.channels.poll_now, channel.id)

    assert answer["ok"] == {
        "started": True,
        "channel_id": channel.id,
        "action": "poll_now",
    }
    assert await told() == {"message": "Канал прогнан.", "danger": False}
    assert ("poll_channel_now", channel.id) in bot.calls


async def test_a_reset_cursor_clears_the_mark_without_the_bot(
    api, ask, session_factory
):
    """Отметка прочитанного сбрасывается и до входа в Telegram.

    Это одна правка строки в базе, и бот ей не нужен вовсе: запри её на
    поднятого бота — кнопка отказывала бы там, где работа ей по силам.
    """
    channel = channel_row(username="pyjobs", last_processed_msg_id=500)
    await put(session_factory, channel)

    assert "ok" in await ask(api.channels.reset_cursor, channel.id)

    saved = await only_row(session_factory, TelegramChannel)
    assert saved.last_processed_msg_id is None


async def test_a_reset_cursor_for_a_missing_channel_is_refused(api, ask):
    """Отмотать отметку у несуществующего канала не выходит.

    Кнопку жмут из карточки, а карточка могла устареть. Ответь мост успехом —
    человек ждал бы повторного разбора старых сообщений, которого не будет.
    """
    answer = await ask(api.channels.reset_cursor, 404)

    assert answer["detail"] == "Канал не найден."


async def test_a_channel_is_deleted_without_the_bot(api, ask, session_factory):
    """Канал сносится и до входа в Telegram.

    Это одна правка строки в базе — ровно как отмотка отметки прочитанного,
    которая рядом и которая бота не требует. Запертая на поднятого бота кнопка
    отказывала бы человеку, разбирающему список каналов на ненастроенном
    приложении, — а разбирают его как раз тогда.
    """
    channel = channel_row(username="pyjobs")
    await put(session_factory, channel)

    answer = await ask(api.channels.delete, channel.id)

    assert "ok" in answer
    assert await only_row(session_factory, TelegramChannel) is None


async def test_the_vacancies_of_a_deleted_channel_survive_it(
    api, ask, session_factory
):
    """Вакансии переживают свой канал, теряя только ссылку на источник.

    Снеси их мост заодно — человек лишился бы всего, что канал успел принести,
    и вернуть это было бы нечем: в Telegram посты доступны, но глубже
    `backfill_limit` за ними никто не пойдёт.
    """
    channel = channel_row(username="pyjobs")
    await put(session_factory, channel)
    await put(
        session_factory,
        vacancy_row(title="Уцелеет", source_channel_id=channel.id),
    )

    assert "ok" in await ask(api.channels.delete, channel.id)

    survivor = await only_row(session_factory, Vacancy)
    assert survivor.title == "Уцелеет"
    assert survivor.source_channel_id is None
