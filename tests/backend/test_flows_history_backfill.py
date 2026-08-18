"""Следствия догона переписки с одним HR.

Пока приложение закрыто, разговор продолжается: HR пишет, пользователь
отвечает с телефона. Догон вытягивает у Telegram хвост переписки и в обе
стороны — иначе в окне видна половина разговора, а вторая только на телефоне.

Порядок обратный: Telegram отдаёт свежее первым, а в переписку надо класть
старое первым, иначе лента окна перевернётся.

Сверка удалённого — предмет соседнего файла, `test_flows_backfill_deletes.py`.
"""

import logging

from pyrogram.errors import FloodWait, PeerIdInvalid

from backend.flows.dm_backfill import backfill_hr_dm_history
from backend.models import HR, Message
from tests.backend.fixtures.backfill import catch_up as _catch_up, ours as _ours, theirs as _theirs
from tests.dbio import all_rows, only_row, put
from tests.factories import hr_row, message_row
from tests.fakes.telegram import FakeTelegramClient, photo


async def test_the_missed_conversation_lands_in_the_chat(
    known_hr, session_factory
):
    """Пропущенная переписка попадает в окно в обе стороны.

    Без исходящих видна половина разговора, и пользователь отвечает
    второй раз на то, что уже ответил с телефона.
    """
    client = FakeTelegramClient()
    client.history = [_theirs(12, "и ещё"), _ours(11, "мой ответ"), _theirs(10, "привет")]

    await _catch_up(client, known_hr, session_factory)

    saved = await all_rows(session_factory, Message)
    assert [(m.tg_message_id, m.is_incoming) for m in saved] == [
        (10, True),
        (11, False),
        (12, True),
    ]


async def test_the_oldest_message_is_saved_first(known_hr, session_factory):
    """Старое сохраняется раньше свежего, хотя Telegram отдаёт наоборот.

    Порядок строк — это порядок ленты в окне; сохранив как пришло,
    переписку показали бы вверх ногами.
    """
    client = FakeTelegramClient()
    client.history = [_theirs(12, "последнее"), _theirs(10, "первое")]

    await _catch_up(client, known_hr, session_factory)

    saved = await all_rows(session_factory, Message)
    assert [m.text for m in saved] == ["первое", "последнее"]


async def test_an_hr_without_an_address_is_skipped(session_factory):
    """У HR без адреса догонять нечего, и Telegram не спрашивают."""
    await put(session_factory, hr_row(telegram_username=None, telegram_user_id=None))
    hr = await only_row(session_factory, HR)
    client = FakeTelegramClient()

    await _catch_up(client, hr, session_factory)

    assert client.history_calls == []


async def test_an_already_saved_message_is_not_doubled(known_hr, session_factory):
    """Уже сохранённое сообщение вторым не пишется."""
    await put(
        session_factory,
        message_row(
            hr_id=known_hr.id, is_incoming=False, tg_message_id=11, text="уже было"
        ),
    )
    client = FakeTelegramClient()
    client.history = [_ours(11, "мой ответ")]

    await _catch_up(client, known_hr, session_factory)

    assert [m.text for m in await all_rows(session_factory, Message)] == ["уже было"]


async def test_an_already_saved_attachment_is_not_downloaded_again(
    known_hr, session_factory
):
    """Вложение уже сохранённого исходящего второй раз не качают.

    Догон проходит по всей доступной истории при каждом запуске и почти
    всегда видит уже записанное. Путь в кэше собран из номера сообщения,
    то есть повторная загрузка целится в тот же файл, который в это время
    может читать окно, — и оставляет его рваным.
    """
    await put(
        session_factory,
        message_row(
            hr_id=known_hr.id, is_incoming=False, tg_message_id=11, text=""
        ),
    )
    client = FakeTelegramClient()
    client.history = [_ours(11, None, photo=photo(big_file_id="big"))]

    await _catch_up(client, known_hr, session_factory)

    assert client.download_calls == []


