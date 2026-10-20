"""Заявка окна «Добавить вакансию», которую ведёт бот: поля с переключателем, текст, пост.

Поля с выключенным переключателем бот не видит — их заводит мост сам; сюда они
приходят, только когда заведённое надо отдать откликателю.
"""

import httpx
import pytest
from pyrogram.errors import ChannelPrivate, UsernameNotOccupied

from backend.flows.hand_made import HandRequest, ingest_by_hand
from backend.flows.hand_outcome import HandResult
from backend.models import Vacancy, VacancyEvent
from backend.repository.vacancies_new import HAND_MADE
from backend.telegram_time import tg_moment
from tests.backend.fixtures.flows import told_then_applied
from tests.dbio import all_rows, only_row, put
from tests.factories import channel_row, vacancy_row
from tests.factories_aggregators import web_search_row
from tests.fakes.agent import kit_for, scripted_kit, submit_step
from tests.fakes.telegram import WithMessages
from tests.fakes.telegram_objects import TG_EPOCH, chat, post
from tests.fakes.telegraph import serve_articles


def _fields(**overrides) -> dict:
    """Поля формы так, как их прочитал мост (`read_new_vacancy_fields`)."""
    return {
        "title": "Python-разработчик", "company_id": None, "hr_id": None, "source_url": None,
        "location": None, "remote": None, "grade": None, "salary_min": None, "salary_max": None,
        "salary_currency": None, "stack_required": ["Python"], "stack_preferred": [],
        "description": "Набрано руками", "notes": None, "posted_at": None, **overrides,
    }


@pytest.fixture
async def filing(make_pipeline):
    """Конвейер, у которого весть окну и отклик пишутся в один след `order`."""
    pipeline = await make_pipeline()
    told_then_applied(pipeline)
    return pipeline


async def test_fields_with_the_switch_are_filed_and_handed_over(filing, session_factory):
    """Набранное человеком — уже готовый разбор: модель его не трогает, строка
    в New, откликатель зван по режиму."""
    await ingest_by_hand(kit_for(filing), HandRequest("fields", _fields(), None, True))

    saved = await only_row(session_factory, Vacancy)
    assert (saved.title, saved.description, saved.raw_text, saved.is_parsed) == (
        "Python-разработчик", "Набрано руками", None, True,
    )
    assert filing.told == [HandResult("ok", saved.id)]
    assert filing.applied == [[saved.id]]
    assert filing.order == ["весть", "отклик"]


async def test_fields_of_a_page_filed_before_are_not_handed_over(filing, session_factory):
    """Повтор не заводится и не отдаётся: окно переходит на существующую."""
    existing = vacancy_row(source_url="https://hh.ru/vacancy/123")
    await put(session_factory, existing)

    await ingest_by_hand(
        kit_for(filing), HandRequest("fields", _fields(source_url="https://hh.ru/vacancy/123"), None, True)
    )

    assert len(await all_rows(session_factory, Vacancy)) == 1
    assert filing.told == [HandResult("duplicate", existing.id)]
    assert filing.applied == []


async def _post_filed(filing, monkeypatch, client, url="https://t.me/s/PyJobs/5?single", hands_over=False):
    """Завести вакансию по ссылке на пост через этого клиента Telegram."""
    monkeypatch.setattr(filing, "client", client)
    await ingest_by_hand(kit_for(filing), HandRequest("post", url, None, hands_over))


def _public_post(text="Ищем QA в команду"):
    return post(5, text=text, chat=chat(id=-1001, username="PyJobs"))


@pytest.mark.usefixtures("one_vector")
async def test_a_post_of_a_public_channel_is_filed_by_hand(filing, session_factory, monkeypatch, parsed):
    """Публичный канал читается и без подписки; дата — дата сообщения, а
    строка помечена заведённой вручную, с постом в нагрузке."""
    await _post_filed(filing, monkeypatch, WithMessages(post=_public_post()))

    saved = await only_row(session_factory, Vacancy)
    assert (saved.source_url, saved.raw_text, saved.posted_at) == (
        "https://t.me/PyJobs/5", "Ищем QA в команду", tg_moment(TG_EPOCH),
    )
    (event,) = await all_rows(session_factory, VacancyEvent)
    assert (event.kind, event.payload) == (HAND_MADE, {"via": "ingested", "channel": "PyJobs", "msg_id": 5})
    assert parsed == [(saved.id, "Ищем QA в команду", "PyJobs", True)]
    assert filing.told == [HandResult("ok", saved.id)] and filing.applied == []


