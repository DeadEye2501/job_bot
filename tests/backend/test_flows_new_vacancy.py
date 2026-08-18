"""Следствия заведения строки под новое объявление.

Строка пишется до разбора: сперва сохраняется сам текст и вектор, и только
потом объявление уходит в модель. Так падение на середине разбора не теряет
объявление — оно останется недоразобранным и его подберут на следующем
запуске.

У пары «канал и номер сообщения» стоит уникальность. Два обхода одного канала
могут пересечься; второй упирается в неё и молча уходит — вакансия уже
заведена первым.
"""

from backend.flows import parse as parse_mod
from backend.flows import ingest
from backend.flows import embeddings
from backend.models import TelegramChannel, Vacancy, VacancyEvent
from backend.payloads import ChannelPost
from tests.dbio import all_rows, only_row, put
from tests.factories import EPOCH, channel_row, vacancy_row
from tests.fakes.telegram import post


async def test_the_text_and_the_vector_are_saved_before_the_parse(
    make_pipeline, session_factory
):
    """Текст объявления и его вектор сохраняются до разбора.

    Падение на середине разбора тогда не теряет объявление: строка
    останется недоразобранной, и её подберут на следующем запуске.
    """
    pipeline = await make_pipeline()

    new_id = await ingest.save_new_vacancy(pipeline, ChannelPost(None, "jobs", post(42, text="Ищем Python-разработчика"), "текст"), [0.1, 0.2])

    saved = await only_row(session_factory, Vacancy)
    assert saved.id == new_id
    assert saved.raw_text == "текст"
    assert saved.embedding == [0.1, 0.2]
    assert saved.is_parsed is False


async def test_the_new_row_remembers_where_it_came_from(
    make_pipeline, session_factory
):
    """У новой строки записано, откуда объявление взялось.

    По этой паре её потом находят при повторном прогоне, и по ней же
    строится ссылка на исходный пост в окне.
    """
    await put(session_factory, channel_row(username="jobs"))
    channel = await only_row(session_factory, TelegramChannel)
    pipeline = await make_pipeline()

    await ingest.save_new_vacancy(pipeline, ChannelPost(channel.id, "jobs", post(42, text="Ищем Python-разработчика"), "текст"), [0.1])

    saved = await only_row(session_factory, Vacancy)
    assert saved.source_channel_id == channel.id
    assert saved.source_msg_id == 42
    assert saved.source_url == "https://t.me/jobs/42"
    assert saved.posted_at == EPOCH


async def test_the_new_vector_joins_the_cache(make_pipeline):
    """Вектор новой вакансии сразу попадает в кэш.

    Иначе два одинаковых объявления в одном обходе разошлись бы в две
    вакансии: второе сравнивалось бы с памятью, где первого ещё нет.
    """
    pipeline = await make_pipeline()
    await embeddings.ensure_embedding_cache(pipeline, width=2)

    new_id = await ingest.save_new_vacancy(pipeline, ChannelPost(None, "jobs", post(42, text="Ищем Python-разработчика"), "текст"), [0.1, 0.2])

    assert pipeline._embedding_ids.tolist() == [new_id]


async def test_the_timeline_records_where_it_was_ingested_from(
    make_pipeline, session_factory
):
    """В ленте вакансии остаётся запись о том, откуда её взяли."""
    pipeline = await make_pipeline()

    await ingest.save_new_vacancy(pipeline, ChannelPost(None, "jobs", post(42, text="Ищем Python-разработчика"), "текст"), [0.1])

    event = await only_row(session_factory, VacancyEvent)
    assert event.kind == "ingested"
    assert event.payload == {"channel": "jobs", "msg_id": 42}


async def test_the_same_post_twice_makes_one_row(make_pipeline, session_factory):
    """Второе заведение того же поста строки не создаёт.

    Два обхода одного канала пересекаются; уникальность пары «канал и
    номер сообщения» это и стережёт.
    """
    await put(session_factory, channel_row(username="jobs"))
    channel = await only_row(session_factory, TelegramChannel)
    pipeline = await make_pipeline()
    first = await ingest.save_new_vacancy(pipeline, ChannelPost(channel.id, "jobs", post(42, text="Ищем Python-разработчика"), "текст"), [0.1])

    second = await ingest.save_new_vacancy(
        pipeline,
        ChannelPost(channel.id, "jobs", post(42, text="Ищем Python-разработчика"), "текст"),
        [0.1],
    )

    assert first is not None
    assert second is None
    assert len(await all_rows(session_factory, Vacancy)) == 1


