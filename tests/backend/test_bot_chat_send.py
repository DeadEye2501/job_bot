"""Следствия отправки сообщения HR из вкладки «Контакты».

Здесь отказ — не тихое «не вышло», а объяснение словами: окно показывает
его подсказкой, и по ней пользователь понимает, что делать дальше. Поэтому
каждая причина названа отдельно, а не сведена к общей неудаче.

Сохранённая строка возвращается наружу: окно рисует её в переписке сразу,
не перечитывая список. Гонка со встречным обработчиком исходящих решается
в пользу уже сохранённого — иначе в переписке появилось бы два одинаковых
сообщения.
"""

import pytest

from backend.models import BotMode, Message
from tests.dbio import all_rows, only_row, put
from tests.factories import blacklist_row, message_row
from tests.fakes.telegram import SENT_AT


async def test_a_message_reaches_the_hr_and_the_chat(
    chatting, session_factory, sending_unlocked
):
    """Сообщение уходит HR и появляется в переписке.

    Возвращается сохранённая строка: окно рисует её сразу, не перечитывая
    переписку целиком.
    """
    bot, client, hr = await chatting()

    row = await bot.send_to_hr_chat(hr.id, "здравствуйте")

    assert client.outgoing == [("send_message", "maria", "здравствуйте")]
    assert row.is_incoming is False
    assert row.text == "здравствуйте"
    assert row.tg_message_id == client.last_message_id
    assert row.sent_at == SENT_AT
    assert (await only_row(session_factory, Message)).id == row.id


async def test_surrounding_whitespace_is_dropped(
    chatting, session_factory, sending_unlocked
):
    """Пробелы по краям обрезаются: их пользователь набрал не нарочно."""
    bot, client, hr = await chatting()

    row = await bot.send_to_hr_chat(hr.id, "  здравствуйте  ")

    assert client.outgoing == [("send_message", "maria", "здравствуйте")]
    assert row.text == "здравствуйте"


@pytest.mark.parametrize(
    "text", [pytest.param("", id="пусто"), pytest.param("   ", id="одни пробелы")]
)
async def test_an_empty_message_is_refused(
    chatting, session_factory, sending_unlocked, text
):
    """Пустое сообщение не уходит: отправлять нечего."""
    bot, client, hr = await chatting()

    with pytest.raises(RuntimeError, match="Пустое сообщение"):
        await bot.send_to_hr_chat(hr.id, text)

    assert client.outgoing == []


async def test_a_switched_off_bot_refuses_to_chat(chatting, session_factory):
    """Выключенный бот сообщений не шлёт и говорит, что включить."""
    bot, client, hr = await chatting(mode=BotMode.OFF)

    with pytest.raises(RuntimeError, match="Бот выключен"):
        await bot.send_to_hr_chat(hr.id, "здравствуйте")

    assert client.outgoing == []


async def test_the_send_guard_refuses_and_says_why(chatting, session_factory):
    """При включённой защите отправка отказывается и называет причину.

    Иначе разработчик, забывший про защиту, счёл бы молчание Telegram
    поломкой самой отправки.
    """
    bot, client, hr = await chatting()

    with pytest.raises(RuntimeError, match="защита от случайной отправки"):
        await bot.send_to_hr_chat(hr.id, "здравствуйте")

    assert client.outgoing == []


async def test_an_hr_without_an_address_is_refused_by_a_switched_off_bot_too(
    chatting, session_factory, sending_unlocked
):
    """У HR без адреса причина отказа одна, включён бот или нет.

    Тот же вопрос — можно ли писать этому HR — конвейер откликов задаёт
    своим набором заслонов, и на выключенном боте без адреса он называет
    «нет адресата». Два разных ответа на один вопрос значат, что заслоны
    разъехались, а пользователь по подсказке чинит не то.
    """
    bot, client, hr = await chatting(
        mode=BotMode.OFF, telegram_username=None, telegram_user_id=None
    )

    with pytest.raises(RuntimeError, match="нечем отправить"):
        await bot.send_to_hr_chat(hr.id, "здравствуйте")

    assert client.outgoing == []


async def test_a_blacklisted_hr_is_named_ahead_of_the_send_lock(
    chatting, session_factory
):
    """У HR из чёрного списка отказ называет список, а не замок отправки.

    Замок снимается одним переключателем, чёрный список — нет. Назови окно
    замок, и человек снимет его, чтобы упереться в то же самое.
    """
    await put(session_factory, blacklist_row("hr", "@maria"))
    bot, client, hr = await chatting(telegram_username="maria")

    with pytest.raises(RuntimeError, match="blacklist"):
        await bot.send_to_hr_chat(hr.id, "здравствуйте")

    assert client.outgoing == []


async def test_a_missing_hr_is_named_in_the_refusal(
    chatting, session_factory, sending_unlocked
):
    """Отказ по несуществующему HR называет, кого не нашли."""
    bot, client, _ = await chatting()

    with pytest.raises(RuntimeError, match="id=404"):
        await bot.send_to_hr_chat(404, "здравствуйте")

    assert client.outgoing == []


async def test_an_hr_without_an_address_is_refused(
    chatting, session_factory, sending_unlocked
):
    """HR без адреса получает отказ: отправлять некуда."""
    bot, client, hr = await chatting(
        telegram_username=None, telegram_user_id=None
    )

    with pytest.raises(RuntimeError, match="нечем отправить"):
        await bot.send_to_hr_chat(hr.id, "здравствуйте")

    assert client.outgoing == []


async def test_a_blacklisted_hr_is_refused_with_the_entry_named(
    chatting, session_factory, sending_unlocked
):
    """Отказ по чёрному списку называет запись, из-за которой отказал.

    По ней пользователь и найдёт, что убрать, если передумал.
    """
    await put(session_factory, blacklist_row("hr", "@maria"))
    bot, client, hr = await chatting()

    with pytest.raises(RuntimeError, match="@maria"):
        await bot.send_to_hr_chat(hr.id, "здравствуйте")

    assert client.outgoing == []


async def test_a_message_the_handler_already_saved_is_not_doubled(
    chatting, session_factory, sending_unlocked
):
    """Сообщение, которое успел сохранить обработчик, не удваивается.

    Отправка и обработчик исходящих идут на одном клиенте и приходят к
    одному сообщению; два одинаковых пузыря в переписке — то, что видит
    пользователь, если гонку не разобрать.
    """
    bot, client, hr = await chatting()

    async def saved_by_the_handler(answer):
        await put(
            session_factory,
            message_row(
                hr_id=hr.id,
                is_incoming=False,
                tg_message_id=answer.id,
                text="сохранено обработчиком",
            ),
        )

    client.on_send = saved_by_the_handler

    row = await bot.send_to_hr_chat(hr.id, "здравствуйте")

    assert row.text == "сохранено обработчиком"
    assert len(await all_rows(session_factory, Message)) == 1