async def test_nothing_but_duplicates_means_the_window_is_not_told(
    known_hr, session_factory
):
    """Догон, встретивший одни повторы, окно не дёргает.

    Он проходит по всей доступной истории и почти всегда видит уже
    записанное; оповещая на каждый повтор, переписку перерисовывали бы
    впустую при каждом запуске.
    """
    await put(
        session_factory,
        message_row(
            hr_id=known_hr.id, is_incoming=False, tg_message_id=11, text="уже было"
        ),
    )
    client = FakeTelegramClient()
    client.history = [_ours(11, "мой ответ")]
    heard: list[int] = []

    await _catch_up(
        client, known_hr, session_factory, on_message_persisted=heard.append
    )

    assert heard == []



async def test_an_unknown_peer_is_resolved_by_name(session_factory):
    """Неизвестного Telegram собеседника ищут по имени и пробуют снова.

    Telegram помнит собеседников по своему списку, и заведённого через
    окно HR там может не быть вовсе, пока его не разыщут по имени.
    """
    await put(session_factory, hr_row(telegram_user_id=777, telegram_username="maria"))
    hr = await only_row(session_factory, HR)
    client = FakeTelegramClient(fails={"get_chat_history": [PeerIdInvalid(), None]})
    client.history = [_theirs(10, "нашлось")]

    await _catch_up(client, hr, session_factory)

    assert client.get_users_calls == ["maria"]
    assert (await only_row(session_factory, Message)).text == "нашлось"


async def test_an_unknown_peer_without_a_name_is_given_up(session_factory):
    """Неизвестного собеседника без имени ищут не по чему, и его пропускают."""
    await put(session_factory, hr_row(telegram_user_id=777, telegram_username=None))
    hr = await only_row(session_factory, HR)
    client = FakeTelegramClient(fails={"get_chat_history": PeerIdInvalid()})
    client.history = [_theirs(10, "не дойдёт")]

    await _catch_up(client, hr, session_factory)

    assert client.get_users_calls == []
    assert await all_rows(session_factory, Message) == []


async def test_a_failed_second_try_leaves_its_trace_in_the_log(
    session_factory, caplog
):
    """Сорванная вторая попытка оставляет в журнале трассировку.

    Догон по этому HR просто заканчивается: ни строки в переписке, ни следа
    в окне. Отличить «переписки не было» от «до Telegram не достучались»
    можно только по журналу.
    """
    await put(session_factory, hr_row(telegram_user_id=777, telegram_username="maria"))
    hr = await only_row(session_factory, HR)
    client = FakeTelegramClient(
        fails={"get_chat_history": [PeerIdInvalid(), OSError("сеть")]}
    )

    with caplog.at_level(logging.WARNING):
        await _catch_up(client, hr, session_factory)

    assert "Traceback (most recent call last)" in caplog.text
    assert "OSError: сеть" in caplog.text


async def test_a_rate_limit_is_waited_out_once(known_hr, session_factory, monkeypatch):
    """Отказ «слишком часто» пережидают и повторяют один раз.

    Догон идёт пачками по два десятка переписок, и упереться в предел на
    середине — обычное дело; бросать из-за этого весь хвост переписки
    было бы расточительно.
    """
    import asyncio

    slept: list[float] = []

    async def note(seconds):
        slept.append(seconds)

    monkeypatch.setattr(asyncio, "sleep", note)
    client = FakeTelegramClient(
        fails={"get_chat_history": [FloodWait(value=42), None]}
    )
    client.history = [_theirs(10, "дошло со второго раза")]

    await _catch_up(client, known_hr, session_factory)

    assert slept == [43]
    assert (
        await only_row(session_factory, Message)
    ).text == "дошло со второго раза"


async def test_a_second_rate_limit_gives_up_on_this_hr(
    known_hr, session_factory, monkeypatch
):
    """Второй отказ подряд — переписку пропускают до следующего раза.

    Значит штраф серьёзный; долбиться в него дальше — верный способ
    получить ещё больший.
    """
    import asyncio

    async def note(seconds):
        pass

    monkeypatch.setattr(asyncio, "sleep", note)
    client = FakeTelegramClient(
        fails={"get_chat_history": [FloodWait(value=42), FloodWait(value=99)]}
    )
    client.history = [_theirs(10, "не дойдёт")]

    await _catch_up(client, known_hr, session_factory)

    assert await all_rows(session_factory, Message) == []


