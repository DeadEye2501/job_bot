"""Следствия повторного прогона вакансии кнопкой из карточки.

Пользователь жмёт «прогнать заново», когда поправил анкету или увидел, что
разбор ошибся. Поэтому перед разбором заново читаются настройки и заново
забирается исходный пост из канала: объявление могли отредактировать, и
прогонять по кэшу означало бы повторить тот же разбор того же текста.

Недоступный пост прогон не отменяет: разбирается сохранённый текст. А
удаление при повторном прогоне запрещено — пользователь просил перечитать
вакансию, а не выбросить её.
"""

from backend.flows import embeddings as embeddings_mod
from adapters import teletype
from backend.flows import parse as parse_mod
import httpx
import pytest
from pyrogram.errors import FloodWait

from backend.models import (
    StatusHistorySource,
    TelegramChannel,
    Vacancy,
    VacancyStatus,
    VacancyStatusHistory,
)
from backend.repository.vacancy_status import (
    apply_parse_outcome,
    mark_vacancy_applied,
)
from tests.dbio import all_rows, only_row, put
from tests.factories import channel_row, vacancy_row
from tests.fakes.telegram import FakeTelegramClient, link_entity, post


class _WithMessages(FakeTelegramClient):
    """Клиент, который умеет отдать отдельное сообщение по номеру."""

    def __init__(self, *, post=None, error=None, **kwargs) -> None:
        super().__init__(**kwargs)
        self._post = post
        self._error = error
        self.asked: list[tuple] = []

    async def get_messages(self, chat_id, message_ids=None):
        self.asked.append((chat_id, message_ids))
        if self._error is not None:
            raise self._error
        return self._post


@pytest.fixture
async def rerunning(make_pipeline, session_factory):
    """Вакансия с сохранённым текстом и каналом-источником."""
    await put(session_factory, channel_row(username="jobs"))
    channel = await only_row(session_factory, TelegramChannel)
    await put(
        session_factory,
        vacancy_row(
            title="старый разбор",
            raw_text="сохранённый текст",
            source_channel_id=channel.id,
            source_msg_id=42,
        ),
    )
    vacancy = await only_row(session_factory, Vacancy)
    return session_factory, vacancy, make_pipeline


async def _prepare(monkeypatch, make_pipeline, client):
    """Конвейер с подставным разбором и без перезагрузки настроек."""
    pipeline = await make_pipeline(client)
    pipeline.parsed = []
    pipeline.parse_done = True

    async def parse(pipeline, vacancy_id, text, username, allow_delete=False):
        pipeline.parsed.append((vacancy_id, text, username, allow_delete))
        return pipeline.parse_done

    async def reload():
        pipeline.parsed.append("настройки")

    async def embed(pipeline, text, what):
        pipeline.embedded.append(text)
        return pipeline.vector

    pipeline.embedded = []
    pipeline.vector = [0.5, 0.25]

    monkeypatch.setattr(embeddings_mod, "embed_text", embed)
    monkeypatch.setattr(parse_mod, "parse_and_update_vacancy", parse)
    pipeline._reload_resources = reload
    return pipeline


async def test_the_fresh_post_is_parsed_and_stored(monkeypatch, rerunning, session_factory):
    """Свежий текст поста сохраняется и разбирается вместо старого.

    Объявление могли отредактировать после сбора; прогонять по кэшу
    означало бы повторить тот же разбор того же текста.
    """
    session_factory, vacancy, make_pipeline = rerunning
    pipeline = await _prepare(monkeypatch, make_pipeline, _WithMessages(post=post(42, text="свежий текст")))

    assert await pipeline.rerun_pipeline_for_vacancy(vacancy.id) == "ok"

    assert (await only_row(session_factory, Vacancy)).raw_text == "свежий текст"
    assert pipeline.parsed[-1] == (vacancy.id, "свежий текст", "jobs", False)


