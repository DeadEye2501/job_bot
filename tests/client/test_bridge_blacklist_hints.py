"""Следствия подсказок к форме заслона: кого окно предлагает выбрать.

Предмет отделён от самих записей: подсказки ничего не заводят и не гасят, они
только смотрят на уже заведённых людей, компании и каналы. Рядом с ними
значение всегда можно вписать руками — того, кто ещё не попадался, в базе нет.
"""

from tests.dbio import put
from tests.factories import channel_row, hr_row


async def test_hints_offer_only_those_who_can_be_barred(
    main_api, watch, session_factory
):
    """В подсказках только те, кого есть чем огородить.

    Заслон сверяется по нику или номеру учётной записи. Предложи окно
    человека без того и другого — запись завелась бы пустой и не сработала
    бы ни разу.
    """
    caught = watch(main_api.contacts_blacklist_candidates_loaded)
    await put(
        session_factory,
        hr_row(name="Мария", telegram_username="maria"),
        hr_row(name="Безымянный", telegram_username=None, telegram_user_id=None),
    )

    main_api.request_blacklist_candidates("hr")

    values = [row["value"] for row in (await caught.next())["items"]]
    assert values == ["@maria"]


async def test_hints_echo_the_kind_they_were_asked_for(
    main_api, watch, session_factory
):
    """Подсказки возвращаются вместе с родом, о котором спрашивали.

    Род переключают быстрее, чем приходит ответ. Без эха окно приняло бы
    ответ про каналы за ответ про компании и подставило бы не те значения.
    """
    caught = watch(main_api.contacts_blacklist_candidates_loaded)
    await put(session_factory, channel_row(username="pyjobs", title="Питон-вакансии"))

    main_api.request_blacklist_candidates("channel")

    answer = await caught.next()
    assert answer["kind"] == "channel"
    assert [row["value"] for row in answer["items"]] == ["@pyjobs"]


async def test_a_keyword_has_no_hints_and_that_is_not_a_failure(main_api, watch):
    """У слова подсказок нет вовсе, и это не ошибка.

    Слово вписывают руками — его неоткуда взять. Ответь мост отказом, окно
    показало бы сообщение о поломке на обычном переключении рода.
    """
    caught = watch(main_api.contacts_blacklist_candidates_loaded)

    main_api.request_blacklist_candidates("keyword")

    assert (await caught.next())["items"] == []