async def test_the_window_hears_about_the_caught_up_chat(
    known_hr, session_factory
):
    """Окно узнаёт о догнанной переписке — по одному разу на собеседника.

    Оповещать на каждое из полусотни сообщений значило бы перерисовать
    переписку полсотни раз подряд.
    """
    client = FakeTelegramClient()
    client.history = [_theirs(11, "и ещё"), _theirs(10, "привет")]
    heard: list[int] = []

    await _catch_up(
        client, known_hr, session_factory, on_message_persisted=heard.append
    )

    assert heard == [known_hr.id]


async def test_the_window_hears_about_a_caught_up_message_of_our_own(
    known_hr, session_factory
):
    """Догнанное своё сообщение доводит окно до оповещения.

    Половина пропущенного разговора — это написанное с телефона, и без
    оповещения переписка в окне останется без него до перезапуска.
    """
    client = FakeTelegramClient()
    client.history = [_ours(11, "мой ответ с телефона")]
    heard: list[int] = []

    await _catch_up(
        client, known_hr, session_factory, on_message_persisted=heard.append
    )

    assert heard == [known_hr.id]


async def test_nothing_new_means_the_window_is_not_told(
    known_hr, session_factory
):
    """Когда нового нет, окно не дёргают."""
    client = FakeTelegramClient()
    heard: list[int] = []

    await _catch_up(
        client, known_hr, session_factory, on_message_persisted=heard.append
    )

    assert heard == []


async def test_without_a_buffer_the_vacancy_list_is_refreshed(
    known_hr, session_factory, monkeypatch
):
    """Без накопителя догон сам сообщает окну о смене статусов.

    С накопителем статус меняется через минуту после разбора, и сигнал
    шлёт он же. Без накопителя разбор идёт на месте, и сообщить некому —
    список вакансий остался бы с прежними статусами до перезапуска.
    """

    async def process_dm(msg, *args, **kwargs):
        pass

    monkeypatch.setattr("backend.flows.dm_backfill.process_dm", process_dm)
    client = FakeTelegramClient()
    client.history = [_theirs(10, "привет")]
    heard: list[int] = []

    await backfill_hr_dm_history(
        client,
        known_hr,
        None,
        "qwen",
        session_factory,
        backfill_limit=50,
        on_vacancies_changed=lambda: heard.append(1),
    )

    assert heard == [1]


async def test_with_a_buffer_the_vacancy_list_is_left_to_the_reader(
    known_hr, session_factory, monkeypatch
):
    """С накопителем догон окно о вакансиях не дёргает.

    Пятьдесят сообщений на тридцать переписок дали бы полторы тысячи
    оповещений за миллисекунду, а статус к этому мигу ещё не менялся.
    """

    async def process_dm(msg, *args, **kwargs):
        pass

    monkeypatch.setattr("backend.flows.dm_backfill.process_dm", process_dm)
    client = FakeTelegramClient()
    client.history = [_theirs(10, "привет")]
    heard: list[int] = []

    await _catch_up(
        client, known_hr, session_factory, on_vacancies_changed=lambda: heard.append(1)
    )

    assert heard == []


async def test_a_long_rate_limit_is_not_waited_out(
    known_hr, session_factory, monkeypatch, caplog
):
    """Долгий отказ «слишком часто» не пережидают вовсе.

    Pyrogram сам переживает просьбы короче минуты, значит сюда доходят только
    долгие — минуты и часы. А ждать их некому: догон идёт внутри тела цикла
    бота, до всякой проверки остановки, и приложение на это время перестаёт
    закрываться, а кнопка «остановить» перестаёт помогать.

    Пропущенная переписка не теряется: догон повторится на следующем переходе
    в рабочий режим.
    """
    import asyncio

    slept: list[float] = []

    async def note(seconds):
        slept.append(seconds)

    monkeypatch.setattr(asyncio, "sleep", note)
    client = FakeTelegramClient(fails={"get_chat_history": [FloodWait(value=1800)]})
    client.history = [_theirs(10, "не должно доехать")]

    with caplog.at_level(logging.WARNING):
        await _catch_up(client, known_hr, session_factory)

    assert slept == []
    assert await all_rows(session_factory, Message) == []
    assert "1800" in caplog.text
