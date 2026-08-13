"""Следствия слотов канала, которым хватает одной базы.

Предмет — запись о канале: перечень, карточка, включение, заслон. Заведение
канала и обход его сообщений лежат своим файлом: там без бота ничего не выйдет.
"""

import json

from backend.models import TelegramChannel
from tests.dbio import all_rows, put
from tests.factories import channel_row, vacancy_row


async def test_the_list_counts_vacancies_and_shows_whether_it_is_on(
    main_api, watch, session_factory
):
    """Строка перечня несёт счёт вакансий и признак включения.

    По ним канал и оценивают: выключенный молчит, а включённый, не давший ни
    одной вакансии за месяц, — повод его выключить.
    """
    caught = watch(main_api.contacts_channel_list_loaded)
    channel = channel_row(username="pyjobs")
    await put(session_factory, channel)
    await put(session_factory, vacancy_row(source_channel_id=channel.id))

    main_api.request_contacts_channel_list(json.dumps({}))

    row = (await caught.next())["channels"][0]
    assert row["vacancy_count"] == 1
    assert row["is_active"] is True


async def test_a_card_of_a_missing_channel_is_refused_with_the_number(main_api, watch):
    """На пропавший канал отвечают отказом с его номером.

    Карточку открывают из перечня, который мог устареть: канал удалили или он
    ушёл в заслон вместе с чисткой. Без номера окно не поймёт, какую строку
    гасить, и оставит на экране запись, которой уже нет.
    """
    caught = watch(main_api.contacts_channel_detail_loaded)

    main_api.request_contacts_channel_detail(404)

    answer = await caught.next()
    assert answer["ok"] is False
    assert answer["channel_id"] == 404


async def test_only_this_channel_vacancies_are_shown(main_api, watch, session_factory):
    """В карточке видны вакансии только этого канала.

    По ним решают, стоит ли его держать включённым. Попади туда чужая —
    молчащий канал выглядел бы работающим, и выключить его было бы не за что.
    """
    caught = watch(main_api.contacts_channel_vacancies_loaded)
    mine = channel_row(username="pyjobs")
    other = channel_row(username="jsjobs")
    await put(session_factory, mine, other)
    await put(
        session_factory,
        vacancy_row(title="Моя", source_channel_id=mine.id),
        vacancy_row(title="Чужая", source_channel_id=other.id),
    )

    main_api.request_contacts_channel_vacancies(json.dumps({"channel_id": mine.id}))

    titles = [row["title"] for row in (await caught.next())["vacancies"]]
    assert titles == ["Моя"]


async def test_turning_a_channel_off_reaches_the_list(main_api, watch, session_factory):
    """Выключение видно в перечне, а не только в ответе.

    Выключенный канал перестаёт опрашиваться. Останься признак только в
    ответе, перечень показывал бы его работающим, и человек ждал бы от него
    вакансий, которых не будет.
    """
    done = watch(main_api.contacts_channel_action_done)
    listed = watch(main_api.contacts_channel_list_loaded)
    channel = channel_row(username="pyjobs")
    await put(session_factory, channel)

    main_api.set_channel_active(
        json.dumps({"channel_id": channel.id, "is_active": False})
    )
    assert (await done.next())["ok"] is True

    main_api.request_contacts_channel_list(json.dumps({}))
    assert (await listed.next())["channels"][0]["is_active"] is False


async def test_a_blacklisted_channel_cannot_be_turned_back_on(
    main_api, watch, session_factory
):
    """Занесённый в заслон канал включить нельзя, и об этом говорят словами.

    Заслон ставят, чтобы канал больше не читали. Пройди включение — канал
    вернулся бы в опрос молча, и заслон оказался бы отменён нажатием, которое
    про него ничего не знает.
    """
    caught = watch(main_api.contacts_channel_action_done)
    channel = channel_row(username="pyjobs")
    await put(session_factory, channel)

    main_api.contacts_add_channel_to_blacklist(channel.id)
    await caught.next()

    main_api.set_channel_active(
        json.dumps({"channel_id": channel.id, "is_active": True})
    )

    answer = await caught.next()
    assert answer["ok"] is False
    assert answer["error"] == "Канал в blacklist — нельзя включить."


