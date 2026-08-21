"""Что бот делает с очередным объявлением из канала.

Каждый пост переводится в вектор и сравнивается с уже собранными. Совпало —
это перепост: каналы переопубликовывают друг друга постоянно, и без сравнения
список вакансий забился бы одним и тем же объявлением в пяти видах.

У совпадения есть второй случай: вакансия, у которой вектор есть, а разбор не
кончился. Такую не пропускают, а дописывают — иначе она осталась бы
полуготовой навсегда, потому что каждый следующий перепост объявлял бы её
повтором и проходил мимо.

Служебные записи и опросы до сравнения не доходят вовсе: вакансий в них нет.
"""

import pytest

import httpx

from adapters import teletype
from backend.flows import embeddings, ingest
from backend.flows import parse as parse_mod
from tests.backend.fixtures.parse_stub import parse_into
from tests.fakes.telegram import link_entity, post


@pytest.fixture
async def intake(make_pipeline, monkeypatch):
    """Конвейер с подставным переводом в вектор, сохранением и разбором."""
    pipeline = await make_pipeline()
    pipeline.saved = []
    pipeline.parsed = []
    pipeline.new_id = 7
    pipeline.similar_id = None
    pipeline.unparsed = False

    async def embed(client, model, text):
        pipeline.embedded = text
        return [0.1, 0.2]

    async def save(pipeline, post, embedding):
        pipeline.saved.append((post.channel_id, post.msg.id, post.text))
        return pipeline.new_id

    async def unparsed(pipeline, vacancy_id):
        return pipeline.unparsed

    monkeypatch.setattr("adapters.lm_embed.embed", embed)
    monkeypatch.setattr(
        pipeline.embeddings,
        "match",
        lambda vector, threshold: pipeline.similar_id,
    )
    monkeypatch.setattr(ingest, "save_new_vacancy", save)
    parse_into(monkeypatch, pipeline.parsed)
    monkeypatch.setattr(parse_mod, "is_unparsed_vacancy", unparsed)
    return pipeline


async def test_a_provider_that_does_not_answer_at_all_stops_the_post(
    intake, monkeypatch
):
    """Молчащий поставщик отпечатков поста не пропускает, а обрывает приём.

    Пропуск здесь — это потеря: отметка канала уедет дальше, и второй раз
    этот пост не прочтут. Отличить «этот текст не посчитался» от «поставщика
    нет вовсе» можно только здесь, у самого обращения: выше видно один и тот
    же пустой отпечаток.
    """

    async def no_answer(client, model, text):
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr("adapters.lm_embed.embed", no_answer)

    with pytest.raises(embeddings.ProviderIsSilent):
        await ingest.ingest_post(intake, 1, "jobs", post(10, text="Ищем Python"))

    assert intake.saved == []


async def test_a_model_the_provider_does_not_have_stops_the_post_too(
    intake, monkeypatch
):
    """Ненайденная модель отпечатков — тоже беда не про этот текст.

    Поставщик отвечает, но модели у него нет: имя сменили в настройках,
    модель не загрузили. Отказ этот придёт на каждый пост подряд, и пропусти
    его приём — канал уехал бы отметкой до самого свежего поста.
    """

    async def not_found(client, model, text):
        raise httpx.HTTPStatusError(
            "model not found",
            request=httpx.Request("POST", "http://provider.test/v1/embeddings"),
            response=httpx.Response(404),
        )

    monkeypatch.setattr("adapters.lm_embed.embed", not_found)

    with pytest.raises(embeddings.ProviderIsSilent):
        await ingest.ingest_post(intake, 1, "jobs", post(10, text="Ищем Python"))

    assert intake.saved == []