async def test_a_hidden_link_address_is_picked_up_on_a_rerun(monkeypatch, rerunning):
    """Прогон заново подбирает адрес спрятанной ссылки, как и первое чтение.

    Иначе объявление, разобранное до этой правки, так и осталось бы без
    способа отклика: кнопка «Прогнать заново» — единственный способ перечитать
    его целиком, и читать она обязана тем же чтением, что и приём поста.
    """
    session_factory, vacancy, make_pipeline = rerunning
    fresh = post(
        42,
        text="контакты в описании",
        entities=[link_entity(offset=11, length=8, url="https://acme.test/jobs")],
    )
    pipeline = await _prepare(monkeypatch, make_pipeline, _WithMessages(post=fresh))

    assert await pipeline.rerun_pipeline_for_vacancy(vacancy.id) == "ok"

    expected = "контакты в описании (https://acme.test/jobs)"
    assert (await only_row(session_factory, Vacancy)).raw_text == expected
    assert pipeline.parsed[-1] == (vacancy.id, expected, "jobs", False)


async def test_an_unreachable_article_keeps_the_saved_text(monkeypatch, rerunning):
    """Не отдавшаяся статья оставляет сохранённый текст на месте.

    В сохранённом статья уже есть, и переписать его перечитанным постом без
    неё — потерять требования, по которым вакансию и отбирали. Прогон в этом
    случае идёт по тому, что лежит в базе, как и при недоступном посте.
    """
    session_factory, vacancy, make_pipeline = rerunning

    async def fetch_article(_client, _url):
        raise httpx.ConnectError("сеть отвалилась")

    monkeypatch.setattr(teletype, "fetch_article", fetch_article)
    fresh = post(42, text="Senior QA https://teletype.in/@a/b")
    pipeline = await _prepare(monkeypatch, make_pipeline, _WithMessages(post=fresh))

    assert await pipeline.rerun_pipeline_for_vacancy(vacancy.id) == "ok"

    assert (await only_row(session_factory, Vacancy)).raw_text == "сохранённый текст"
    assert pipeline.parsed[-1] == (vacancy.id, "сохранённый текст", "jobs", False)


async def test_the_settings_are_reloaded_before_the_parse(monkeypatch, rerunning):
    """Настройки перечитываются до разбора.

    Кнопку жмут как раз после правки анкеты или чёрного списка — разбор
    должен идти уже по новым правилам.
    """
    _, vacancy, make_pipeline = rerunning
    pipeline = await _prepare(monkeypatch, make_pipeline, _WithMessages(post=post(42, text="свежий текст")))

    await pipeline.rerun_pipeline_for_vacancy(vacancy.id)

    assert pipeline.parsed[0] == "настройки"


async def test_a_rerun_that_could_not_ask_the_model_says_so(
    monkeypatch, rerunning
):
    """Прогон, не сумевший спросить модель, отвечает своим словом.

    Окно показывает по нему «модель не ответила», и человек идёт поднимать
    модель, а не искать пропавшую вакансию. Ответь прогон успехом — он показал
    бы «готово» там, где карточка не менялась вовсе.
    """
    _, vacancy, make_pipeline = rerunning
    pipeline = await _prepare(
        monkeypatch, make_pipeline, _WithMessages(post=post(42, text="свежий текст"))
    )
    pipeline.parse_done = False

    assert await pipeline.rerun_pipeline_for_vacancy(vacancy.id) == "llm"


async def test_deletion_is_forbidden_on_a_rerun(monkeypatch, rerunning):
    """При повторном прогоне вакансию удалять нельзя.

    Пользователь просил перечитать её, а не выбросить: пустой разбор
    здесь оставляет карточку с пометкой «не подходит».
    """
    _, vacancy, make_pipeline = rerunning
    pipeline = await _prepare(monkeypatch, make_pipeline, _WithMessages(post=post(42, text="свежий текст")))

    await pipeline.rerun_pipeline_for_vacancy(vacancy.id)

    assert pipeline.parsed[-1][3] is False


