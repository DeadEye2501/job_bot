"""Имя агрегатора: как сервис зовут люди, а не его адрес.

Главная страница и модель подделаны; разбор страницы и ответа — боевые.
"""

import httpx

from backend.flows.aggregator_name import create_named_aggregator
from backend.models import Aggregator
from backend.provider_config import LlmProviderConfig
from tests.dbio import only_row, put
from tests.factories_aggregators import aggregator_row
from tests.fakes.llm import CHAT, chat_response, provider
from tests.fakes.site_home import home_page, serve_home

CHAT_MODEL = LlmProviderConfig(base_url="http://provider.test", api_key="", model="m")

_DECLARED = '<meta property="og:site_name" content="Пример Работа">'


def _model_says(monkeypatch, answer: httpx.Response | BaseException) -> list:
    """Модель отвечает заготовленным; отдаёт список ушедших к ней запросов."""
    client = provider({CHAT: answer})
    monkeypatch.setattr("adapters.lm_studio.make_client", lambda _cfg: client)
    return client.sent


async def _name_of_created(session_factory, chat: LlmProviderConfig | None) -> str:
    """Имя, под которым агрегатор заводится по адресу."""
    row, _ = await create_named_aggregator(session_factory, "jobs.example.com", chat)
    return row.name


async def test_the_model_answer_is_the_name_with_a_capital_letter(monkeypatch, session_factory):
    serve_home(monkeypatch, home_page(head=_DECLARED))
    sent = _model_says(monkeypatch, chat_response("пример Карьера"))

    assert await _name_of_created(session_factory, CHAT_MODEL) == "Пример Карьера"
    assert "Пример Работа" in sent[0].content.decode()


async def test_a_rambling_model_answer_gives_way_to_the_declared_name(monkeypatch, session_factory):
    serve_home(monkeypatch, home_page(head=_DECLARED))
    _model_says(monkeypatch, chat_response("Пример Работа\nэто сайт вакансий"))

    assert await _name_of_created(session_factory, CHAT_MODEL) == "Пример Работа"


async def test_the_title_part_naming_the_site_stands_in_for_a_silent_model(monkeypatch, session_factory):
    serve_home(monkeypatch, home_page(head="<title>Работа и вакансии | example</title>"))

    assert await _name_of_created(session_factory, None) == "Example"


async def test_without_hints_and_model_the_name_is_the_site_label(monkeypatch, session_factory):
    serve_home(monkeypatch, home_page())

    assert await _name_of_created(session_factory, None) == "Example"


async def test_an_unreachable_site_does_not_block_creation(monkeypatch, session_factory):
    serve_home(monkeypatch, httpx.ConnectError("сеть отвалилась"))
    _model_says(monkeypatch, httpx.ConnectError("модель молчит"))

    row, status = await create_named_aggregator(session_factory, "https://example.com/jobs", CHAT_MODEL)

    assert (status, row.host, row.name) == ("created", "example.com", "Example")
    assert (await only_row(session_factory, Aggregator)).name == "Example"


async def test_an_address_the_client_cannot_even_build_does_not_block_creation(
    monkeypatch, session_factory
):
    """Негодный адрес клиент отвергает ещё до сети, и не ошибкой HTTP."""
    serve_home(monkeypatch, home_page())

    row, status = await create_named_aggregator(session_factory, "exa\tmple.com", None)

    assert (status, row.avatar) == ("created", None)


_ICON = b"\x89PNG\r\n\x1a\n-icon-"


def _image(body: bytes = _ICON) -> httpx.Response:
    return httpx.Response(200, content=body, headers={"content-type": "image/png"})


async def test_the_icon_the_page_declares_becomes_the_avatar(monkeypatch, session_factory):
    serve_home(monkeypatch, home_page(head='<link rel="icon" href="/static/i.png">'),
               {"/static/i.png": _image()})

    row, _ = await create_named_aggregator(session_factory, "example.com", None)

    assert row.avatar == _ICON
    assert (await only_row(session_factory, Aggregator)).avatar == _ICON


async def test_without_a_declared_icon_the_site_favicon_is_taken(monkeypatch, session_factory):
    serve_home(monkeypatch, home_page(), {"/favicon.ico": _image(b"ico")})

    row, _ = await create_named_aggregator(session_factory, "example.com", None)

    assert row.avatar == b"ico"


async def test_a_broken_icon_address_gives_way_to_the_next_one(monkeypatch, session_factory):
    """Адрес значка пишет сайт, и негодный клиент отвергает ещё до сети."""
    head = '<link rel="icon" href="https://example.com:abc/i.png">'
    serve_home(monkeypatch, home_page(head=head), {"/favicon.ico": _image(b"ico")})

    row, _ = await create_named_aggregator(session_factory, "example.com", None)

    assert row.avatar == b"ico"


async def test_a_vector_icon_gives_way_to_a_picture(monkeypatch, session_factory):
    """Векторный значок окно не покажет: он вшивается картинкой, а не разметкой."""
    head = '<link rel="icon" href="/i.svg" type="image/svg+xml"><link rel="apple-touch-icon" href="/t.png">'
    serve_home(monkeypatch, home_page(head=head), {"/t.png": _image(b"touch")})

    row, _ = await create_named_aggregator(session_factory, "example.com", None)

    assert row.avatar == b"touch"


async def test_a_site_without_an_icon_is_created_without_one(monkeypatch, session_factory):
    serve_home(monkeypatch, home_page(), {"/favicon.ico": httpx.Response(404)})

    row, status = await create_named_aggregator(session_factory, "example.com", None)

    assert (status, row.avatar) == ("created", None)


async def test_a_page_answering_instead_of_a_picture_is_not_an_icon(monkeypatch, session_factory):
    """Сайты отдают на неизвестный путь страницу «не найдено» с кодом 200."""
    serve_home(monkeypatch, home_page(), {"/favicon.ico": httpx.Response(200, text="<html>нет</html>")})

    row, _ = await create_named_aggregator(session_factory, "example.com", None)

    assert row.avatar is None


async def test_a_known_site_is_not_asked_again(monkeypatch, session_factory):
    await put(session_factory, aggregator_row(host="example.com", name="Старое"))
    serve_home(monkeypatch, httpx.ConnectError("сюда ходить не должны"))

    row, status = await create_named_aggregator(session_factory, "example.com", None)

    assert (status, row.name) == ("exists", "Старое")
