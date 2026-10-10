"""Случаи, когда отклик не отправляется и не засчитывается.

Отказ здесь означает больше, чем «письмо не ушло»: вакансия остаётся в
прежнем статусе, и следующая попытка — ручная или очередная авто — пройдёт
заново. Поэтому отказ и успех различаются не только в Telegram, но и в базе.

Три причины отказа: у HR нет адреса, бот выключен, HR в чёрном списке.
Чёрный список проверяется прямо перед отправкой нарочно: между разбором
вакансии и готовым письмом проходит время на языковую модель, и попасть
туда HR успевает как раз в этот промежуток.
"""

import pytest

from backend.bot import can_send
from backend.models import BotMode, Message, Vacancy, VacancyEvent, VacancyStatus
from tests.dbio import all_rows, only_row, put
from tests.factories import blacklist_row, hr_row


async def test_an_hr_without_an_address_is_not_written_to(
    ready_to_send, session_factory, outbox
):
    """HR без адреса не получает письма, и отклик не засчитывается.

    Отправлять некуда, а зачесть отклик значило бы навсегда закрыть
    вакансию от следующей попытки.
    """
    bot, saved_hr, vacancy = await ready_to_send(
        hr=hr_row(telegram_username=None, telegram_user_id=None)
    )

    assert await bot.send(saved_hr, "письмо", vacancy_id=vacancy.id) is False

    assert outbox.sent == []
    assert (await only_row(session_factory, Vacancy)).status is VacancyStatus.NEW


async def test_a_switched_off_bot_still_writes_what_the_person_asked(
    ready_to_send, outbox
):
    """Режим — про автоматику, а не про то, что человек нажал сам: в Off отклик
    по кнопке из окна уходит. Человек знает, что нажимает."""
    bot, saved_hr, vacancy = await ready_to_send(mode=BotMode.OFF)

    assert await bot.send(saved_hr, "письмо", vacancy_id=vacancy.id) is True

    assert len(outbox.sent) == 1


@pytest.mark.parametrize(
    ("value", "hr_fields"),
    [
        pytest.param(
            "@maria",
            {"telegram_username": "maria", "telegram_user_id": None},
            id="по имени",
        ),
        pytest.param(
            "user_id:777",
            {"telegram_username": None, "telegram_user_id": 777},
            id="по номеру",
        ),
    ],
)
async def test_a_blacklisted_hr_is_not_written_to(
    ready_to_send, session_factory, outbox, value, hr_fields
):
    """HR из чёрного списка письма не получает, и отклик не засчитывается.

    Список проверяется прямо перед отправкой: между разбором вакансии и
    готовым письмом проходит время на языковую модель, и попасть в список
    HR успевает как раз тогда.
    """
    await put(session_factory, blacklist_row("hr", value))
    bot, saved_hr, vacancy = await ready_to_send(hr=hr_row(**hr_fields))

    assert await bot.send(saved_hr, "письмо", vacancy_id=vacancy.id) is False

    assert outbox.sent == []
    assert (await only_row(session_factory, Vacancy)).status is VacancyStatus.NEW


async def test_an_unknown_refusal_does_not_count_as_a_sent_application(
    ready_to_send, session_factory, outbox, monkeypatch
):
    """Незнакомая причина отказа отклик не засчитывает.

    Заглушают отправку ровно два замка, и оба названы поимённо. Причина, о
    которой отправка не знает, — это причина, заведённая позже; сочти её
    заглушкой, и вакансия пометится откликнутой без письма, то есть закроется
    от следующей попытки навсегда.
    """
    bot, saved_hr, vacancy = await ready_to_send()

    async def refuse_for_a_new_reason(bot, hr):
        return can_send.SendPermission(target=1, refusal="причина из будущего")

    monkeypatch.setattr(can_send, "can_send_to_hr", refuse_for_a_new_reason)

    assert await bot.send(saved_hr, "письмо", vacancy_id=vacancy.id) is False

    assert outbox.sent == []
    assert (await only_row(session_factory, Vacancy)).status is VacancyStatus.NEW


async def test_a_refusal_leaves_no_trace_in_the_history(
    ready_to_send, session_factory, outbox
):
    """Отказ не оставляет ни сообщения, ни отметки в истории вакансии.

    Строка «отклик отправлен» в ленте означала бы для пользователя, что
    ход сделан, и он не стал бы отправлять письмо руками.
    """
    bot, saved_hr, vacancy = await ready_to_send(
        hr=hr_row(telegram_username=None, telegram_user_id=None)
    )

    await bot.send(saved_hr, "письмо", vacancy_id=vacancy.id)

    assert await all_rows(session_factory, Message) == []
    assert await all_rows(session_factory, VacancyEvent) == []
