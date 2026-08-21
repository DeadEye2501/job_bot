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

from adapters import teletype
from backend.flows import parse as parse_mod
from backend.flows import ingest, rerun
from backend.flows import embeddings
from backend.models import TelegramChannel, Vacancy, VacancyEvent
from backend.payloads import ChannelPost
from tests.backend.fixtures.parse_stub import parse_into
from tests.backend.fixtures.rerun import WithMessages
from tests.dbio import all_rows, only_row, put
from tests.factories import EPOCH, channel_row, vacancy_row
from tests.fakes.telegram import post

WITH_ARTICLE = "Senior QA https://teletype.in/@a/b"
"""Пост, всё содержание которого вынесено в статью по ссылке."""


@pytest.fixture
def parses(monkeypatch):
    """Подставной разбор объявления: список того, о чём его просили.

    Общим домом (`fixtures/parse_stub`), а не своим телом: разъедься у копий
    умолчание `allow_delete`, проверка про запрет зеленела бы на подделке, а
    не на коде. Своё тело осталось у одной проверки — той, где разбор обязан
    сорваться на первой строке и уцелеть на второй.
    """
    calls: list[tuple] = []
    parse_into(monkeypatch, calls)
    return calls


@pytest.fixture(autouse=True)
def embeds(monkeypatch):
    """Подставной отпечаток: список текстов, по которым его считали.

    Подделкой на весь файл, а не по месту: подбор недоразобранного считает
    отпечаток на каждой разобранной строке, и настоящий зов ушёл бы к
    поставщику. У подставного соединения запроса нет вовсе, а беда эта тонет в
    записи журнала — проверки зеленели бы на несработавшем шаге.
    """
    texts: list[str] = []

    async def embed(pipeline, text, what):
        texts.append(text)
        return [0.5, 0.25]

    monkeypatch.setattr(embeddings, "embed_text", embed)
    return texts


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


