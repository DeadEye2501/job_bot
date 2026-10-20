"""Следствия заведения строки под новое объявление.

Строка пишется до разбора: сперва сохраняется сам текст и вектор, и только
потом объявление уходит в модель. Так падение на середине разбора не теряет
объявление — оно останется недоразобранным и его подберут на следующем
запуске.

У пары «канал и номер сообщения» стоит уникальность. Два обхода одного канала
могут пересечься; второй упирается в неё и молча уходит — вакансия уже
заведена первым.
"""

from datetime import datetime, timezone

import httpx
import pytest

from tests.fakes.telegraph import serve_articles
from backend.flows import ingest, rerun
from backend.flows import intake as intake_flow
from backend.flows import embeddings
from backend.models import TelegramChannel, Vacancy, VacancyEvent
from backend.payloads import ChannelPost
from tests.backend.fixtures.flows import similar_by_hand
from tests.backend.fixtures.parse_stub import parse_into
from tests.dbio import all_rows, only_row, put
from tests.factories import EPOCH, channel_row, vacancy_row
from tests.fakes.telegram import WithMessages
from tests.fakes.telegram_objects import post

# Подделка отпечатка на весь файл, а не по месту: подбор недоразобранного
# считает отпечаток на каждой разобранной строке, и настоящий зов ушёл бы к
# поставщику — беда утонула бы в журнале, проверки зеленели бы на
# несработавшем шаге.
pytestmark = pytest.mark.usefixtures("one_vector")

WITH_ARTICLE = "Senior QA https://telegra.ph/QA-08-21"
"""Пост, всё содержание которого вынесено в статью по ссылке."""


async def _orphan_waiting_for_an_article(session_factory, created_at=None):
    """Заведённая, но не разобранная строка под пост со ссылкой на статью."""
    await put(session_factory, channel_row(username="jobs"))
    channel = await only_row(session_factory, TelegramChannel)
    await put(
        session_factory,
        vacancy_row(
            title=None,
            is_parsed=False,
            raw_text=WITH_ARTICLE,
            source_channel_id=channel.id,
            source_msg_id=42,
            created_at=created_at or datetime.now(timezone.utc).replace(tzinfo=None),
        ),
    )


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


async def test_a_row_without_a_vector_leaves_the_cache_alone(make_pipeline, session_factory):
    """Строка без отпечатка кэш не трогает и следующей не мешает.

    Отпечатка у строки не бывает у того, кто заводит её мимо бота, — модель
    отпечатков поднимают не всегда. Положи такую пустоту в кэш, и он потеряет
    ширину: следующий настоящий вектор в него уже не встанет, а строка к тому
    мигу записана — она осталась бы навсегда неразобранной и невидимой.
    """
    pipeline = await make_pipeline()
    await embeddings.ensure_embedding_cache(pipeline, width=2)

    await intake_flow.save_new_vacancy(
        pipeline, Vacancy(raw_text="Ищем повара"), "created_by_hand"
    )
    with_vector = await intake_flow.save_new_vacancy(
        pipeline, Vacancy(raw_text="Ищем сварщика", embedding=[0.1, 0.2]), "ingested"
    )

    assert pipeline.embeddings.ids.tolist() == [with_vector]


async def test_the_new_vector_joins_the_cache(make_pipeline):
    """Вектор новой вакансии сразу попадает в кэш.

    Иначе два одинаковых объявления в одном обходе разошлись бы в две
    вакансии: второе сравнивалось бы с памятью, где первого ещё нет.
    """
    pipeline = await make_pipeline()
    await embeddings.ensure_embedding_cache(pipeline, width=2)

    new_id = await ingest.save_new_vacancy(pipeline, ChannelPost(None, "jobs", post(42, text="Ищем Python-разработчика"), "текст"), [0.1, 0.2])

    assert pipeline.embeddings.ids.tolist() == [new_id]


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

    assert pipeline.embeddings.ids.tolist() == [first]


async def test_an_unfinished_vacancy_is_picked_up_later(parsed,
    make_pipeline, session_factory
):
    """Недоразобранная вакансия без ссылок на статью подбирается целиком.

    Ждать ей нечего: в тексте нет ничего, что могло бы дособраться, — значит
    и в Telegram за постом ради неё не ходят, и приговор выносится по тому,
    что есть, с правом убрать непригодное.
    """
    await put(session_factory, vacancy_row(title=None, is_parsed=False, raw_text="текст"))
    client = WithMessages(post=post(42, text="текст"))
    pipeline = await make_pipeline(client)

    assert await pipeline.recover_orphan_vacancies() == 1
    assert parsed == [(1, "текст", "", True)]
    assert client.asked == [] and pipeline.applied == [[1]]


