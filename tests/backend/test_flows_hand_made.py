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
from tests.dbio import all_rows, only_row, put
from tests.factories import channel_row, vacancy_row
from tests.fakes.agent import kit_for
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
    pipeline.told = []
    pipeline.order = []

    def told(result):
        pipeline.told.append(result)
        pipeline.order.append("весть")

    async def apply(ids):
        pipeline.applied.append(ids)
        pipeline.order.append("отклик")

    pipeline.on_hand_made = told
    pipeline.apply = apply
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
    orphan = vacancy_row(is_parsed=False, embedding=[0.1, 0.2], raw_text="Ищем QA")
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
    """Повтор узнаётся по адресу поста, заведён ли его канал или нет."""
    if known_channel:
        await put(session_factory, channel_row(username="pyjobs"))
    client = WithMessages(post=_public_post())
    await _post_filed(filing, monkeypatch, client)
    first = await only_row(session_factory, Vacancy)

    await _post_filed(filing, monkeypatch, client)

    assert len(await all_rows(session_factory, Vacancy)) == 1
    assert filing.told[-1] == HandResult("duplicate", first.id)


async def test_a_link_to_a_channel_is_not_a_post(filing, session_factory):
    await ingest_by_hand(kit_for(filing), HandRequest("channel", "https://t.me/pyjobs", None, False))

    assert filing.told == [HandResult("channel_link")]
