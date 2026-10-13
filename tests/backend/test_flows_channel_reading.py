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

from backend.flows import channels
import pytest

from backend.flows import embeddings
from backend.flows import ingest as ingest_mod
from backend.models import TelegramChannel
from tests.dbio import only_row, put
from tests.factories import channel_row
from tests.fakes.telegram import FakeTelegramClient
from tests.fakes.telegram_objects import post


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

    monkeypatch.setattr(ingest_mod, "ingest_post", take)
    return pipeline, client, channel


async def test_the_new_posts_are_taken_oldest_first(reading):
    """Новые объявления разбираются от старого к свежему.

    Telegram отдаёт наоборот, а отметка должна двигаться вперёд: разобрав
    свежее первым, бот сдвинул бы её и потерял бы всё, что между.
    """
    pipeline, client, channel = reading
    client.history = [post(12), post(11), post(10)]

    await channels.poll_channel(pipeline, channel.id, "jobs", None)

    assert pipeline.taken == [10, 11, 12]


async def test_reading_stops_at_the_mark(reading):
    """Чтение обрывается на первом же сообщении не новее отметки.

    Дальше идёт то, что уже разобрано; читать его заново значило бы
    тратить обращение к модели на каждое старое объявление.
    """
    pipeline, client, channel = reading
    client.history = [post(12), post(11), post(10), post(9)]

    await channels.poll_channel(pipeline, channel.id, "jobs", 10)

    assert pipeline.taken == [11, 12]


async def test_a_channel_without_a_mark_is_read_whole(reading):
    """Канал без отметки читается целиком — так идёт первый обход."""
    pipeline, client, channel = reading
    client.history = [post(12), post(11)]

    await channels.poll_channel(pipeline, channel.id, "jobs", None)

    assert pipeline.taken == [11, 12]


async def test_the_mark_ends_up_on_the_lastpost(reading, session_factory):
    """После обхода отметка стоит на последнем разобранном сообщении."""
    pipeline, client, channel = reading
    client.history = [post(12), post(11), post(10)]

    await channels.poll_channel(pipeline, channel.id, "jobs", None)

    saved = await only_row(session_factory, TelegramChannel)
    assert saved.last_processed_msg_id == 12


async def test_a_silent_prints_provider_leaves_the_mark_alone(
    monkeypatch, reading, session_factory
):
    """Пост, не принятый из-за молчащего поставщика отпечатков, отметку не двигает.

    Двинутая отметка теряет объявления навсегда: следующий обход берёт то,
    что новее её, а эти посты никто не считал. Сорвавшийся разбор — другое
    дело: там строка вакансии уже заведена, и перечитывать пост незачем.
    """
    pipeline, client, channel = reading
    client.history = [post(12), post(11), post(10)]

    async def no_provider(pipeline, channel_id, username, msg):
        raise embeddings.ProviderIsSilent(f"[@{username}] {msg.id}")

    monkeypatch.setattr(ingest_mod, "ingest_post", no_provider)

    await channels.poll_channel(pipeline, channel.id, "jobs", None)

    saved = await only_row(session_factory, TelegramChannel)
    assert saved.last_processed_msg_id is None


async def test_one_silent_post_holds_the_mark_below_itself(
    monkeypatch, reading, session_factory
):
    """Одна осечка держит отметку под собой, сколько бы постов ни легло следом.

    Молчание поставщика бывает и одиночным — медленная выдача сразу после
    загрузки модели. Двинь отметку по следующим удачным постам, и пропущенный
    останется ниже неё: следующий обход берёт только то, что новее, и
    объявление не увидит уже никто.

    Посты после осечки при этом заводятся, а на следующем обходе
    перечитываются и срезаются отсевом повторов — это дешевле потери.
    """
    pipeline, client, channel = reading
    client.history = [post(13), post(12), post(11)]

    async def silent_on_the_first(pipeline, channel_id, username, msg):
        if msg.id == 11:
            raise embeddings.ProviderIsSilent(f"[@{username}] {msg.id}")

    monkeypatch.setattr(ingest_mod, "ingest_post", silent_on_the_first)

    await channels.poll_channel(pipeline, channel.id, "jobs", None)

    saved = await only_row(session_factory, TelegramChannel)
    assert saved.last_processed_msg_id is None


async def test_a_dropped_walk_is_not_reported_as_done(monkeypatch, reading):
    """Брошенный обход отвечает бедой, а не «прогнан».

    Человек нажал «Прогнать сейчас», поставщик отпечатков молчит, обход
    бросили на третьем посте — окно обязано сказать о беде. Слово «прогнан»
    здесь означало бы, что канал вычитан, и человек не стал бы разбираться,
    почему не появилось ни одной вакансии.
    """
    pipeline, client, channel = reading
    client.history = [post(msg_id) for msg_id in range(20, 10, -1)]

    async def no_provider(pipeline, channel_id, username, msg):
        raise embeddings.ProviderIsSilent(f"[@{username}] {msg.id}")

    monkeypatch.setattr(ingest_mod, "ingest_post", no_provider)

    assert await channels.poll_one_channel(pipeline, channel.id) == "error"


