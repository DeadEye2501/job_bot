"""Следствия повторного прогона вакансии кнопкой из карточки.

Пользователь жмёт «прогнать заново», когда поправил анкету или увидел, что
разбор ошибся. Поэтому перед разбором заново читаются настройки и заново
забирается исходный пост из канала: объявление могли отредактировать, и
прогонять по кэшу означало бы повторить тот же разбор того же текста.

Недоступный пост прогон не отменяет: разбирается сохранённый текст. А
удаление при повторном прогоне запрещено — пользователь просил перечитать
вакансию, а не выбросить её.
"""

from backend.flows import parse as parse_mod
import pytest
from pyrogram.errors import FloodWait

from backend.models import TelegramChannel, Vacancy
from tests.dbio import only_row, put
from tests.factories import channel_row, vacancy_row
from tests.fakes.telegram import FakeTelegramClient, post


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

    async def parse(pipeline, vacancy_id, text, username, allow_delete=False):
        pipeline.parsed.append((vacancy_id, text, username, allow_delete))

    async def reload():
        pipeline.parsed.append("настройки")

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

    assert await pipeline.rerun_pipeline_for_vacancy(vacancy.id) is True

    assert (await only_row(session_factory, Vacancy)).raw_text == "свежий текст"
    assert pipeline.parsed[-1] == (vacancy.id, "свежий текст", "jobs", False)


async def test_the_settings_are_reloaded_before_the_parse(monkeypatch, rerunning):
    """Настройки перечитываются до разбора.

    Кнопку жмут как раз после правки анкеты или чёрного списка — разбор
    должен идти уже по новым правилам.
    """
    _, vacancy, make_pipeline = rerunning
    pipeline = await _prepare(monkeypatch, make_pipeline, _WithMessages(post=post(42, text="свежий текст")))

    await pipeline.rerun_pipeline_for_vacancy(vacancy.id)

    assert pipeline.parsed[0] == "настройки"


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

    assert await pipeline.rerun_pipeline_for_vacancy(vacancy.id) is True
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

    assert await pipeline.rerun_pipeline_for_vacancy(vacancy.id) is True
    assert client.asked == []
    assert pipeline.parsed[-1] == (vacancy.id, "сохранённый текст", "", False)


async def test_a_vacancy_with_no_text_at_all_cannot_be_rerun(monkeypatch, 
    make_pipeline, session_factory
):
    """Вакансию без текста прогнать нельзя: разбирать нечего."""
    await put(session_factory, vacancy_row(raw_text=""))
    vacancy = await only_row(session_factory, Vacancy)
    pipeline = await _prepare(monkeypatch, make_pipeline, _WithMessages(post=None))

    assert await pipeline.rerun_pipeline_for_vacancy(vacancy.id) is False
    assert pipeline.parsed == []


async def test_a_vanished_vacancy_cannot_be_rerun(monkeypatch, make_pipeline):
    """Прогон исчезнувшей вакансии сообщает о неудаче."""
    pipeline = await _prepare(monkeypatch, make_pipeline, _WithMessages(post=None))

    assert await pipeline.rerun_pipeline_for_vacancy(404) is False
    assert pipeline.parsed == []