async def test_blacklisting_sweeps_the_namesake_channel_too(
    main_api, watch, session_factory
):
    """Заслон гасит все каналы под этим написанием, а не только нажатый.

    Одно и то же написание в базе бывает дважды — канал завели повторно, а
    старую строку не убрали. Погаси заслон только нажатый, второй продолжил
    бы носить вакансии из того самого источника, от которого ограждались, и
    заметить это было бы нечем: в списке он выглядит включённым по своей
    воле.
    """
    done = watch(main_api.contacts_channel_action_done)
    clicked = channel_row(username="pyjobs", title="Питон-вакансии")
    namesake = channel_row(username="pyjobs", title="Он же, заведённый заново")
    await put(session_factory, clicked, namesake)

    main_api.contacts_add_channel_to_blacklist(clicked.id)
    await done.next()

    # Смотрим в базу, а не в список: показ списка сам чинит дрейф тем же
    # объявлением, и через него зелено было бы и без правки.
    rows = await all_rows(session_factory, TelegramChannel)
    assert [row.is_active for row in rows] == [False, False]


async def test_blacklisting_turns_the_channel_off_at_once(
    main_api, watch, session_factory
):
    """Заслон гасит канал сразу, а не оставляет включённым до перечитывания.

    Иначе между заслоном и следующим обходом канал успел бы принести ещё
    вакансий — ровно от них и ограждались.
    """
    done = watch(main_api.contacts_channel_action_done)
    shown = watch(main_api.contacts_channel_detail_loaded)
    channel = channel_row(username="pyjobs")
    await put(session_factory, channel)

    main_api.contacts_add_channel_to_blacklist(channel.id)
    answer = await done.next()
    assert answer["value"] == "@pyjobs"

    main_api.request_contacts_channel_detail(channel.id)
    card = await shown.next()
    assert card["is_active"] is False
    assert card["blacklist_value"] == "@pyjobs"


async def test_removing_the_blacklist_clears_the_card(main_api, watch, session_factory):
    """Снятый заслон виден в карточке: значения там больше нет."""
    done = watch(main_api.contacts_channel_action_done)
    shown = watch(main_api.contacts_channel_detail_loaded)
    channel = channel_row(username="pyjobs")
    await put(session_factory, channel)

    main_api.contacts_add_channel_to_blacklist(channel.id)
    await done.next()

    main_api.contacts_remove_channel_from_blacklist(channel.id)
    assert (await done.next())["updated"] == 1

    main_api.request_contacts_channel_detail(channel.id)
    assert (await shown.next())["blacklist_value"] is None


async def test_turning_all_on_leaves_the_blacklisted_ones_off(
    main_api, watch, session_factory
):
    """Сплошное включение обходит огороженные каналы стороной.

    Кнопкой «включить все» пользуются после долгого перерыва, не помня, кого
    и за что выключали. Включи она заслонённых — те вернулись бы в опрос без
    единого слова об этом.
    """
    done = watch(main_api.contacts_channel_action_done)
    listed = watch(main_api.contacts_channel_list_loaded)
    plain = channel_row(username="pyjobs")
    barred = channel_row(username="spam")
    await put(session_factory, plain, barred)

    main_api.contacts_add_channel_to_blacklist(barred.id)
    await done.next()

    # Оба гасим до сплошного включения: канал заводится уже включённым, и на
    # готовых умолчаниях тест зеленел бы, даже не включив ничего.
    main_api.set_channel_active(json.dumps({"channel_id": plain.id, "is_active": False}))
    assert (await done.next())["ok"] is True

    main_api.set_all_channels_active(json.dumps({"is_active": True}))
    assert (await done.next())["affected"] == 1

    main_api.request_contacts_channel_list(json.dumps({}))
    state = {row["username"]: row["is_active"] for row in (await listed.next())["channels"]}
    assert state == {"pyjobs": True, "spam": False}
