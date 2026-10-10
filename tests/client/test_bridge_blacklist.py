"""Следствия слотов чёрного списка: записи заслона и весь их перечень.

Заслон, поставленный из карточки HR, компании или канала, лежит с ними: там
его ставят одним нажатием и по другому поводу. Подсказки к форме заведения —
своим файлом: они ничего не заводят, а только смотрят на уже известных.
"""

from backend.models import TelegramChannel
from tests.dbio import all_rows, put
from tests.factories import blacklist_row, channel_row, company_row


async def test_the_list_carries_kind_value_and_whether_it_is_on(
    api, ask, session_factory
):
    """Строка перечня несёт род, значение и признак действия.

    Погашенная запись остаётся в перечне нарочно — её заводили не зря и ещё
    вернут. Пропади признак, погашенная выглядела бы работающей, и человек
    считал бы себя огороженным.
    """
    await put(session_factory, blacklist_row("keyword", "казино", active=False))

    answer = await ask(api.blacklist.list)

    row = answer["ok"]["items"][0]
    assert row["kind"] == "keyword"
    assert row["value"] == "казино"
    assert row["active"] is False


async def test_an_unknown_kind_is_refused(api, ask):
    """Неизвестный род записи не заводят.

    Родов четыре, и по роду идёт сверка: запись с выдуманным родом не
    совпала бы ни с чем и молча ничего не ограждала бы.
    """
    answer = await ask(
        api.blacklist.create, {"kind": "выдуманный", "value": "что-то"}
    )

    assert answer["fail"] == "denied"
    assert answer["detail"] == "Неверный тип записи."


async def test_an_empty_value_is_refused(api, ask):
    """Пустое значение не заводят: сверять будет нечего."""
    answer = await ask(api.blacklist.create, {"kind": "keyword", "value": "   "})

    assert answer["fail"] == "denied"
    assert answer["detail"] == "Значение не может быть пустым."


async def test_the_same_entry_twice_does_not_make_a_second_one(
    api, ask
):
    """Повторное заведение не плодит вторую запись, а признаётся в первой.

    Заводят их и из перечня, и из карточки, не помня прежнего. Заведись
    вторая — гашение одной оставило бы вторую работать, и человек не понял бы,
    почему заслон держится после снятия.
    """
    first = await ask(api.blacklist.create, {"kind": "keyword", "value": "казино"})
    assert first["ok"]["created"] is True

    again = await ask(api.blacklist.create, {"kind": "keyword", "value": "казино"})
    assert again["ok"]["created"] is False

    listed = await ask(api.blacklist.list)
    assert len(listed["ok"]["items"]) == 1


async def test_repeating_a_switched_off_entry_brings_it_back(
    api, ask, session_factory
):
    """Заведение погашенной записи заново её оживляет.

    Человек не помнит, что уже гасил её; он просто заводит снова. Останься
    запись погашенной, заслон не работал бы, а окно отвечало бы успехом.
    """
    entry = blacklist_row("keyword", "казино", active=False)
    await put(session_factory, entry)

    answer = await ask(api.blacklist.create, {"kind": "keyword", "value": "казино"})
    assert answer["ok"]["created"] is False

    listed = await ask(api.blacklist.list)
    assert listed["ok"]["items"][0]["active"] is True


async def test_barring_a_channel_switches_it_off_right_away(
    api, ask, session_factory
):
    """Запись про канал гасит совпавшие каналы сразу.

    Иначе канал остался бы в опросе до следующего перечитывания списка и
    успел бы принести ещё объявлений — ровно от них и ограждались. Смотрим в
    базу, а не в список: показ списка чинит дрейф сам, и через него зелено
    было бы и без правила.
    """
    await put(session_factory, channel_row(username="spam", title="Спам"))

    answer = await ask(api.blacklist.create, {"kind": "channel", "value": "@spam"})

    assert "ok" in answer

    rows = await all_rows(session_factory, TelegramChannel)
    assert [row.is_active for row in rows] == [False]