async def test_a_text_the_provider_refuses_is_skipped(intake, monkeypatch):
    """Отказ по самому тексту пост пропускает, а приём не обрывает.

    Такой отказ говорит об этом посте, а не о поставщике: следующий
    посчитается. Встать на нём значило бы остановить канал из-за одного
    объявления.
    """

    async def refuse(client, model, text):
        raise httpx.HTTPStatusError(
            "context length exceeded",
            request=httpx.Request("POST", "http://provider.test/v1/embeddings"),
            response=httpx.Response(400),
        )

    monkeypatch.setattr("adapters.lm_embed.embed", refuse)

    await ingest.ingest_post(intake, 1, "jobs", post(10, text="Ищем Python"))

    assert intake.saved == []


async def test_a_fresh_post_is_saved_and_parsed(intake):
    """Незнакомое объявление сохраняется и уходит в разбор."""
    await ingest.ingest_post(intake, 1, "jobs", post(10, text="Ищем Python-разработчика"))

    assert intake.saved == [(1, 10, "Ищем Python-разработчика")]
    assert intake.parsed == [(7, "Ищем Python-разработчика", "jobs", True)]


async def test_a_hidden_contact_address_reaches_the_row_and_the_parse(intake):
    """Адрес, спрятанный под словом, доезжает и до строки, и до разбора.

    Объявление показывает «контакты в описании», а сам адрес лежит в разметке
    сообщения. Не подобрав его здесь, разбору нечего класть в способ отклика:
    подпись ссылки адресом не является и отбрасывается.
    """
    await ingest.ingest_post(
        intake,
        1,
        "jobs",
        post(
            10,
            text="Ищем Python-разработчика, контакты в описании",
            entities=[link_entity(offset=37, length=8, url="https://acme.test/jobs")],
        ),
    )

    expected = "Ищем Python-разработчика, контакты в описании (https://acme.test/jobs)"
    assert intake.saved == [(1, 10, expected)]
    assert intake.parsed == [(7, expected, "jobs", True)]


async def test_a_linked_article_is_written_into_the_post(intake, monkeypatch):
    """Статья по ссылке дописывается к объявлению до сохранения и до разбора.

    В таких объявлениях пост — одна шапка, а требования, условия и способ
    отклика вынесены в статью: без неё разбирать нечего, а сохранённый текст
    не годится для прогона заново.
    """
    async def fetch_article(_client, url):
        return "Требования: Python"

    monkeypatch.setattr(teletype, "fetch_article", fetch_article)

    await ingest.ingest_post(
        intake, 1, "jobs", post(10, text="Senior QA https://teletype.in/@a/b")
    )

    expected = "Senior QA https://teletype.in/@a/b\n\nТребования: Python"
    assert intake.saved == [(1, 10, expected)]
    assert intake.parsed == [(7, expected, "jobs", True)]


async def test_the_fingerprint_is_taken_from_the_post_alone(intake, monkeypatch):
    """Отпечаток считается по одному тексту поста, без адресов и без статьи.

    Отпечатками отсеивают перепосты, а сравнивают их с теми, что посчитаны
    год назад, — тогда ни адресов, ни статей в тексте не было. Посчитай
    отпечаток по склейке, и перепост давно заведённой вакансии перестал бы с
    ней сходиться, заведясь второй строкой.
    """

    async def fetch_article(_client, _url):
        return "Требования: Python"

    monkeypatch.setattr(teletype, "fetch_article", fetch_article)
    text = "Senior QA, контакты в описании https://teletype.in/@a/b"

    await ingest.ingest_post(
        intake,
        1,
        "jobs",
        post(
            10,
            text=text,
            entities=[link_entity(offset=10, length=8, url="https://acme.test/jobs")],
        ),
    )

    assert intake.embedded == text


@pytest.mark.parametrize(
    "msg",
    [
        pytest.param(post(10, text=""), id="без текста"),
        pytest.param(post(10, text=None), id="текста нет вовсе"),
        pytest.param(
            post(10, text="Ищем Python-разработчика", service=object()),
            id="служебная запись",
        ),
        pytest.param(
            post(10, text="Ищем Python-разработчика", poll=object()), id="опрос"
        ),
    ],
)
async def test_a_post_without_a_vacancy_goes_no_further(intake, msg):
    """Объявление, в котором вакансии быть не может, дальше не идёт.

    Служебные записи о смене названия канала и опросы приходят тем же
    потоком; переводить их в вектор — платить за заведомо пустое.
    """
    await ingest.ingest_post(intake, 1, "jobs", msg)

    assert intake.saved == []
    assert intake.parsed == []