@pytest.mark.usefixtures("one_vector")
async def test_a_post_of_a_known_channel_is_tied_to_it(filing, session_factory, monkeypatch, parsed):
    channel = channel_row(username="pyjobs")
    await put(session_factory, channel)

    await _post_filed(filing, monkeypatch, WithMessages(post=_public_post()))

    saved = await only_row(session_factory, Vacancy)
    assert (saved.source_channel_id, saved.source_msg_id) == (channel.id, 5)


@pytest.mark.usefixtures("one_vector")
async def test_a_post_of_a_closed_channel_keeps_the_pasted_address(filing, session_factory, monkeypatch, parsed):
    """У закрытого канала ника нет: источник — адрес, вставленный человеком."""
    url = "https://t.me/c/123/5"
    await _post_filed(filing, monkeypatch, WithMessages(post=post(5, text="Ищем QA", chat=chat(id=-100123))), url)

    saved = await only_row(session_factory, Vacancy)
    assert (saved.source_url, saved.source_channel_id) == (url, None)
    assert parsed[0][2] is None


@pytest.mark.usefixtures("one_vector")
async def test_a_post_by_hand_is_handed_over_by_the_switch(filing, session_factory, monkeypatch, parsed):
    await _post_filed(filing, monkeypatch, WithMessages(post=_public_post()), hands_over=True)

    saved = await only_row(session_factory, Vacancy)
    assert filing.applied == [[saved.id]] and filing.order == ["весть", "отклик"]


@pytest.mark.parametrize(("client", "said"), [
    (WithMessages(error=ChannelPrivate()), "tg_private"),
    (WithMessages(error=UsernameNotOccupied()), "tg_invalid"),
    (WithMessages(post=post(5, empty=True)), "no_post"),
    (WithMessages(post=post(5, text=None, chat=chat(id=-1001, username="pyjobs"))), "empty_post"),
], ids=["закрыт", "нет канала", "удалён", "без текста"])
async def test_a_post_that_cannot_be_filed_says_why(filing, session_factory, monkeypatch, client, said):
    await _post_filed(filing, monkeypatch, client)

    assert await all_rows(session_factory, Vacancy) == []
    assert filing.told == [HandResult(said)]


async def test_a_post_whose_article_did_not_load_is_not_filed(filing, session_factory, monkeypatch):
    serve_articles(monkeypatch, httpx.ConnectError("сеть"))

    await _post_filed(filing, monkeypatch, WithMessages(post=_public_post("QA https://telegra.ph/QA-08-21")))

    assert await all_rows(session_factory, Vacancy) == []
    assert filing.told == [HandResult("article")]


@pytest.mark.usefixtures("one_vector")
async def test_a_post_by_hand_does_not_merge_with_a_similar_row(filing, session_factory, monkeypatch, parsed):
    """Сходство однозначного повтора не даёт: пост заводится своей строкой, а
    брошенная похожая остаётся подбору недоразобранного."""
    orphan = vacancy_row(is_parsed=False, embedding=[0.1, 0.25], raw_text="Ищем QA")
    await put(session_factory, orphan)

    await _post_filed(filing, monkeypatch, WithMessages(post=_public_post()))

    assert len(await all_rows(session_factory, Vacancy)) == 2
    assert orphan.id not in [one[0] for one in parsed]


async def test_a_post_without_a_fingerprint_is_not_filed(filing, session_factory, monkeypatch, silent_embedder):
    await _post_filed(filing, monkeypatch, WithMessages(post=_public_post()))

    assert await all_rows(session_factory, Vacancy) == []
    assert filing.told == [HandResult("embed")]