async def test_an_unfinished_vacancy_is_picked_up_later(parses,
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
    assert parses == [(1, "текст", "", True)]
    assert client.asked == []


async def test_an_orphan_whose_article_arrived_is_judged_in_full(monkeypatch,
    parses, make_pipeline, session_factory
):
    """Дочитанное объявление судят по свежему тексту, и мусор уже можно убрать.

    Приговора у него не было ровно потому, что статья не дошла. Дошла —
    недобор больше ни при чём, и запрет на удаление уходит вместе с ним.
    """
    await _orphan_waiting_for_an_article(session_factory)

    async def fetch_article(_client, _url):
        return "Требования: Python"

    monkeypatch.setattr(teletype, "fetch_article", fetch_article)
    pipeline = await make_pipeline(WithMessages(post=post(42, text=WITH_ARTICLE)))

    assert await pipeline.recover_orphan_vacancies() == 1

    whole = f"{WITH_ARTICLE}\n\nТребования: Python"
    assert parses == [(1, whole, "jobs", True)]
    assert (await only_row(session_factory, Vacancy)).raw_text == whole


async def test_a_dug_out_article_moves_the_fingerprint_too(monkeypatch,
    parses, embeds, make_pipeline, session_factory
):
    """Дочитанная статья двигает и отпечаток строки.

    Отпечаток ей посчитали на приёме — по одной шапке со ссылкой, потому что
    статьи тогда не было. Оставь его как есть, и в отсеве повторов эта строка
    осталась бы шапкой: своё же объявление, пришедшее из соседнего канала уже
    со статьёй, с ней бы не сошлось и завелось второй строкой.
    """
    await _orphan_waiting_for_an_article(session_factory)

    async def fetch_article(_client, _url):
        return "Требования: Python"

    monkeypatch.setattr(teletype, "fetch_article", fetch_article)
    pipeline = await make_pipeline(WithMessages(post=post(42, text=WITH_ARTICLE)))

    assert await pipeline.recover_orphan_vacancies() == 1

    whole = f"{WITH_ARTICLE}\n\nТребования: Python"
    assert embeds == [whole]
    assert (await only_row(session_factory, Vacancy)).embedding == [0.5, 0.25]
    # Кэш отсева живёт в памяти и из базы не перечитывается: не поправь его — и
    # приём поста сравнивал бы свежий пост с шапкой, которой в строке уже нет.
    assert pipeline.embeddings.matrix.tolist() == [[0.5, 0.25]]


async def test_an_orphan_still_without_its_article_waits_on(monkeypatch,
    parses, make_pipeline, session_factory
):
    """Объявление, статья которого так и не пришла, ждёт дальше — приговора нет.

    Разбери его сейчас — и по одной шапке модель сочинит описание, а оценщик
    вынесет приговор тому, чего не видел. Ждать дешевле: статья вернётся.
    """
    await _orphan_waiting_for_an_article(session_factory)

    async def fetch_article(_client, _url):
        raise httpx.ConnectError("сеть отвалилась")

    monkeypatch.setattr(teletype, "fetch_article", fetch_article)
    pipeline = await make_pipeline(WithMessages(post=post(42, text=WITH_ARTICLE)))

    assert await pipeline.recover_orphan_vacancies() == 0
    assert parses == []


async def test_an_orphan_that_waited_too_long_is_judged_as_it_is(monkeypatch,
    parses, make_pipeline, session_factory
):
    """Прождавшее статью дольше срока объявление судят по тому, что есть.

    Иначе ожидание не кончается никогда: сайт может закрыться от нас навсегда
    или лечь насмерть, и строка осталась бы невидимой до конца своих дней —
    ни в списке, ни в отказах, нигде. Убирать по такому тексту нельзя: целым
    он так и не собрался.
    """
    await _orphan_waiting_for_an_article(session_factory, created_at=EPOCH)

    async def fetch_article(_client, _url):
        raise httpx.ConnectError("сеть отвалилась")

    monkeypatch.setattr(teletype, "fetch_article", fetch_article)
    pipeline = await make_pipeline(WithMessages(post=post(42, text=WITH_ARTICLE)))

    assert await pipeline.recover_orphan_vacancies() == 1
    assert parses == [(1, WITH_ARTICLE, "jobs", False)]


async def test_a_parsed_vacancy_is_not_picked_up(parses, make_pipeline, session_factory):
    """Разобранная вакансия повторно не подбирается."""
    await put(session_factory, vacancy_row(title="готова", is_parsed=True, raw_text="т"))
    pipeline = await make_pipeline()

    assert await pipeline.recover_orphan_vacancies() == 0
    assert parses == []


async def test_a_vacancy_without_text_cannot_be_picked_up(parses,
    make_pipeline, session_factory
):
    """Недоразобранная вакансия без текста не подбирается: разбирать нечего."""
    await put(session_factory, vacancy_row(title=None, is_parsed=False, raw_text=""))
    pipeline = await make_pipeline()

    assert await pipeline.recover_orphan_vacancies() == 0
    assert parses == []


async def test_one_broken_orphan_does_not_stop_the_rest(monkeypatch,
    make_pipeline, session_factory
):
    """Сорвавшийся подбор одной вакансии остальные не отменяет.

    Оборот идёт по всем недоразобранным сразу; потерять из-за одной строки
    все остальные значило бы оставить их полуготовыми до следующего оборота.
    """
    await put(
        session_factory,
        vacancy_row(title=None, is_parsed=False, raw_text="первая"),
        vacancy_row(title=None, is_parsed=False, raw_text="вторая"),
    )
    pipeline = await make_pipeline()
    done: list[str] = []

    async def parse(pipeline, vacancy_id, text, username, allow_delete=True):
        if text == "первая":
            raise RuntimeError("не разобралось")
        done.append(text)
        return True

    monkeypatch.setattr(parse_mod, "parse_and_update_vacancy", parse)

    assert await pipeline.recover_orphan_vacancies() == 1
    assert done == ["вторая"]


async def test_the_window_hears_about_the_recovery(parses, make_pipeline, session_factory):
    """Окно узнаёт о подборе и о его завершении.

    Подбор идёт до обхода каналов; без гашения полосы следующая стадия
    унаследовала бы его счётчик.
    """
    await put(session_factory, vacancy_row(title=None, is_parsed=False, raw_text="т"))
    pipeline = await make_pipeline()
    heard: list[tuple] = []
    pipeline.on_progress = lambda *args: heard.append(args)

    await pipeline.recover_orphan_vacancies()

    assert heard == [("recover", "", 0, 1), ("recover", "", 0, 0)]


async def test_the_sweep_does_not_eat_the_whole_turn(parses, make_pipeline, session_factory):
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
    assert len(parses) == rerun.RECOVERED_PER_TURN


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
    embeds, make_pipeline, session_factory
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

    assert embeds == []


async def test_nothing_to_recover_is_no_work(make_pipeline):
    """Когда подбирать нечего, ничего и не делается."""
    pipeline = await make_pipeline()
    heard: list[tuple] = []
    pipeline.on_progress = lambda *args: heard.append(args)

    assert await pipeline.recover_orphan_vacancies() == 0
    assert heard == []
