"""Отпечаток вакансии при повторном прогоне и кэш отсева повторов.

Прогон заново — это весь путь заново, и отпечаток тоже: оставшийся от прежнего
текста, он отсеивал бы будущие похожие посты по тому, чего в объявлении уже
нет. Считается он по тому же тексту, с каким идёт разбор, — тем же, чем на
приёме, — иначе прогон уводил бы вакансию из общего счёта, и её же перепост
перестал бы с ней сходиться.

Кэш живёт в памяти и сам из базы не перечитывается, поэтому правится он вслед
за строкой и только вместе с ней.
"""

from adapters import telegraph
from backend.flows import embeddings as embeddings_mod
from backend.flows import parse as parse_mod
from backend.models import Vacancy
from tests.backend.fixtures.rerun import WithMessages, prepare
from tests.dbio import only_row
from tests.fakes.telegram_objects import link_entity, post


async def test_the_fingerprint_is_recomputed_for_the_parsed_text(
    monkeypatch, rerunning, session_factory
):
    """Отпечаток считается заново — по тому тексту, с которым идёт прогон.

    Прогон заново — это весь путь заново. Отпечаток, оставшийся от прежнего
    текста, отсеивал бы будущие похожие посты по тому, чего в объявлении уже
    нет.
    """
    session_factory, vacancy, make_pipeline = rerunning
    pipeline = await prepare(
        monkeypatch, make_pipeline, WithMessages(post=post(42, text="свежий текст"))
    )

    await pipeline.rerun_pipeline_for_vacancy(vacancy.id)

    assert pipeline.embedded == ["свежий текст"]
    assert (await only_row(session_factory, Vacancy)).embedding == [0.5, 0.25]


async def test_the_fingerprint_is_taken_from_the_whole_text(monkeypatch, rerunning):
    """Отпечаток считается по тому же тексту, с которым идёт разбор.

    Тем же, чем он считается на приёме: разойдись эти два текста, прогон
    уводил бы вакансию из общего счёта, и её же перепост перестал бы с ней
    сходиться.
    """
    _, vacancy, make_pipeline = rerunning

    async def fetch_article(_client, _url):
        return "Требования: Python"

    monkeypatch.setattr(telegraph, "fetch_article", fetch_article)
    text = "Senior QA, контакты в описании https://telegra.ph/QA-08-21"
    fresh = post(
        42,
        text=text,
        entities=[link_entity(offset=11, length=8, url="https://acme.test/jobs")],
    )
    pipeline = await prepare(monkeypatch, make_pipeline, WithMessages(post=fresh))

    await pipeline.rerun_pipeline_for_vacancy(vacancy.id)

    assert pipeline.embedded == [
        "Senior QA, контакты (https://acme.test/jobs) в описании"
        " https://telegra.ph/QA-08-21\n\nТребования: Python"
    ]


async def test_a_provider_that_answers_nobody_does_not_cancel_the_rerun(
    monkeypatch, rerunning, session_factory
):
    """Молчащий поставщик отпечатков прогон не отменяет.

    Он отдельный от чат-модели и лежать может порознь с ней, а разбор — то
    главное, ради чего кнопку и жали. Отпечаток в этом случае остаётся
    прежним до следующего прогона.
    """
    session_factory, vacancy, make_pipeline = rerunning
    pipeline = await prepare(
        monkeypatch, make_pipeline, WithMessages(post=post(42, text="свежий текст"))
    )

    async def silent(pipeline, text, what):
        raise embeddings_mod.ProviderIsSilent(what)

    monkeypatch.setattr(embeddings_mod, "embed_text", silent)

    assert await pipeline.rerun_pipeline_for_vacancy(vacancy.id) == "ok"

    assert (await only_row(session_factory, Vacancy)).raw_text == "свежий текст"


async def test_a_vacancy_deleted_while_the_model_answered_stays_out_of_the_cache(
    monkeypatch, rerunning, session_factory
):
    """Вакансию, снесённую посреди прогона, в кэш отсева не возвращают.

    Разбор идёт минутами, и человек успевает выбросить вакансию из окна.
    Кэш живёт в памяти и сам из базы не перечитывается: вернувшийся туда
    вектор отсеивал бы будущие посты как повторы строки, которой уже нет, — и
    объявление не завелось бы вовсе.
    """
    session_factory, vacancy, make_pipeline = rerunning
    pipeline = await prepare(
        monkeypatch, make_pipeline, WithMessages(post=post(42, text="свежий текст"))
    )

    async def parse_and_delete(pipeline, vacancy_id, text, username, allow_delete=False):
        async with session_factory() as session:
            await session.delete(await session.get(Vacancy, vacancy_id))
            await session.commit()
        return True

    monkeypatch.setattr(parse_mod, "parse_and_update_vacancy", parse_and_delete)

    await pipeline.rerun_pipeline_for_vacancy(vacancy.id)

    assert list(pipeline.embeddings.ids) == []


async def test_an_unread_post_is_fingerprinted_by_the_stored_text(
    monkeypatch, rerunning
):
    """Не перечитанный пост считают по сохранённому тексту — тому же, что судят.

    Сохранённый текст для этого и годится: в нём то самое, с чем идёт прогон.
    Пропусти мы отпечаток — и прогон, объявленный «весь путь заново», обошёл бы
    стороной ровно то, чем строку узнают в отсеве повторов.
    """
    _, vacancy, make_pipeline = rerunning
    pipeline = await prepare(monkeypatch, make_pipeline, WithMessages(post=None))

    await pipeline.rerun_pipeline_for_vacancy(vacancy.id)

    assert pipeline.embedded == ["сохранённый текст"]


async def test_a_silent_fingerprint_provider_does_not_cancel_the_rerun(
    monkeypatch, rerunning
):
    """Молчащий поставщик отпечатков прогон не отменяет.

    Он отдельный от чат-модели и лежать может порознь с ней, а разбор — то
    главное, ради чего кнопку и жали.
    """
    _, vacancy, make_pipeline = rerunning
    pipeline = await prepare(monkeypatch, make_pipeline, WithMessages(post=None))
    pipeline.vector = None

    assert await pipeline.rerun_pipeline_for_vacancy(vacancy.id) == "ok"
    assert pipeline.parsed[-1][1] == "сохранённый текст"


async def test_the_new_fingerprint_replaces_the_old_one_in_the_cache(
    monkeypatch, rerunning
):
    """Кэш отсева перепостов получает новый отпечаток вместо прежнего.

    Кэш живёт в памяти и сам из базы не перечитывается: оставь мы в нём старый
    вектор — отсев сравнивал бы будущие посты с текстом, которого в вакансии
    уже нет.
    """
    _, vacancy, make_pipeline = rerunning
    pipeline = await prepare(
        monkeypatch, make_pipeline, WithMessages(post=post(42, text="свежий текст"))
    )
    pipeline.embeddings.append(vacancy.id, [0.9, 0.9])

    await pipeline.rerun_pipeline_for_vacancy(vacancy.id)

    assert list(pipeline.embeddings.ids) == [vacancy.id]
    assert pipeline.embeddings.matrix.tolist() == [[0.5, 0.25]]