@pytest.mark.usefixtures("one_vector")
@pytest.mark.parametrize("known_channel", [True, False], ids=["канал заведён", "канал не заведён"])
async def test_the_same_post_twice_is_a_duplicate(filing, session_factory, monkeypatch, parsed, known_channel):
    """Повтор узнаётся по адресу поста, заведён ли его канал или нет.

    Первый заход разобран — подставной разбор строку не отмечает, и это
    делается здесь: неразобранная повтором не считается."""
    if known_channel:
        await put(session_factory, channel_row(username="pyjobs"))
    client = WithMessages(post=_public_post())
    await _post_filed(filing, monkeypatch, client)
    first = await only_row(session_factory, Vacancy)
    async with session_factory() as session:
        (await session.get(Vacancy, first.id)).is_parsed = True
        await session.commit()

    await _post_filed(filing, monkeypatch, client)

    assert len(await all_rows(session_factory, Vacancy)) == 1
    assert filing.told[-1] == HandResult("duplicate", first.id)


async def test_a_link_to_a_channel_is_not_a_post(filing, session_factory):
    await ingest_by_hand(kit_for(filing), HandRequest("channel", "https://t.me/pyjobs", None, False))

    assert filing.told == [HandResult("channel_link")]


async def test_another_telegram_link_has_no_vacancy_and_no_agent(filing, session_factory):
    """Мгновенный просмотр постом не разбирается, а в Telegram агенту хода нет."""
    sessions = []

    async def agent(plan):
        sessions.append(plan)

    await ingest_by_hand(kit_for(filing, run_session=agent), HandRequest("telegram", "https://t.me/iv?url=x", None, False))

    assert filing.told == [HandResult("no_vacancy")] and sessions == []


@pytest.mark.usefixtures("one_vector")
@pytest.mark.parametrize("hands_over", [True, False], ids=["с откликом", "без отклика"])
async def test_a_page_goes_to_the_agent_as_made_by_hand(make_pipeline, session_factory, parsed, hands_over):
    """Страницу заводит агент, а строка — заведённая человеком: окно слышит
    итог, откликатель зван по переключателю окна."""
    url = "https://company.test/qa"
    await put(session_factory, web_search_row())
    kit = scripted_kit(await make_pipeline(), [submit_step(url, "Ищем QA в команду")])
    told_then_applied(kit.pipeline)

    await ingest_by_hand(kit, HandRequest("page", url, None, hands_over))

    saved = await only_row(session_factory, Vacancy)
    (event,) = await all_rows(session_factory, VacancyEvent)
    assert event.kind == HAND_MADE and kit.pipeline.told == [HandResult("ok", saved.id)]
    assert kit.pipeline.applied == ([[saved.id]] if hands_over else [])


@pytest.mark.usefixtures("one_vector")
async def test_an_article_link_goes_the_way_of_pasted_text(filing, session_factory, monkeypatch, parsed):
    """Статья по ссылке — тот же вставленный текст из одной ссылки: склейка
    дочитывает статью, повтор не проверяется."""
    serve_articles(monkeypatch)

    await ingest_by_hand(kit_for(filing), HandRequest("article", "https://telegra.ph/QA-08-21", None, False))

    saved = await only_row(session_factory, Vacancy)
    assert "Требования" in saved.raw_text
    assert filing.told == [HandResult("ok", saved.id)]


@pytest.mark.parametrize("kind, url, msg_id", [
    ("post", "https://t.me/pyjobs/5", 5),
    ("page", "https://hh.ru/vacancy/123", None),
], ids=["пост", "страница"])
async def test_a_link_filed_before_is_a_duplicate_before_anything_else(filing, session_factory, kind, url, msg_id):
    """Однозначный повтор узнаётся первым: ни Telegram, ни агента, ни строки, ни
    откликателя — окно переходит на существующую."""
    existing = vacancy_row(is_parsed=True, source_url=url, source_msg_id=msg_id)
    await put(session_factory, existing)

    await ingest_by_hand(kit_for(filing), HandRequest(kind, url, None, True))

    assert len(await all_rows(session_factory, Vacancy)) == 1
    assert filing.told == [HandResult("duplicate", existing.id)] and filing.applied == []


