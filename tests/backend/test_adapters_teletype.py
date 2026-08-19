"""Следствия, которые наблюдают тесты `adapters/teletype.py`.

Страница собирается здесь короткой, но с той же разметкой, что у настоящей:
teletype размечает заголовок и тело статьи по schema.org, и держится разбор
именно за неё. Собери страницу без разметки — и проверки зеленели бы на
поиске по именам стилей, которого в боевом коде нет.
"""

import httpx
import pytest

from adapters import teletype


def _page(*, headline: str = "Senior Manual QA", body: str = "<p>Ищем QA</p>") -> str:
    """Страница статьи в той разметке, в какой её отдаёт teletype."""
    return (
        "<html><body>"
        f'<h1 itemprop="headline">{headline}</h1>'
        f'<article itemprop="articleBody">{body}</article>'
        "</body></html>"
    )


def _client(handler) -> httpx.AsyncClient:
    """Клиент к поддельному teletype: обращения уходят в переданный обработчик."""
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def test_the_article_comes_back_with_its_headline():
    """Из страницы достаются и заголовок, и тело статьи."""
    async with _client(lambda _r: httpx.Response(200, text=_page())) as client:
        got = await teletype.fetch_article(client, "https://teletype.in/@a/b")

    assert got == "Senior Manual QA\n\nИщем QA"


async def test_the_article_body_keeps_its_lines():
    """Строки тела остаются строками, а не сливаются в одну.

    Требования в статьях идут списком, и слитые в строку они читаются
    разбором как одно предложение.
    """
    body = "<ul><li>Python</li><li>SQL</li></ul>"
    async with _client(lambda _r: httpx.Response(200, text=_page(body=body))) as client:
        got = await teletype.fetch_article(client, "https://teletype.in/@a/b")

    assert got == "Senior Manual QA\n\nPython\nSQL"


async def test_an_article_without_a_headline_comes_back_without_it():
    """Статья без размеченного заголовка отдаётся одним телом.

    Пустой строки перед текстом при этом не появляется: в разборе она читалась
    бы как оборванный заголовок.
    """
    page = '<html><body><article itemprop="articleBody">Ищем QA</article></body></html>'
    async with _client(lambda _r: httpx.Response(200, text=page)) as client:
        got = await teletype.fetch_article(client, "https://teletype.in/@a/b")

    assert got == "Ищем QA"


async def test_an_empty_article_gives_nothing():
    """Размеченное, но пустое тело — та же пустота, что и его отсутствие.

    Дописывать к объявлению один заголовок статьи незачем: он и так стоит в
    посте, а разбор примет повтор за второе название.
    """
    async with _client(lambda _r: httpx.Response(200, text=_page(body=""))) as client:
        assert await teletype.fetch_article(client, "https://teletype.in/@a/b") is None


async def test_a_page_without_an_article_gives_nothing():
    """Страница без размеченного тела статьи не даёт ничего.

    По адресу статьи может лежать страница автора или весть о том, что
    статью снесли: объявление от этого объявлением быть не перестаёт.
    """
    page = "<html><body><h1>Автор</h1></body></html>"
    async with _client(lambda _r: httpx.Response(200, text=page)) as client:
        assert await teletype.fetch_article(client, "https://teletype.in/@a") is None


@pytest.mark.parametrize(
    "trouble",
    [
        pytest.param(httpx.Response(500, text="упал"), id="сайт упал"),
        pytest.param(httpx.Response(429, text="частишь"), id="просят подождать"),
        pytest.param(httpx.Response(403, text="не пущу"), id="не пустили"),
        pytest.param(httpx.Response(408, text="долго"), id="истекло ожидание"),
        pytest.param(httpx.ConnectError("сеть отвалилась"), id="обрыв связи"),
    ],
)
async def test_a_site_that_did_not_answer_says_so(trouble):
    """Не отдали страницу — беда идёт наружу, а не притворяется пустотой.

    Различать это обязан зовущий: «страницу не отдали» — беда на час, и
    сохранённый текст вакансии переписывать нельзя; «статьи там нет» —
    навсегда, и держаться за сохранённый текст незачем.
    """

    def handle(_request):
        if isinstance(trouble, BaseException):
            raise trouble
        return trouble

    async with _client(handle) as client:
        with pytest.raises(httpx.HTTPError):
            await teletype.fetch_article(client, "https://teletype.in/@a/b")


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        pytest.param(
            "вся вакансия https://teletype.in/@courierus/OxPcuC1iLUU",
            ["https://teletype.in/@courierus/OxPcuC1iLUU"],
            id="адрес словами",
        ),
        pytest.param(
            "ПОСМОТРЕТЬ (https://teletype.in/@courierus/OxPcuC1iLUU)",
            ["https://teletype.in/@courierus/OxPcuC1iLUU"],
            id="адрес за подписью ссылки",
        ),
        pytest.param(
            "вся вакансия https://teletype.in/@courierus/OxPcuC1iLUU.",
            ["https://teletype.in/@courierus/OxPcuC1iLUU"],
            id="точка в конце предложения",
        ),
        pytest.param(
            "тут https://teletype.in/@a/b, а ещё тут",
            ["https://teletype.in/@a/b"],
            id="запятая после адреса",
        ),
        pytest.param("наш канал https://teletype.in/@courierus", [], id="страница автора"),
        pytest.param("пишите @courierus", [], id="ник без адреса"),
        pytest.param("https://habr.com/@a/b", [], id="чужой сайт"),
    ],
)
def test_which_addresses_count_as_an_article(text, expected):
    """Адрес статьи узнаётся в тексте объявления и не прихватывает лишнего.

    Скобка отдельно: адрес спрятанной ссылки дописывают в текст именно в
    скобках, и утащенная в адрес закрывающая скобка вела бы в никуда.
    """
    assert teletype.ARTICLE_URL_RE.findall(text) == expected


@pytest.mark.parametrize(
    "code",
    [
        pytest.param(404, id="страницу снесли"),
        pytest.param(410, id="страница ушла навсегда"),
        pytest.param(451, id="страницу закрыли по закону"),
    ],
)
async def test_a_page_that_will_never_come_back_gives_nothing(code):
    """Отказ, который завтра не пройдёт, читается как «статьи там нет».

    Снесённая статья не вернётся ни к утру, ни к концу недели. Считай её
    бедой на час — и прогон заново перестал бы обновлять текст такой вакансии
    до конца её дней, сколько бы раз человек ни нажимал кнопку; на приёме
    поста тот же отказ запрещал бы удалять настоящий мусор.

    Соседние отказы того же семейства — «не пустили» и «истекло ожидание» —
    вечными не считаются: они про нас, а не про страницу, и завтра проходят.

    Страница при этом отдаётся годной, с разметкой: пустота от неразобранной
    страницы выглядела бы так же, и тест зеленел бы, не читая кода ответа.
    """
    async with _client(lambda _r: httpx.Response(code, text=_page())) as client:
        assert await teletype.fetch_article(client, "https://teletype.in/@a/x") is None