@pytest.mark.parametrize(
    "answer",
    [
        pytest.param({"post": None}, id="поста больше нет"),
        pytest.param({"post": post(42, text="свежий текст", empty=True)}, id="пост пустой"),
        pytest.param({"post": post(42, text=None)}, id="в посте нет текста"),
        pytest.param({"error": FloodWait(value=42)}, id="слишком часто"),
        pytest.param({"error": OSError("сеть")}, id="сеть отвалилась"),
    ],
)
async def test_an_unavailable_post_falls_back_to_the_stored_text(monkeypatch, rerunning, answer):
    """Недоступный пост прогон не отменяет: разбирается сохранённый текст.

    Канал могли закрыть, объявление удалить, а Telegram — попросить
    подождать. Ни один из этих случаев не повод отказать пользователю в
    перечитывании того, что уже собрано.
    """
    _, vacancy, make_pipeline = rerunning
    pipeline = await _prepare(monkeypatch, make_pipeline, _WithMessages(**answer))

    assert await pipeline.rerun_pipeline_for_vacancy(vacancy.id) == "ok"
    assert pipeline.parsed[-1][1] == "сохранённый текст"


async def test_an_unchanged_post_is_not_rewritten(monkeypatch, rerunning, session_factory):
    """Совпавший текст поста заново не записывается: менять нечего."""
    session_factory, vacancy, make_pipeline = rerunning
    pipeline = await _prepare(
        monkeypatch,
        make_pipeline, _WithMessages(post=post(42, text="сохранённый текст"))
    )

    await pipeline.rerun_pipeline_for_vacancy(vacancy.id)

    assert (await only_row(session_factory, Vacancy)).raw_text == "сохранённый текст"


async def test_a_vacancy_without_a_source_is_parsed_from_the_cache(monkeypatch, 
    make_pipeline, session_factory
):
    """Вакансию без канала-источника разбирают по сохранённому тексту.

    Telegram спросить не о чем: ни канала, ни номера сообщения у неё нет.
    """
    await put(session_factory, vacancy_row(raw_text="сохранённый текст"))
    vacancy = await only_row(session_factory, Vacancy)
    client = _WithMessages(post=post(42, text="свежий текст"))
    pipeline = await _prepare(monkeypatch, make_pipeline, client)

    assert await pipeline.rerun_pipeline_for_vacancy(vacancy.id) == "ok"
    assert client.asked == []
    assert pipeline.parsed[-1] == (vacancy.id, "сохранённый текст", "", False)


async def test_a_vacancy_with_no_text_at_all_cannot_be_rerun(monkeypatch, 
    make_pipeline, session_factory
):
    """Вакансию без текста прогнать нельзя: разбирать нечего."""
    await put(session_factory, vacancy_row(raw_text=""))
    vacancy = await only_row(session_factory, Vacancy)
    pipeline = await _prepare(monkeypatch, make_pipeline, _WithMessages(post=None))

    assert await pipeline.rerun_pipeline_for_vacancy(vacancy.id) == "no_text"
    assert pipeline.parsed == []


async def test_a_vanished_vacancy_cannot_be_rerun(monkeypatch, make_pipeline):
    """Прогон исчезнувшей вакансии называет своё: записи нет."""
    pipeline = await _prepare(monkeypatch, make_pipeline, _WithMessages(post=None))

    assert await pipeline.rerun_pipeline_for_vacancy(404) == "missing"
    assert pipeline.parsed == []


async def test_the_fingerprint_is_recomputed_for_the_parsed_text(
    monkeypatch, rerunning, session_factory
):
    """Отпечаток считается заново — по тому тексту, с которым идёт прогон.

    Прогон заново — это весь путь заново. Отпечаток, оставшийся от прежнего
    текста, отсеивал бы будущие похожие посты по тому, чего в объявлении уже
    нет.
    """
    session_factory, vacancy, make_pipeline = rerunning
    pipeline = await _prepare(
        monkeypatch, make_pipeline, _WithMessages(post=post(42, text="свежий текст"))
    )

    await pipeline.rerun_pipeline_for_vacancy(vacancy.id)

    assert pipeline.embedded == ["свежий текст"]
    assert (await only_row(session_factory, Vacancy)).embedding == [0.5, 0.25]