async def test_the_channel_is_dropped_after_the_provider_keeps_silent(
    monkeypatch, reading
):
    """Молчание поставщика подряд бросает обход канала, а не перебирает хвост.

    Молчит он сразу для всех, и перебор оставшихся постов — это десятки
    напрасных обращений и минуты на канал, за которыми всё равно ничего не
    заводится.
    """
    pipeline, client, channel = reading
    client.history = [post(msg_id) for msg_id in range(20, 10, -1)]
    tried: list[int] = []

    async def no_provider(pipeline, channel_id, username, msg):
        tried.append(msg.id)
        raise embeddings.ProviderIsSilent(f"[@{username}] {msg.id}")

    monkeypatch.setattr(ingest_mod, "ingest_post", no_provider)

    await channels.poll_channel(pipeline, channel.id, "jobs", None)

    assert tried == [11, 12, 13]


async def test_the_mark_is_saved_in_batches(monkeypatch, reading):
    """Отметка сохраняется пачками, а не после каждого сообщения.

    Полтора десятка каналов по полтора десятка сообщений дали бы сотни
    записей на диск за один обход.
    """
    pipeline, client, channel = reading
    await pipeline.rs.set_app("backfill_limit", "25")
    client.history = [post(msg_id) for msg_id in range(25, 0, -1)]
    saves: list[int] = []
    real_advance = channels.advance_cursor

    async def note(pipeline, channel_id, msg_id):
        saves.append(msg_id)
        await real_advance(pipeline, channel_id, msg_id)

    monkeypatch.setattr(channels, "advance_cursor", note)

    await channels.poll_channel(pipeline, channel.id, "jobs", None)

    assert saves == [10, 20, 25]


async def test_nothing_new_leaves_the_mark_alone(monkeypatch, reading, session_factory):
    """Когда нового нет, отметка не трогается и записи не идёт."""
    pipeline, client, channel = reading
    await put(session_factory, channel_row(username="other"))
    async with session_factory() as session:
        row = await session.get(TelegramChannel, channel.id)
        row.last_processed_msg_id = 12
        await session.commit()
    client.history = [post(12)]
    saves: list[int] = []
    monkeypatch.setattr(
        channels, "advance_cursor",
        lambda pipeline, channel_id, msg_id: saves.append(msg_id),
    )

    await channels.poll_channel(pipeline, channel.id, "jobs", 12)

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

    monkeypatch.setattr(ingest_mod, "ingest_post", take)

    await channels.poll_channel(pipeline, channel.id, "jobs", None)

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

    monkeypatch.setattr(ingest_mod, "ingest_post", take)

    with pytest.raises(KeyboardInterrupt):
        await channels.poll_channel(pipeline, channel.id, "jobs", None)

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

    await channels.poll_channel(pipeline, channel.id, "jobs", None)

    assert heard == [
        ("message", "@jobs", 0, 2),
        ("message", "@jobs", 1, 2),
        ("message", "@jobs", 2, 2),
    ]


async def test_a_channel_that_outran_the_limit_loses_nothing(reading, session_factory):
    """Канал, выложивший больше предела за простой, не теряет середину.

    За обход берётся предел старейших непрочитанных, и отметка встаёт на
    последнем из них: остальное заберут следующие обходы. Отметка, уехавшая на
    самый свежий, оставила бы между ней и прежней посты, которых не увидит уже
    никто.
    """
    pipeline, client, channel = reading
    await pipeline.rs.set_app("backfill_limit", "3")
    client.history = [post(msg_id) for msg_id in range(20, 0, -1)]

    await channels.poll_channel(pipeline, channel.id, "jobs", 5)
    first = list(pipeline.taken)
    await channels.poll_channel(pipeline, channel.id, "jobs", 8)

    assert first == [6, 7, 8]
    assert pipeline.taken == [6, 7, 8, 9, 10, 11]
    saved = await only_row(session_factory, TelegramChannel)
    assert saved.last_processed_msg_id == 11


async def test_the_first_walk_of_a_channel_is_not_called_a_loss(reading, caplog):
    """Первый обход канала потерей не считается, сколько бы он ни прочёл.

    Отметки ещё нет, читать «до виденного» нечего, и предел здесь работает по
    назначению — это глубина первого захода, а не обрыв.
    """
    pipeline, client, channel = reading
    await pipeline.rs.set_app("backfill_limit", "3")
    client.history = [post(msg_id) for msg_id in range(20, 0, -1)]

    with caplog.at_level("WARNING"):
        await channels.poll_channel(pipeline, channel.id, "jobs", None)

    assert "WARNING" not in caplog.text
