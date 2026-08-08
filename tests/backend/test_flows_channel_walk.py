"""Следствия обхода каналов за один цикл.

Сводка названий идёт по всем каналам с именем, включая выключенные: они видны
в окне, и пользователь ждёт там свежих данных. А вот сообщения читаются только
у включённых — выключить канал и значит «не собирай отсюда».

Сорвавшийся канал обход не обрывает: их полтора десятка, и потерять из-за
одного все остальные — потерять полтора часа работы. В конце обе полосы в окне
гасятся, иначе нижняя так и застынет на счётчике последнего канала.
"""

from backend.flows import channels
import pytest

from backend.models import TelegramChannel
from tests.dbio import all_rows, put
from tests.factories import channel_row
from tests.fakes.telegram import FakeTelegramClient, chat


@pytest.fixture
async def walking(monkeypatch, make_pipeline):
    """Конвейер с подставным чтением канала и без перезагрузки ресурсов.

    Предмет здесь — сам обход: кого он обходит, в каком порядке и что
    сообщает окну. Чтение сообщений и перезагрузка настроек — работа
    соседних слайсов.
    """
    pipeline = await make_pipeline(FakeTelegramClient())
    pipeline.walked = []

    async def reload():
        pipeline.walked.append("настройки")

    async def poll(pipeline, channel_id, username, last_id):
        pipeline.walked.append(username)

    pipeline._reload_resources = reload
    monkeypatch.setattr(channels, "_poll_channel", poll)
    return pipeline


async def test_only_the_switched_on_channels_are_read(
    walking, session_factory
):
    """Сообщения читаются только у включённых каналов.

    Выключить канал и значит «не собирай отсюда»; название у него всё
    равно обновится — он виден в окне.
    """
    await put(
        session_factory,
        channel_row(username="on", is_active=True),
        channel_row(username="off", is_active=False),
    )

    await walking.poll_active_channels()

    assert [step for step in walking.walked if step != "настройки"] == ["on"]


async def test_a_channel_without_a_name_is_not_walked(walking, session_factory):
    """Канал без имени не обходят: спросить у Telegram его нечем."""
    await put(
        session_factory,
        channel_row(username=None, is_active=True),
        channel_row(username="on", is_active=True),
    )

    await walking.poll_active_channels()

    assert [step for step in walking.walked if step != "настройки"] == ["on"]


async def test_the_settings_are_reloaded_before_the_walk(walking, session_factory):
    """Настройки перечитываются до обхода, а не после.

    Пользователь мог поправить навыки или чёрный список между циклами, и
    обход должен идти уже по новым правилам.
    """
    await put(session_factory, channel_row(username="on", is_active=True))

    await walking.poll_active_channels()

    assert walking.walked[0] == "настройки"


async def test_a_broken_channel_does_not_stop_the_walk(monkeypatch, walking, session_factory):
    """Сорвавшийся канал обход не обрывает.

    Каналов полтора десятка, цикл идёт полтора часа; уронив его на
    первом же недоступном, бот терял бы всю работу.
    """
    await put(
        session_factory,
        channel_row(username="broken", is_active=True),
        channel_row(username="good", is_active=True),
    )
    walked: list[str] = []

    async def poll(pipeline, channel_id, username, last_id):
        if username == "broken":
            raise OSError("канал закрыт")
        walked.append(username)

    monkeypatch.setattr(channels, "_poll_channel", poll)

    await walking.poll_active_channels()

    assert walked == ["good"]


async def test_the_window_is_told_where_the_walk_is(walking, session_factory):
    """Окно узнаёт, на каком канале обход и сколько их всего.

    Полтора часа без единого признака жизни пользователь читает как
    зависшее приложение.
    """
    await put(
        session_factory,
        channel_row(username="first", is_active=True),
        channel_row(username="second", is_active=True),
    )
    heard: list[tuple] = []
    walking.on_progress = lambda *args: heard.append(args)

    await walking.poll_active_channels()

    assert heard[:2] == [("channel", "@first", 0, 2), ("channel", "@second", 1, 2)]


async def test_both_bars_are_cleared_when_the_walk_ends(walking, session_factory):
    """В конце обхода обе полосы в окне гасятся.

    Иначе нижняя застывает на счётчике последнего канала и до следующего
    цикла выглядит как незаконченная работа.
    """
    await put(session_factory, channel_row(username="only", is_active=True))
    heard: list[tuple] = []
    walking.on_progress = lambda *args: heard.append(args)

    await walking.poll_active_channels()

    assert heard[-2:] == [("channel", "", 1, 1), ("message", "", 0, 0)]


async def test_names_are_refreshed_even_for_switched_off_channels(
    make_pipeline, session_factory
):
    """Названия обновляются и у выключенных каналов.

    Они показаны в том же списке, и застывшее название там выглядит
    ошибкой приложения, а не следствием выключенности.
    """
    await put(session_factory, channel_row(username="off", title="Было", is_active=False))
    client = FakeTelegramClient(chats={"off": chat(title="Стало")})
    pipeline = await make_pipeline(client)

    async def nothing():
        pass

    pipeline._reload_resources = nothing

    await pipeline.poll_active_channels()

    saved = await all_rows(session_factory, TelegramChannel)
    assert [c.title for c in saved] == ["Стало"]


async def test_one_channel_on_demand_is_read(walking, session_factory):
    """Прогон одного канала читает именно его."""
    await put(
        session_factory,
        channel_row(username="wanted", is_active=True),
        channel_row(username="other", is_active=True),
    )
    rows = await all_rows(session_factory, TelegramChannel)
    wanted = next(c for c in rows if c.username == "wanted")

    assert await walking.poll_one_channel(wanted.id) is True
    assert [step for step in walking.walked if step != "настройки"] == ["wanted"]


async def test_a_switched_off_channel_is_still_read_on_demand(
    walking, session_factory
):
    """Выключенный канал по кнопке всё равно читается.

    Кнопку нажал пользователь, глядя именно на этот канал: отказать ему
    из-за выключенности значило бы проигнорировать прямую просьбу.
    """
    await put(session_factory, channel_row(username="off", is_active=False))
    rows = await all_rows(session_factory, TelegramChannel)

    assert await walking.poll_one_channel(rows[0].id) is True


async def test_a_missing_channel_on_demand_reports_failure(walking):
    """Прогон несуществующего канала сообщает о неудаче."""
    assert await walking.poll_one_channel(404) is False


async def test_a_channel_without_a_name_on_demand_reports_failure(
    walking, session_factory
):
    """Прогон канала без имени сообщает о неудаче: спрашивать нечем."""
    await put(session_factory, channel_row(username=None))
    rows = await all_rows(session_factory, TelegramChannel)

    assert await walking.poll_one_channel(rows[0].id) is False


async def test_a_broken_read_on_demand_reports_failure(monkeypatch, walking, session_factory):
    """Сорвавшийся прогон одного канала сообщает о неудаче.

    Окно показывает по этому ответу подсказку; проглотив сбой молча, оно
    сказало бы пользователю, что всё прошло.
    """
    await put(session_factory, channel_row(username="broken", is_active=True))
    rows = await all_rows(session_factory, TelegramChannel)

    async def poll(pipeline, channel_id, username, last_id):
        raise OSError("канал закрыт")

    monkeypatch.setattr(channels, "_poll_channel", poll)

    assert await walking.poll_one_channel(rows[0].id) is False