async def test_a_rerun_writes_the_status_it_changed_into_the_history(
    monkeypatch, rerunning, session_factory
):
    """Смена статуса прогоном не остаётся без объяснения.

    Разбор ставит статус прямо, как у только что заведённой строки. Без этой
    записи история обрывалась бы на прежнем статусе, а шапка карточки
    показывала бы новый, и связать их было бы нечем.
    """
    session_factory, vacancy, make_pipeline = rerunning
    pipeline = await _prepare(monkeypatch, make_pipeline, _WithMessages(post=None))

    async def parse(_pipeline, vacancy_id, text, username, allow_delete=False):
        async with session_factory() as session:
            row = await session.get(Vacancy, vacancy_id)
            apply_parse_outcome(row, VacancyStatus.NOT_FIT)
            await session.commit()
        return True

    monkeypatch.setattr(parse_mod, "parse_and_update_vacancy", parse)

    await pipeline.rerun_pipeline_for_vacancy(vacancy.id)

    written = await only_row(session_factory, VacancyStatusHistory)
    assert written.previous_status is VacancyStatus.NEW
    assert written.status is VacancyStatus.NOT_FIT
    assert written.explanation == "Прогон заново."
    assert written.applied is True
    assert written.source is StatusHistorySource.SYSTEM


async def test_a_rerun_that_changed_nothing_writes_no_history(
    monkeypatch, rerunning, session_factory
):
    """Прогон, оставивший статус прежним, истории не трогает: сказать нечего."""
    session_factory, vacancy, make_pipeline = rerunning
    pipeline = await _prepare(monkeypatch, make_pipeline, _WithMessages(post=None))

    await pipeline.rerun_pipeline_for_vacancy(vacancy.id)

    assert await all_rows(session_factory, VacancyStatusHistory) == []


async def test_a_silent_fingerprint_provider_does_not_cancel_the_rerun(
    monkeypatch, rerunning
):
    """Молчащий поставщик отпечатков прогон не отменяет.

    Он отдельный от чат-модели и лежать может порознь с ней, а разбор — то
    главное, ради чего кнопку и жали.
    """
    _, vacancy, make_pipeline = rerunning
    pipeline = await _prepare(monkeypatch, make_pipeline, _WithMessages(post=None))
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
    pipeline = await _prepare(
        monkeypatch, make_pipeline, _WithMessages(post=post(42, text="свежий текст"))
    )
    embeddings_mod.append_embedding(pipeline, vacancy.id, [0.9, 0.9])

    await pipeline.rerun_pipeline_for_vacancy(vacancy.id)

    assert list(pipeline._embedding_ids) == [vacancy.id]
    assert pipeline._embedding_matrix.tolist() == [[0.5, 0.25]]


async def test_a_status_already_explained_gets_no_second_row(
    monkeypatch, rerunning, session_factory
):
    """Переход, уже объяснённый чужой строкой, второй не получает.

    Самоотклик внутри разбора сам переводит вакансию в «отклик отправлен» и
    пишет об этом в историю; вторая строка о том же переходе показала бы его
    в ленте дважды.
    """
    session_factory, vacancy, make_pipeline = rerunning
    pipeline = await _prepare(monkeypatch, make_pipeline, _WithMessages(post=None))

    async def parse(_pipeline, vacancy_id, text, username, allow_delete=False):
        async with session_factory() as session:
            await mark_vacancy_applied(
                session, vacancy_id, "Авто-отправка отклика.", force=False
            )
            await session.commit()
        return True

    monkeypatch.setattr(parse_mod, "parse_and_update_vacancy", parse)

    await pipeline.rerun_pipeline_for_vacancy(vacancy.id)

    written = await only_row(session_factory, VacancyStatusHistory)
    assert written.explanation == "Авто-отправка отклика."
