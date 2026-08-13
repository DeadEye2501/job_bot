"""Следствия слотов чёрного списка: записи заслона и весь их перечень.

Заслон, поставленный из карточки HR, компании или канала, лежит с ними: там
его ставят одним нажатием и по другому поводу. Подсказки к форме заведения —
своим файлом: они ничего не заводят, а только смотрят на уже известных.
"""

import json

from tests.dbio import put
from tests.factories import blacklist_row, channel_row, company_row


async def test_the_list_carries_kind_value_and_whether_it_is_on(
    main_api, watch, session_factory
):
    """Строка перечня несёт род, значение и признак действия.

    Погашенная запись остаётся в перечне нарочно — её заводили не зря и ещё
    вернут. Пропади признак, погашенная выглядела бы работающей, и человек
    считал бы себя огороженным.
    """
    caught = watch(main_api.contacts_blacklist_list_loaded)
    await put(session_factory, blacklist_row("keyword", "казино", active=False))

    main_api.request_contacts_blacklist_list()

    row = (await caught.next())["items"][0]
    assert row["kind"] == "keyword"
    assert row["value"] == "казино"
    assert row["active"] is False


async def test_an_unknown_kind_is_refused(main_api, watch):
    """Неизвестный род записи не заводят.

    Родов четыре, и по роду идёт сверка: запись с выдуманным родом не
    совпала бы ни с чем и молча ничего не ограждала бы.
    """
    caught = watch(main_api.contacts_blacklist_action_done)

    main_api.request_create_blacklist(
        json.dumps({"kind": "выдуманный", "value": "что-то"})
    )

    answer = await caught.next()
    assert answer["ok"] is False
    assert answer["error"] == "Неверный тип записи."


async def test_an_empty_value_is_refused(main_api, watch):
    """Пустое значение не заводят: сверять будет нечего."""
    caught = watch(main_api.contacts_blacklist_action_done)

    main_api.request_create_blacklist(json.dumps({"kind": "keyword", "value": "   "}))

    answer = await caught.next()
    assert answer["ok"] is False
    assert answer["error"] == "Значение не может быть пустым."


async def test_the_same_entry_twice_does_not_make_a_second_one(
    main_api, watch, session_factory
):
    """Повторное заведение не плодит вторую запись, а признаётся в первой.

    Заводят их и из перечня, и из карточки, не помня прежнего. Заведись
    вторая — гашение одной оставило бы вторую работать, и человек не понял бы,
    почему заслон держится после снятия.
    """
    done = watch(main_api.contacts_blacklist_action_done)
    listed = watch(main_api.contacts_blacklist_list_loaded)

    main_api.request_create_blacklist(json.dumps({"kind": "keyword", "value": "казино"}))
    assert (await done.next())["created"] is True

    main_api.request_create_blacklist(json.dumps({"kind": "keyword", "value": "казино"}))
    assert (await done.next())["created"] is False

    main_api.request_contacts_blacklist_list()
    assert len((await listed.next())["items"]) == 1


async def test_repeating_a_switched_off_entry_brings_it_back(
    main_api, watch, session_factory
):
    """Заведение погашенной записи заново её оживляет.

    Человек не помнит, что уже гасил её; он просто заводит снова. Останься
    запись погашенной, заслон не работал бы, а окно отвечало бы успехом.
    """
    caught = watch(main_api.contacts_blacklist_action_done)
    entry = blacklist_row("keyword", "казино", active=False)
    await put(session_factory, entry)

    main_api.request_create_blacklist(json.dumps({"kind": "keyword", "value": "казино"}))
    assert (await caught.next())["created"] is False

    listed = watch(main_api.contacts_blacklist_list_loaded)
    main_api.request_contacts_blacklist_list()
    assert (await listed.next())["items"][0]["active"] is True


async def test_barring_a_channel_switches_it_off_right_away(
    main_api, watch, session_factory
):
    """Запись про канал гасит совпавшие каналы и говорит, сколько погасила.

    Иначе канал остался бы в опросе до следующего перечитывания списка и
    успел бы принести ещё объявлений — ровно от них и ограждались.
    """
    caught = watch(main_api.contacts_blacklist_action_done)
    listed = watch(main_api.contacts_channel_list_loaded)
    await put(session_factory, channel_row(username="spam", title="Спам"))

    main_api.request_create_blacklist(
        json.dumps({"kind": "channel", "value": "@spam"})
    )

    answer = await caught.next()
    assert answer["ok"] is True
    assert answer["deactivated_channels"] == 1

    main_api.request_contacts_channel_list(json.dumps({}))
    assert (await listed.next())["channels"][0]["is_active"] is False


async def test_an_update_without_either_field_is_refused(
    main_api, watch, session_factory
):
    """Правку, не назвавшую ни значения, ни причины, отбивают.

    Править нечего, а ответ об успехе окно приняло бы за сохранение и
    показало бы новое состояние, которого в записи нет.
    """
    caught = watch(main_api.contacts_blacklist_action_done)
    entry = blacklist_row("keyword", "казино")
    await put(session_factory, entry)

    main_api.update_blacklist(json.dumps({"id": entry.id}))

    answer = await caught.next()
    assert answer["ok"] is False
    assert "value / reason" in answer["error"]


async def test_an_update_to_an_empty_value_is_refused(
    main_api, watch, session_factory
):
    """Значение нельзя стереть правкой — сверять станет нечем."""
    caught = watch(main_api.contacts_blacklist_action_done)
    entry = blacklist_row("keyword", "казино")
    await put(session_factory, entry)

    main_api.update_blacklist(json.dumps({"id": entry.id, "value": "  "}))

    answer = await caught.next()
    assert answer["ok"] is False
    assert answer["error"] == "Значение не может быть пустым."


async def test_a_switched_off_entry_stays_in_the_list(
    main_api, watch, session_factory
):
    """Погашенная запись остаётся в перечне, но помечена погашенной.

    Гасят её, чтобы вернуть потом, — удаление для этого есть отдельное.
    Пропади она из перечня, включить её обратно было бы нечем.
    """
    done = watch(main_api.contacts_blacklist_action_done)
    listed = watch(main_api.contacts_blacklist_list_loaded)
    entry = blacklist_row("keyword", "казино")
    await put(session_factory, entry)

    main_api.set_blacklist_active(json.dumps({"id": entry.id, "active": False}))
    assert (await done.next())["ok"] is True

    main_api.request_contacts_blacklist_list()
    items = (await listed.next())["items"]
    assert len(items) == 1
    assert items[0]["active"] is False


async def test_deleting_a_missing_entry_is_refused(main_api, watch):
    """Удаление несуществующей записи отбивают, а не считают удавшимся."""
    caught = watch(main_api.contacts_blacklist_action_done)

    main_api.delete_blacklist(404)

    answer = await caught.next()
    assert answer["ok"] is False
    assert answer["error"] == "Запись не найдена."


async def test_a_deleted_entry_leaves_the_list(main_api, watch, session_factory):
    """Удалённая запись исчезает из перечня насовсем."""
    done = watch(main_api.contacts_blacklist_action_done)
    listed = watch(main_api.contacts_blacklist_list_loaded)
    entry = blacklist_row("company", "Рога")
    await put(session_factory, entry, company_row(name="Рога"))

    main_api.delete_blacklist(entry.id)
    assert (await done.next())["ok"] is True

    main_api.request_contacts_blacklist_list()
    assert (await listed.next())["items"] == []