async def test_a_new_post_goes_from_the_parse_to_the_applier(
    parsed, one_vector, make_pipeline, session_factory, monkeypatch
):
    await put(session_factory, channel_row(username="jobs"))
    channel = await only_row(session_factory, TelegramChannel)
    pipeline = await make_pipeline()
    similar_by_hand(pipeline, monkeypatch)

    await ingest.ingest_post(pipeline, channel.id, "jobs", post(42, text="Ищем Python-разработчика"))

    (row,) = await all_rows(session_factory, Vacancy)
    assert pipeline.applied == [[row.id]]


async def test_an_orphan_whose_article_arrived_is_judged_in_full(monkeypatch,
    parsed, make_pipeline, session_factory
):
    """Дочитанное объявление судят по свежему тексту, и мусор уже можно убрать.

    Приговора у него не было ровно потому, что статья не дошла. Дошла —
    недобор больше ни при чём, и запрет на удаление уходит вместе с ним.
    """
    await _orphan_waiting_for_an_article(session_factory)

    serve_articles(monkeypatch)
    pipeline = await make_pipeline(WithMessages(post=post(42, text=WITH_ARTICLE)))

    assert await pipeline.recover_orphan_vacancies() == 1

    whole = f"{WITH_ARTICLE}\n\nТребования: Python"
    assert parsed == [(1, whole, "jobs", True)]
    assert (await only_row(session_factory, Vacancy)).raw_text == whole


async def test_an_orphan_post_of_a_closed_channel_is_reread_by_its_address(
    monkeypatch, parsed, make_pipeline, session_factory
):
    """Пост закрытого канала, заведённый по ссылке, перечитывается по адресу
    строки: строки канала у него нет."""
    await put(session_factory, vacancy_row(
        title=None, is_parsed=False, raw_text=WITH_ARTICLE, source_msg_id=42,
        source_url="https://t.me/c/123/42",
    ))
    serve_articles(monkeypatch)
    client = WithMessages(post=post(42, text=WITH_ARTICLE))
    pipeline = await make_pipeline(client)

    assert await pipeline.recover_orphan_vacancies() == 1

    assert client.asked == [(-100123, 42)]


async def test_a_dug_out_article_moves_the_fingerprint_too(monkeypatch,
    parsed, one_vector, make_pipeline, session_factory
):
    """Дочитанная статья двигает и отпечаток строки.

    Отпечаток ей посчитали на приёме — по одной шапке со ссылкой, потому что
    статьи тогда не было. Оставь его как есть, и в отсеве повторов эта строка
    осталась бы шапкой: своё же объявление, пришедшее из соседнего канала уже
    со статьёй, с ней бы не сошлось и завелось второй строкой.
    """
    await _orphan_waiting_for_an_article(session_factory)

    serve_articles(monkeypatch)
    pipeline = await make_pipeline(WithMessages(post=post(42, text=WITH_ARTICLE)))

    assert await pipeline.recover_orphan_vacancies() == 1

    whole = f"{WITH_ARTICLE}\n\nТребования: Python"
    assert one_vector == [whole]
    assert (await only_row(session_factory, Vacancy)).embedding == [0.1, 0.2]
    # Кэш отсева живёт в памяти и из базы не перечитывается: не поправь его — и
    # приём поста сравнивал бы свежий пост с шапкой, которой в строке уже нет.
    (row,) = pipeline.embeddings.matrix.tolist()
    assert row == pytest.approx([0.1, 0.2])


async def test_an_orphan_still_without_its_article_waits_on(monkeypatch,
    parsed, make_pipeline, session_factory
):
    """Объявление, статья которого так и не пришла, ждёт дальше — приговора нет.

    Разбери его сейчас — и по одной шапке модель сочинит описание, а оценщик
    вынесет приговор тому, чего не видел. Ждать дешевле: статья вернётся.
    """
    await _orphan_waiting_for_an_article(session_factory)

    serve_articles(monkeypatch, httpx.ConnectError("сеть отвалилась"))
    pipeline = await make_pipeline(WithMessages(post=post(42, text=WITH_ARTICLE)))

    assert await pipeline.recover_orphan_vacancies() == 0
    assert parsed == []


async def test_an_orphan_that_waited_too_long_is_judged_as_it_is(monkeypatch,
    parsed, make_pipeline, session_factory
):
    """Прождавшее статью дольше срока объявление судят по тому, что есть.

    Иначе ожидание не кончается никогда: сайт может закрыться от нас навсегда
    или лечь насмерть, и строка осталась бы невидимой до конца своих дней —
    ни в списке, ни в отказах, нигде. Убирать по такому тексту нельзя: целым
    он так и не собрался.
    """
    await _orphan_waiting_for_an_article(session_factory, created_at=EPOCH)

    serve_articles(monkeypatch, httpx.ConnectError("сеть отвалилась"))
    pipeline = await make_pipeline(WithMessages(post=post(42, text=WITH_ARTICLE)))

    assert await pipeline.recover_orphan_vacancies() == 1
    assert parsed == [(1, WITH_ARTICLE, "jobs", False)]


