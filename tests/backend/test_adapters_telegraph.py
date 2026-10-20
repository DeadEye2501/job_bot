"""Следствия, которые наблюдают тесты `adapters/telegraph.py`.

Страница собирается здесь короткой, но с той же разметкой, что у настоящей:
Telegraph кладёт статью целиком — вместе с заголовком — в тег `article`, и
держится разбор именно за него. Собери страницу без этого тега — и проверки
зеленели бы на поиске по именам стилей, которого в боевом коде нет.
"""

import httpx
import pytest

from adapters import telegraph


def _page(*, headline: str = "Senior Manual QA", body: str = "<p>Ищем QA</p>") -> str:
    """Страница статьи в той разметке, в какой её отдаёт Telegraph."""
    return (
        "<html><body>"
        '<article id="_tl_editor" class="tl_article_content">'
        f"<h1>{headline}</h1><address></address>{body}"
        "</article>"
        "</body></html>"
    )


def _client(handler) -> httpx.AsyncClient:
    """Клиент к поддельному Telegraph: обращения уходят в переданный обработчик."""
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def test_the_article_comes_back_with_its_headline():
    """Из страницы достаются и заголовок, и тело статьи."""
    async with _client(lambda _r: httpx.Response(200, text=_page())) as client:
        got = await telegraph.fetch_article(client, "https://telegra.ph/Senior-QA-08-21")

    assert got == "Senior Manual QA\n\nИщем QA"


async def test_the_article_body_keeps_its_lines():
    """Строки тела остаются строками, а не сливаются в одну.

    Требования в статьях идут списком, и слитые в строку они читаются
    разбором как одно предложение.
    """
    body = "<ul><li>Python</li><li>SQL</li></ul>"
    async with _client(lambda _r: httpx.Response(200, text=_page(body=body))) as client:
        got = await telegraph.fetch_article(client, "https://telegra.ph/Senior-QA-08-21")

    assert got == "Senior Manual QA\n\nPython\nSQL"


async def test_an_article_without_a_headline_comes_back_without_it():
    """Статья без заголовка отдаётся одним телом.

    Пустой строки перед текстом при этом не появляется: в разборе она читалась
    бы как оборванный заголовок.
    """
    page = (
        "<html><body>"
        '<article id="_tl_editor" class="tl_article_content"><p>Ищем QA</p></article>'
        "</body></html>"
    )
    async with _client(lambda _r: httpx.Response(200, text=page)) as client:
        got = await telegraph.fetch_article(client, "https://telegra.ph/Senior-QA-08-21")

    assert got == "Ищем QA"


async def test_only_the_first_headline_leaves_the_body():
    """Заголовком считается первый `h1`, остальное остаётся телом статьи.

    Своих подзаголовков Telegraph размечает `h3` и `h4`, но вставить второй
    `h1` в статью автору никто не мешает, и такой заголовок — часть текста,
    а не второе название вакансии.
    """
    body = "<h1>Про компанию</h1><p>Ищем QA</p>"
    async with _client(lambda _r: httpx.Response(200, text=_page(body=body))) as client:
        got = await telegraph.fetch_article(client, "https://telegra.ph/Senior-QA-08-21")

    assert got == "Senior Manual QA\n\nПро компанию\nИщем QA"


async def test_an_article_of_one_headline_gives_nothing():
    """Статья из одного заголовка — та же пустота, что и её отсутствие.

    Дописывать к объявлению один заголовок статьи незачем: он и так стоит в
    посте, а разбор примет повтор за второе название.
    """
    async with _client(lambda _r: httpx.Response(200, text=_page(body=""))) as client:
        assert (
            await telegraph.fetch_article(client, "https://telegra.ph/Senior-QA-08-21")
            is None
        )


async def test_a_page_without_an_article_gives_nothing():
    """Страница без тега статьи не даёт ничего.

    По адресу статьи может лежать весть о том, что её снесли: объявление от
    этого объявлением быть не перестаёт.
    """
    page = "<html><body><h1>Статья не найдена</h1></body></html>"
    async with _client(lambda _r: httpx.Response(200, text=page)) as client:
        assert (
            await telegraph.fetch_article(client, "https://telegra.ph/Senior-QA-08-21")
            is None
        )


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
            await telegraph.fetch_article(client, "https://telegra.ph/Senior-QA-08-21")


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
        assert (
            await telegraph.fetch_article(client, "https://telegra.ph/Senior-QA-08-21")
            is None
        )
