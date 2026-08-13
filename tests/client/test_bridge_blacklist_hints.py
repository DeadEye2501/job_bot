"""Следствия подсказок к форме заслона: кого окно предлагает выбрать.

Предмет отделён от самих записей: подсказки ничего не заводят и не гасят, они
только смотрят на уже заведённых людей, компании и каналы. Рядом с ними
значение всегда можно вписать руками — того, кто ещё не попадался, в базе нет.
"""

from tests.dbio import put
from tests.factories import channel_row, hr_row


async def test_hints_offer_only_those_who_can_be_barred(
    api, ask, session_factory
):
    """В подсказках только те, кого есть чем огородить.

    Заслон сверяется по нику или номеру учётной записи. Предложи окно
    человека без того и другого — запись завелась бы пустой и не сработала
    бы ни разу.
    """
    await put(
        session_factory,
        hr_row(name="Мария", telegram_username="maria"),
        hr_row(name="Безымянный", telegram_username=None, telegram_user_id=None),
    )

    answer = await ask(api.blacklist.candidates, "hr")

    values = [row["value"] for row in answer["ok"]["items"]]
    assert values == ["@maria"]


async def test_hints_echo_the_kind_they_were_asked_for(
    api, ask, session_factory
):
    """Подсказки возвращаются вместе с родом, о котором спрашивали.

    Род переключают быстрее, чем приходит ответ. Без эха окно приняло бы
    ответ про каналы за ответ про компании и подставило бы не те значения.
    """
    await put(session_factory, channel_row(username="pyjobs", title="Питон-вакансии"))

    answer = await ask(api.blacklist.candidates, "channel")

    assert answer["ok"]["kind"] == "channel"
    assert [row["value"] for row in answer["ok"]["items"]] == ["@pyjobs"]


async def test_a_keyword_has_no_hints_and_that_is_not_a_failure(api, ask):
    """У слова подсказок нет вовсе, и это не ошибка.

    Слово вписывают руками — его неоткуда взять. Ответь мост отказом, окно
    показало бы сообщение о поломке на обычном переключении рода.
    """
    answer = await ask(api.blacklist.candidates, "keyword")

    assert answer["ok"]["items"] == []