async def test_a_parsed_vacancy_is_not_picked_up(parsed, make_pipeline, session_factory):
    """Разобранная вакансия повторно не подбирается."""
    await put(session_factory, vacancy_row(title="готова", is_parsed=True, raw_text="т"))
    pipeline = await make_pipeline()

    assert await pipeline.recover_orphan_vacancies() == 0
    assert parsed == []


async def test_a_vacancy_without_text_cannot_be_picked_up(parsed,
    make_pipeline, session_factory
):
    """Недоразобранная вакансия без текста не подбирается: разбирать нечего."""
    await put(session_factory, vacancy_row(title=None, is_parsed=False, raw_text=""))
    pipeline = await make_pipeline()

    assert await pipeline.recover_orphan_vacancies() == 0
    assert parsed == []


async def test_one_broken_orphan_does_not_stop_the_rest(monkeypatch,
    make_pipeline, session_factory
):
    """Сорвавшийся подбор одной вакансии остальные не отменяет.

    Оборот идёт по всем недоразобранным сразу; потерять из-за одной строки
    все остальные значило бы оставить их полуготовыми до следующего оборота.
    """
    first = vacancy_row(title=None, is_parsed=False, raw_text="первая")
    await put(session_factory, first,
              vacancy_row(title=None, is_parsed=False, raw_text="вторая"))
    pipeline = await make_pipeline()
    calls: list[tuple] = []
    parse_into(monkeypatch, calls, fails={first.id})

    assert await pipeline.recover_orphan_vacancies() == 1
    assert [text for _, text, *_ in calls] == ["вторая"]


async def test_the_window_hears_about_the_recovery(parsed, make_pipeline, session_factory):
    """Окно узнаёт о подборе и о его завершении.

    Подбор идёт до обхода каналов; без гашения полосы следующая стадия
    унаследовала бы его счётчик.
    """
    await put(session_factory, vacancy_row(title=None, is_parsed=False, raw_text="т"))
    pipeline = await make_pipeline()
    heard: list[tuple] = []
    pipeline.on_progress = lambda *args: heard.append(args)

    await pipeline.recover_orphan_vacancies()

    assert heard == [("recover", "Разбор отложенных", 0, 1), ("recover", "", 0, 0)]


async def test_the_sweep_does_not_eat_the_whole_turn(parsed, make_pipeline, session_factory):
    """Подбор берёт за оборот не больше горсти строк, сколько бы их ни ждало.

    Идёт он перед обходом каналов, и каждая ждущая строка стоит похода в
    Telegram и до трёх обращений к чужому сайту по двадцать секунд. Не
    ограничь его — накопившаяся сотня отложила бы свежие объявления на часы,
    а канал бы за это время уехал.
    """
    await put(
        session_factory,
        *[
            vacancy_row(title=None, is_parsed=False, raw_text=f"текст {n}")
            for n in range(rerun.RECOVERED_PER_TURN + 3)
        ],
    )
    pipeline = await make_pipeline()

    assert await pipeline.recover_orphan_vacancies() == rerun.RECOVERED_PER_TURN
    assert len(parsed) == rerun.RECOVERED_PER_TURN


async def test_a_row_the_parse_gave_up_on_is_not_counted(monkeypatch,
    make_pipeline, session_factory
):
    """Строка, на которой разбор сдался, подобранной не считается.

    Счёт этот человек читает в журнале, и завышенный он говорит «всё
    разобрано» там, где строки остались ждать следующего оборота.
    """
    await put(session_factory, vacancy_row(title=None, is_parsed=False, raw_text="текст"))
    pipeline = await make_pipeline()

    parse_into(monkeypatch, [], done=False)

    assert await pipeline.recover_orphan_vacancies() == 0


async def test_a_row_the_parse_gave_up_on_keeps_its_fingerprint(monkeypatch,
    one_vector, make_pipeline, session_factory
):
    """Строка, на которой сдался разбор, отпечатка не меняет.

    Отпечаток идёт следом за разбором, а не рядом с ним: сдался разбор — строка
    осталась какой была, и отпечаток обязан отвечать ей, а не тому тексту, по
    которому разбор не состоялся.
    """
    await put(session_factory, vacancy_row(title=None, is_parsed=False, raw_text="текст"))
    pipeline = await make_pipeline()

    parse_into(monkeypatch, [], done=False)

    await pipeline.recover_orphan_vacancies()

    assert one_vector == []


async def test_nothing_to_recover_is_no_work(make_pipeline):
    """Когда подбирать нечего, ничего и не делается."""
    pipeline = await make_pipeline()
    heard: list[tuple] = []
    pipeline.on_progress = lambda *args: heard.append(args)

    assert await pipeline.recover_orphan_vacancies() == 0
    assert heard == []