async def test_an_update_without_either_field_is_refused(
    api, ask, session_factory
):
    """Правку, не назвавшую ни значения, ни причины, отбивают.

    Править нечего, а ответ об успехе окно приняло бы за сохранение и
    показало бы новое состояние, которого в записи нет.
    """
    entry = blacklist_row("keyword", "казино")
    await put(session_factory, entry)

    answer = await ask(api.blacklist.update, {"id": entry.id})

    assert answer["fail"] == "fields"
    assert "value / reason" in answer["detail"]


async def test_an_update_to_an_empty_value_is_refused(
    api, ask, session_factory
):
    """Значение нельзя стереть правкой — сверять станет нечем."""
    entry = blacklist_row("keyword", "казино")
    await put(session_factory, entry)

    answer = await ask(api.blacklist.update, {"id": entry.id, "value": "  "})

    assert answer["fail"] == "denied"
    assert answer["detail"] == "Значение не может быть пустым."


async def test_a_switched_off_entry_stays_in_the_list(
    api, ask, session_factory
):
    """Погашенная запись остаётся в перечне, но помечена погашенной.

    Гасят её, чтобы вернуть потом, — удаление для этого есть отдельное.
    Пропади она из перечня, включить её обратно было бы нечем.
    """
    entry = blacklist_row("keyword", "казино")
    await put(session_factory, entry)

    switched = await ask(api.blacklist.set_active, {"id": entry.id, "active": False})
    assert "ok" in switched

    listed = await ask(api.blacklist.list)
    items = listed["ok"]["items"]
    assert len(items) == 1
    assert items[0]["active"] is False


async def test_deleting_a_missing_entry_is_refused(api, ask):
    """Удаление несуществующей записи отбивают, а не считают удавшимся."""
    answer = await ask(api.blacklist.delete, 404)

    assert answer["fail"] == "denied"
    assert answer["detail"] == "Запись не найдена."


async def test_a_deleted_entry_leaves_the_list(api, ask, session_factory):
    """Удалённая запись исчезает из перечня насовсем."""
    entry = blacklist_row("company", "Рога")
    await put(session_factory, entry, company_row(name="Рога"))

    answer = await ask(api.blacklist.delete, entry.id)
    assert "ok" in answer

    listed = await ask(api.blacklist.list)
    assert listed["ok"]["items"] == []


async def test_switching_a_barred_row_back_on_stops_its_channel(
    api, ask, session_factory
):
    """Возвращённая в отсев запись гасит канал так же, как заведённая.

    Отметку в списке снимают и возвращают тумблером, и до этого правило
    держали только заведение и показ списка: канал, отсеянный тумблером,
    продолжал носить вакансии до ближайшего открытия экрана каналов — а
    человек считал, что оградился.
    """
    channel = channel_row(username="spam", title="Спам")
    row = blacklist_row(kind="channel", value="@spam", active=False)
    await put(session_factory, channel, row)

    answer = await ask(api.blacklist.set_active, {"id": row.id, "active": True})

    assert "ok" in answer
    rows = await all_rows(session_factory, TelegramChannel)
    assert [one.is_active for one in rows] == [False]


async def test_a_new_entry_tells_the_lists_to_reread_themselves(api, ask, hub):
    """Заведённая запись кладёт в очередь весть, что списки устарели.

    Отметка отсева запечена в строках людей, компаний и каналов: не узнав про
    новую запись, соседние экраны показывали бы человека незаблокированным до
    следующей правки руками.

    Красной фазы у этого сторожа не было — оповещение дописано вместе с
    переездом домена, и доверие оно заслужит итоговым проходом.
    """
    await ask(api.blacklist.create, {"kind": "keyword", "value": "казино"})

    news = await hub.events.take(after=0, timeout=0.01)

    assert [one["kind"] for one in news["events"]] == ["contacts_lists_changed"]


async def test_an_aggregator_entry_is_stored_as_its_host(api, ask):
    await ask(api.blacklist.create, {"kind": "aggregator", "value": "https://www.Site.test/jobs"})

    listed = (await ask(api.blacklist.list))["ok"]["items"]

    assert [(row["kind"], row["value"]) for row in listed] == [("aggregator", "site.test")]


async def test_an_aggregator_entry_without_a_host_is_refused(api, ask):
    answer = await ask(api.blacklist.create, {"kind": "aggregator", "value": "https://"})

    assert (answer["fail"], answer["detail"]) == ("denied", "Адрес не похож на сайт")