@pytest.mark.usefixtures("one_vector")
async def test_an_unparsed_row_at_the_same_address_is_replaced(filing, session_factory, monkeypatch, parsed):
    """Недоразобранная прав не имеет: повтор с ней её сносит, и пост заводится
    заново тем, что принёс человек."""
    stale = vacancy_row(is_parsed=False, raw_text="шапка", source_url="https://t.me/PyJobs/5", source_msg_id=5)
    await put(session_factory, stale)

    await _post_filed(filing, monkeypatch, WithMessages(post=_public_post()), url="https://t.me/PyJobs/5")

    saved = await only_row(session_factory, Vacancy)
    assert (saved.raw_text, saved.is_parsed) == ("Ищем QA в команду", False)
    assert parsed == [(saved.id, "Ищем QA в команду", "PyJobs", True)]
    assert filing.told == [HandResult("ok", saved.id)]


async def test_the_parsed_row_behind_an_unparsed_one_is_the_duplicate(filing, session_factory):
    """По адресу две строки: недоразобранная прав не имеет и сносится, повтор —
    разобранная за ней, а не новая третья строка."""
    stale = vacancy_row(is_parsed=False, source_url="https://hh.ru/vacancy/123")
    kept = vacancy_row(is_parsed=True, source_url="https://hh.ru/vacancy/123?from=main")
    await put(session_factory, stale, kept)

    await ingest_by_hand(kit_for(filing), HandRequest("page", "https://hh.ru/vacancy/123", None, True))

    assert [row.id for row in await all_rows(session_factory, Vacancy)] == [kept.id]
    assert filing.told == [HandResult("duplicate", kept.id)]


@pytest.mark.usefixtures("one_vector")
async def test_a_post_linked_from_fields_is_filed_by_its_link(filing, session_factory, monkeypatch, parsed):
    """Ссылка на пост у набранной в «Полях» — упоминание и для поста по ссылке:
    вторая вакансия того же поста заводится, а не уводит на набранную."""
    await put(session_factory, vacancy_row(is_parsed=True, source_url="https://t.me/PyJobs/5"))

    await _post_filed(filing, monkeypatch, WithMessages(post=_public_post()), url="https://t.me/PyJobs/5")

    assert len(await all_rows(session_factory, Vacancy)) == 2
    assert filing.told[-1].outcome == "ok"


@pytest.mark.usefixtures("one_vector")
async def test_the_same_text_pasted_again_is_a_duplicate(filing, session_factory, parsed):
    """Тот же текст даёт отпечаток не рядом, а в той же точке: это та же вакансия."""
    existing = vacancy_row(is_parsed=True, embedding=[0.1, 0.2])
    await put(session_factory, existing)

    await ingest_by_hand(kit_for(filing), HandRequest("text", "Ищем QA", None, True))

    assert len(await all_rows(session_factory, Vacancy)) == 1
    assert filing.told == [HandResult("duplicate", existing.id)] and filing.applied == []


@pytest.mark.usefixtures("one_vector")
async def test_the_same_text_as_an_unparsed_row_replaces_it(filing, session_factory, parsed):
    stale = vacancy_row(is_parsed=False, raw_text="Ищем QA", embedding=[0.1, 0.2], title="старая")
    await put(session_factory, stale)

    await ingest_by_hand(kit_for(filing), HandRequest("text", "Ищем QA", None, False))

    saved = await only_row(session_factory, Vacancy)
    assert saved.title is None and filing.told == [HandResult("ok", saved.id)]


@pytest.mark.usefixtures("one_vector")
async def test_a_text_only_like_a_filed_one_gets_its_own_row(filing, session_factory, parsed):
    """Похожий, но не тот же текст повтором не считается: сходство однозначного
    повтора не даёт."""
    await put(session_factory, vacancy_row(is_parsed=True, embedding=[0.1, 0.25]))

    await ingest_by_hand(kit_for(filing), HandRequest("text", "Ищем QA", None, False))

    assert len(await all_rows(session_factory, Vacancy)) == 2


async def test_fields_linking_a_post_of_another_vacancy_are_filed(filing, session_factory):
    """В посте бывает несколько вакансий: ссылка на пост у набранной в «Полях» —
    упоминание, а не её собственный адрес, и повтором не считается."""
    await put(session_factory, vacancy_row(is_parsed=True, source_url="https://t.me/pyjobs/5"))

    await ingest_by_hand(kit_for(filing), HandRequest("fields", _fields(source_url="https://t.me/pyjobs/5"), None, False))

    assert len(await all_rows(session_factory, Vacancy)) == 2
    assert filing.told[0].outcome == "ok"


