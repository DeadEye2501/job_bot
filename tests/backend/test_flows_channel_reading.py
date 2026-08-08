"""Следствия чтения новых сообщений одного канала.

Читается только то, что новее отметки: Telegram отдаёт свежее первым, и на
первом же старом сообщении обход канала обрывается. Разбираются они в обратном
порядке — от старого к свежему, — чтобы отметка двигалась вперёд, а не прыгала.

Отметка сохраняется пачками, а не после каждого сообщения: полтора десятка
каналов по полтора десятка сообщений дали бы сотни записей на диск за цикл.
Досохраняется она в любом случае — иначе следующий обход перечитал бы то же
самое.

Сообщение, на котором разбор сорвался, отметку всё равно двигает. Иначе оно
перечитывалось бы вечно, каждый цикл упираясь в ту же ошибку.
"""

import pytest

from backend.flows import ingest as ingest_mod
from backend.models import TelegramChannel
from tests.dbio import only_row, put
from tests.factories import channel_row
from tests.fakes.telegram import FakeTelegramClient, post


@pytest.fixture
async def reading(monkeypatch, make_pipeline, session_factory):
    """Канал, конвейер с подставным приёмом поста и отметкой на месте."""
    await put(session_factory, channel_row(username="jobs", last_processed_msg_id=None))
    channel = await only_row(session_factory, TelegramChannel)
    client = FakeTelegramClient()
    pipeline = await make_pipeline(client)
    pipeline.taken = []

    async def take(pipeline, channel_id, username, msg):
        pipeline.taken.append(msg.id)

    monkeypatch.setattr(ingest_mod, "_ingest_post", take)
    return pipeline, client, channel


async def test_the_new_posts_are_taken_oldest_first(reading, session_factory):
    """Новые объявления разбираются от старого к свежему.

    Telegram отдаёт наоборот, а отметка должна двигаться вперёд: разобрав
    свежее первым, бот сдвинул бы её и потерял бы всё, что между.
    """
    pipeline, client, channel = reading
    client.history = [post(12), post(11), post(10)]

    await pipeline._poll_channel(channel.id, "jobs", None)

    assert pipeline.taken == [10, 11, 12]


async def test_reading_stops_at_the_mark(reading, session_factory):
    """Чтение обрывается на первом же сообщении не новее отметки.

    Дальше идёт то, что уже разобрано; читать его заново значило бы
    тратить обращение к модели на каждое старое объявление.
    """
    pipeline, client, channel = reading
    client.history = [post(12), post(11), post(10), post(9)]

    await pipeline._poll_channel(channel.id, "jobs", 10)

    assert pipeline.taken == [11, 12]


async def test_a_channel_without_a_mark_is_read_whole(reading):
    """Канал без отметки читается целиком — так идёт первый обход."""
    pipeline, client, channel = reading
    client.history = [post(12), post(11)]

    await pipeline._poll_channel(channel.id, "jobs", None)

    assert pipeline.taken == [11, 12]


async def test_the_mark_ends_up_on_the_lastpost(reading, session_factory):
    """После обхода отметка стоит на последнем разобранном сообщении."""
    pipeline, client, channel = reading
    client.history = [post(12), post(11), post(10)]

    await pipeline._poll_channel(channel.id, "jobs", None)

    saved = await only_row(session_factory, TelegramChannel)
    assert saved.last_processed_msg_id == 12


async def test_the_mark_is_saved_in_batches(reading, session_factory):
    """Отметка сохраняется пачками, а не после каждого сообщения.

    Полтора десятка каналов по полтора десятка сообщений дали бы сотни
    записей на диск за один обход.
    """
    pipeline, client, channel = reading
    await pipeline._rs.set_app("backfill_limit", "25")
    client.history = [post(msg_id) for msg_id in range(25, 0, -1)]
    saves: list[int] = []
    real_advance = pipeline._advance_cursor

    async def note(channel_id, msg_id):
        saves.append(msg_id)
        await real_advance(channel_id, msg_id)

    pipeline._advance_cursor = note

    await pipeline._poll_channel(channel.id, "jobs", None)

    assert saves == [10, 20, 25]


async def test_nothing_new_leaves_the_mark_alone(reading, session_factory):
    """Когда нового нет, отметка не трогается и записи не идёт."""
    pipeline, client, channel = reading
    await put(session_factory, channel_row(username="other"))
    async with session_factory() as session:
        row = await session.get(TelegramChannel, channel.id)
        row.last_processed_msg_id = 12
        await session.commit()
    client.history = [post(12)]
    saves: list[int] = []
    pipeline._advance_cursor = lambda channel_id, msg_id: saves.append(msg_id)

    await pipeline._poll_channel(channel.id, "jobs", 12)

    assert pipeline.taken == []
    assert saves == []


async def test_a_broken_post_still_moves_the_mark(monkeypatch, reading, session_factory):
    """Сообщение, на котором разбор сорвался, отметку всё равно двигает.

    Иначе оно перечитывалось бы вечно, каждый обход упираясь в ту же
    ошибку и не пропуская дальше ничего.
    """
    pipeline, client, channel = reading
    client.history = [post(11), post(10)]

    async def take(pipeline, channel_id, username, msg):
        if msg.id == 10:
            raise RuntimeError("не разобралось")
        pipeline.taken.append(msg.id)

    monkeypatch.setattr(ingest_mod, "_ingest_post", take)

    await pipeline._poll_channel(channel.id, "jobs", None)

    assert pipeline.taken == [11]
    saved = await only_row(session_factory, TelegramChannel)
    assert saved.last_processed_msg_id == 11


async def test_the_mark_survives_a_break_mid_channel(monkeypatch, reading, session_factory):
    """Отметка досохраняется, даже если обход оборвался на середине.

    Без этого следующий обход перечитал бы всё, что уже разобрано, — и
    заплатил бы за это обращением к модели на каждое сообщение.
    """
    pipeline, client, channel = reading
    client.history = [post(12), post(11), post(10)]

    async def take(pipeline, channel_id, username, msg):
        pipeline.taken.append(msg.id)
        if msg.id == 11:
            raise KeyboardInterrupt

    monkeypatch.setattr(ingest_mod, "_ingest_post", take)

    with pytest.raises(KeyboardInterrupt):
        await pipeline._poll_channel(channel.id, "jobs", None)

    saved = await only_row(session_factory, TelegramChannel)
    assert saved.last_processed_msg_id == 10


async def test_the_window_is_told_where_inside_the_channel_it_is(reading):
    """Окно узнаёт, на каком сообщении канала идёт разбор.

    Канал с полусотней объявлений разбирается минутами; без счётчика
    полоса в окне выглядит замершей.
    """
    pipeline, client, channel = reading
    client.history = [post(11), post(10)]
    heard: list[tuple] = []
    pipeline.on_progress = lambda *args: heard.append(args)

    await pipeline._poll_channel(channel.id, "jobs", None)

    assert heard == [
        ("message", "@jobs", 0, 2),
        ("message", "@jobs", 1, 2),
        ("message", "@jobs", 2, 2),
    ]