async def test_a_repost_is_skipped(intake):
    """Перепост уже собранной вакансии пропускается.

    Каналы переопубликовывают друг друга постоянно; без этого список
    забился бы одним объявлением в пяти видах.
    """
    intake.similar_id = 3
    intake.unparsed = False

    await ingest.ingest_post(intake, 1, "jobs", post(10, text="Ищем Python-разработчика"))

    assert intake.saved == []
    assert intake.parsed == []


async def test_a_repost_of_a_half_parsed_vacancy_finishes_it(intake):
    """Перепост недоразобранной вакансии её дописывает.

    Иначе она осталась бы полуготовой навсегда: каждый следующий
    перепост объявлял бы её повтором и проходил мимо.
    """
    intake.similar_id = 3
    intake.unparsed = True

    await ingest.ingest_post(intake, 1, "jobs", post(10, text="Ищем Python-разработчика"))

    assert intake.saved == []
    assert intake.parsed == [(3, "Ищем Python-разработчика", "jobs", True)]


async def test_a_post_the_model_could_not_embed_is_skipped(intake, monkeypatch):
    """Объявление, которое не удалось перевести в вектор, пропускается.

    Сравнить его не с чем, а сохранить без вектора значило бы завести
    вакансию, которую поиск повторов больше никогда не увидит.
    """

    async def broken(client, model, text):
        raise RuntimeError("модель вернула не тот размер")

    monkeypatch.setattr("adapters.lm_embed.embed", broken)

    await ingest.ingest_post(intake, 1, "jobs", post(10, text="Ищем Python-разработчика"))

    assert intake.saved == []
    assert intake.parsed == []


async def test_a_vacancy_that_could_not_be_saved_is_not_parsed(intake):
    """Несохранившееся объявление в разбор не уходит.

    Разбирать нечего: строки, в которую записать итог, не появилось.
    """
    intake.new_id = None

    await ingest.ingest_post(intake, 1, "jobs", post(10, text="Ищем Python-разработчика"))

    assert intake.parsed == []


async def test_an_article_that_did_not_load_holds_the_verdict_back(
    intake, monkeypatch
):
    """Не отдавшаяся статья откладывает приговор: разбора у объявления нет.

    Сперва полный текст, потом приговор. В таком посте — одна шапка со
    ссылкой, и разбор по ней сочиняет описание на пустом месте, а оценщик
    судит о том, чего не видел. Строка заводится, чтобы объявление не пропало
    вместе с уехавшим курсором канала, и ждёт дочитывания.
    """
    async def fetch_article(_client, _url):
        raise httpx.ConnectError("сеть отвалилась")

    monkeypatch.setattr(teletype, "fetch_article", fetch_article)

    await ingest.ingest_post(
        intake, 1, "jobs", post(10, text="Senior QA https://teletype.in/@a/b")
    )

    assert intake.saved == [(1, 10, "Senior QA https://teletype.in/@a/b")]
    assert intake.parsed == []


async def test_a_repost_that_lost_its_article_holds_the_verdict_back_too(
    intake, monkeypatch
):
    """Дозабор перепоста без статьи тоже приговора не выносит.

    Дорога другая — строка уже есть и её дописывают, — а причина та же: без
    статьи разбору видна одна шапка со ссылкой. Строка так и остаётся
    недоразобранной и ждёт дочитывания вместе с остальными.
    """
    async def fetch_article(_client, _url):
        raise httpx.ConnectError("сеть отвалилась")

    monkeypatch.setattr(teletype, "fetch_article", fetch_article)
    intake.similar_id = 3
    intake.unparsed = True

    await ingest.ingest_post(
        intake, 1, "jobs", post(10, text="Senior QA https://teletype.in/@a/b")
    )

    assert intake.parsed == []
