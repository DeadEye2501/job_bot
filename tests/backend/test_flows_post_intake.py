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

from backend.flows import parse as parse_mod
import pytest

from backend.flows import ingest
from tests.fakes.telegram import post


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

    async def save(pipeline, channel_id, username, msg, text, embedding):
        pipeline.saved.append((channel_id, msg.id, text))
        return pipeline.new_id

    async def parse(pipeline, vacancy_id, text, username):
        pipeline.parsed.append((vacancy_id, text))

    async def unparsed(pipeline, vacancy_id):
        return pipeline.unparsed

    monkeypatch.setattr("adapters.lm_studio.embed", embed)
    monkeypatch.setattr(
        "backend.flows.ingest.cosine_top_match",
        lambda vec, ids, matrix, threshold: pipeline.similar_id,
    )
    monkeypatch.setattr(ingest, "save_new_vacancy", save)
    monkeypatch.setattr(parse_mod, "parse_and_update_vacancy", parse)
    monkeypatch.setattr(parse_mod, "is_unparsed_vacancy", unparsed)
    return pipeline


async def test_a_fresh_post_is_saved_and_parsed(intake):
    """Незнакомое объявление сохраняется и уходит в разбор."""
    await ingest.ingest_post(intake, 1, "jobs", post(10, text="Ищем Python-разработчика"))

    assert intake.saved == [(1, 10, "Ищем Python-разработчика")]
    assert intake.parsed == [(7, "Ищем Python-разработчика")]


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
    assert intake.parsed == [(3, "Ищем Python-разработчика")]


async def test_a_post_the_model_could_not_embed_is_skipped(intake, monkeypatch):
    """Объявление, которое не удалось перевести в вектор, пропускается.

    Сравнить его не с чем, а сохранить без вектора значило бы завести
    вакансию, которую поиск повторов больше никогда не увидит.
    """

    async def broken(client, model, text):
        raise RuntimeError("модель вернула не тот размер")

    monkeypatch.setattr("adapters.lm_studio.embed", broken)

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