async def test_a_refused_row_leaves_no_vector_behind(make_pipeline, session_factory):
    """Незаведённая строка вектора в кэше не оставляет.

    Иначе в памяти висел бы вектор с чужим номером, и найденный по нему
    повтор указывал бы не на ту вакансию.
    """
    await put(session_factory, channel_row(username="jobs"))
    channel = await only_row(session_factory, TelegramChannel)
    pipeline = await make_pipeline()
    await embeddings.ensure_embedding_cache(pipeline, width=2)
    first = await ingest.save_new_vacancy(pipeline, ChannelPost(channel.id, "jobs", post(42, text="Ищем Python-разработчика"), "текст"), [0.1])

    await ingest.save_new_vacancy(pipeline, ChannelPost(channel.id, "jobs", post(42, text="Ищем Python-разработчика"), "текст"), [0.1])

    assert pipeline._embedding_ids.tolist() == [first]


async def test_an_unfinished_vacancy_is_picked_up_later(monkeypatch, 
    make_pipeline, session_factory
):
    """Недоразобранная вакансия подбирается на следующем запуске."""
    await put(session_factory, vacancy_row(title=None, is_parsed=False, raw_text="текст"))
    pipeline = await make_pipeline()
    picked: list[tuple] = []

    async def parse(pipeline, vacancy_id, text, username, allow_delete=False):
        picked.append((vacancy_id, text, allow_delete))

    monkeypatch.setattr(parse_mod, "parse_and_update_vacancy", parse)

    assert await pipeline.recover_orphan_vacancies() == 1
    assert picked == [(1, "текст", True)]


async def test_a_parsed_vacancy_is_not_picked_up(monkeypatch, make_pipeline, session_factory):
    """Разобранная вакансия повторно не подбирается."""
    await put(session_factory, vacancy_row(title="готова", is_parsed=True, raw_text="т"))
    pipeline = await make_pipeline()
    picked: list[int] = []

    async def parse(pipeline, vacancy_id, text, username, allow_delete=False):
        picked.append(vacancy_id)

    monkeypatch.setattr(parse_mod, "parse_and_update_vacancy", parse)

    assert await pipeline.recover_orphan_vacancies() == 0
    assert picked == []


async def test_a_vacancy_without_text_cannot_be_picked_up(monkeypatch, 
    make_pipeline, session_factory
):
    """Недоразобранная вакансия без текста не подбирается: разбирать нечего."""
    await put(session_factory, vacancy_row(title=None, is_parsed=False, raw_text=""))
    pipeline = await make_pipeline()
    picked: list[int] = []

    async def parse(pipeline, vacancy_id, text, username, allow_delete=False):
        picked.append(vacancy_id)

    monkeypatch.setattr(parse_mod, "parse_and_update_vacancy", parse)

    assert await pipeline.recover_orphan_vacancies() == 0
    assert picked == []


async def test_one_broken_orphan_does_not_stop_the_rest(monkeypatch, 
    make_pipeline, session_factory
):
    """Сорвавшийся подбор одной вакансии остальные не отменяет.

    Подбор идёт один раз при запуске; потерять из-за одной строки все
    остальные значило бы оставить их полуготовыми до следующего раза.
    """
    await put(
        session_factory,
        vacancy_row(title=None, is_parsed=False, raw_text="первая"),
        vacancy_row(title=None, is_parsed=False, raw_text="вторая"),
    )
    pipeline = await make_pipeline()
    done: list[str] = []

    async def parse(pipeline, vacancy_id, text, username, allow_delete=False):
        if text == "первая":
            raise RuntimeError("не разобралось")
        done.append(text)

    monkeypatch.setattr(parse_mod, "parse_and_update_vacancy", parse)

    assert await pipeline.recover_orphan_vacancies() == 1
    assert done == ["вторая"]


async def test_the_window_hears_about_the_recovery(monkeypatch, make_pipeline, session_factory):
    """Окно узнаёт о подборе и о его завершении.

    Подбор идёт до обхода каналов; без гашения полосы следующая стадия
    унаследовала бы его счётчик.
    """
    await put(session_factory, vacancy_row(title=None, is_parsed=False, raw_text="т"))
    pipeline = await make_pipeline()

    async def parse(pipeline, vacancy_id, text, username, allow_delete=False):
        pass

    monkeypatch.setattr(parse_mod, "parse_and_update_vacancy", parse)
    heard: list[tuple] = []
    pipeline.on_progress = lambda *args: heard.append(args)

    await pipeline.recover_orphan_vacancies()

    assert heard == [("recover", "", 0, 1), ("recover", "", 0, 0)]


async def test_nothing_to_recover_is_no_work(make_pipeline):
    """Когда подбирать нечего, ничего и не делается."""
    pipeline = await make_pipeline()
    heard: list[tuple] = []
    pipeline.on_progress = lambda *args: heard.append(args)

    assert await pipeline.recover_orphan_vacancies() == 0
    assert heard == []
