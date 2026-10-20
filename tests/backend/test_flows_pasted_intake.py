"""Что бот делает с объявлением, вставленным человеком.

Предмет — второй вход в тот же конвейер: текст объявления человек приносит
сам, потому что нашёл его глазами — на бирже, в почте, по наводке. Строка
заводится заведённой человеком: отпечаток, разбор моделью и балл, но без
приговора, и откликателю её отдают только по просьбе. Чем кончилось, окно
узнаёт вестью сразу после разбора, до отклика.

Приём поста проверяется своим слайсом (`test_flows_post_intake`): там предмет
— курсор канала, а общего у двух приёмов отпечаток и дочитывание статей по
ссылке.
"""

from datetime import datetime, timezone

import httpx
import pytest

from backend.flows import parse as parse_mod
from backend.flows import pasted
from backend.flows.hand_outcome import HandResult
from backend.models import Vacancy, VacancyEvent
from tests.backend.fixtures.flows import similar_by_hand
from tests.dbio import all_rows, only_row, put
from tests.factories import vacancy_row
from tests.fakes.telegraph import serve_articles


@pytest.fixture
async def intake(make_pipeline, monkeypatch, one_vector):
    """Конвейер с подставным переводом в вектор и подставным разбором.

    Вести окну и отклики ложатся в один след `order`: по нему видно, что весть
    ушла раньше отклика.
    """
    pipeline = await make_pipeline()
    pipeline.parsed = []
    pipeline.told = []
    pipeline.order = []
    pipeline.parse_done = True
    similar_by_hand(pipeline, monkeypatch)

    async def reload_resources():
        # Отметка ложится в тот же список, что и зовы разбора: по её месту в
        # нём и видно, что слепки перечитаны до разбора, а не после.
        pipeline.parsed.append("слепки")

    monkeypatch.setattr(pipeline, "reload_resources", reload_resources)

    async def parse(pipeline_arg, vacancy_id, text, username, *, allow_delete=True):
        pipeline.parsed.append((vacancy_id, text, username, allow_delete))
        return parse_mod.Judged(pipeline.parse_done)

    monkeypatch.setattr(parse_mod, "parse_and_update_vacancy", parse)

    def told(result: HandResult) -> None:
        pipeline.told.append(result)
        pipeline.order.append("весть")

    async def apply(ids):
        pipeline.applied.append(ids)
        pipeline.order.append("отклик")

    pipeline.on_hand_made = told
    pipeline.apply = apply
    return pipeline


def parse_calls(intake) -> list[tuple]:
    """Зовы разбора без отметок о перечитывании слепков."""
    return [one for one in intake.parsed if isinstance(one, tuple)]


async def _pasted(intake, text, *, posted_at=None, hands_over=False) -> None:
    await pasted.ingest_pasted_text(intake, text, posted_at, hands_over)


async def test_the_pasted_text_becomes_a_row_and_goes_to_the_parser(intake, session_factory):
    """Вставленный текст ложится строкой и уходит на разбор.

    Текст сохраняется целиком: по нему потом судят повторный прогон и подбор
    недоразобранного, и строка без исходника для них всё равно что пустая.
    """
    await _pasted(intake, "Ищем Python-разработчика")

    saved = await only_row(session_factory, Vacancy)
    assert saved.raw_text == "Ищем Python-разработчика"
    assert saved.embedding == [0.1, 0.2]
    assert [(text, username) for _, text, username, _ in parse_calls(intake)] == [
        ("Ищем Python-разработчика", None)
    ]
    assert intake.told == [HandResult("ok", saved.id)]


async def test_a_pasted_text_reads_its_linked_article(intake, session_factory, monkeypatch):
    """Вставленный текст дочитывает статью так же, как пост канала: шапка со
    ссылкой — объявление без требований, и разбирать в нём нечего."""
    serve_articles(monkeypatch)
    text = "Senior QA https://telegra.ph/QA-08-21"

    await _pasted(intake, text)

    expected = f"{text}\n\nТребования: Python"
    assert (await only_row(session_factory, Vacancy)).raw_text == expected
    assert [got for _, got, _, _ in parse_calls(intake)] == [expected]


async def test_a_pasted_text_whose_article_did_not_come_is_not_filed(
    intake, session_factory, monkeypatch
):
    """Статья не скачалась — строки нет: приём поста ждёт статью у заведённой
    строки, а человек может просто нажать ещё раз."""
    serve_articles(monkeypatch, httpx.ConnectError("сайт лежит"))

    await _pasted(intake, "Senior QA https://telegra.ph/QA-08-21")

    assert intake.told == [HandResult("article")]
    assert (await all_rows(session_factory, Vacancy), parse_calls(intake)) == ([], [])


async def test_the_new_vector_joins_the_cache(intake, session_factory):
    """Отпечаток заведённой строки встаёт в кэш отсева сразу: то же объявление,
    пришедшее следом из канала, иначе завелось бы второй строкой."""
    await _pasted(intake, "Ищем Python-разработчика")

    saved = await only_row(session_factory, Vacancy)
    assert intake.embeddings.ids.tolist() == [saved.id]


async def test_the_timeline_says_the_vacancy_came_from_a_human(intake, session_factory):
    """Лента говорит, что вакансию принёс человек, а не обход каналов — и по
    этой же отметке разбор не выносит ей приговора."""
    await _pasted(intake, "Ищем повара")

    event = await only_row(session_factory, VacancyEvent)
    assert event.kind == "created_by_hand"


async def test_a_pasted_vacancy_has_no_channel_behind_it(intake, session_factory):
    """У вставленной вакансии источника нет, и притворяться им нечему.

    Колонки канала и поста держат связь со своим каналом: положи туда чужое
    или выдуманное, и статистика канала посчитает эту строку своей.
    """
    await _pasted(intake, "Ищем флориста")

    saved = await only_row(session_factory, Vacancy)
    assert (saved.source_channel_id, saved.source_msg_id) == (None, None)
    # Дату тоже не выдумывают: проставленное «сегодня» подняло бы всякую
    # вставленную вакансию наверх в отборе за последние дни.
    assert saved.posted_at is None


async def test_the_named_publication_date_lands_in_the_row(intake, session_factory):
    when = datetime(2026, 8, 20, tzinfo=timezone.utc)

    await _pasted(intake, "Ищем сварщика", posted_at=when)

    assert (await only_row(session_factory, Vacancy)).posted_at.date() == when.date()


async def test_a_text_like_a_known_vacancy_is_filed_as_its_own_row(intake, session_factory):
    """Похожесть по отпечатку однозначного повтора не даёт: заведённое
    человеком заводится своей строкой, а не отказом."""
    known = vacancy_row(raw_text="Ищем Python-разработчика")
    await put(session_factory, known)
    intake.similar_id = known.id

    await _pasted(intake, "Ищем Python-разработчика")

    rows = await all_rows(session_factory, Vacancy)
    (own,) = [row for row in rows if row.id != known.id]
    assert intake.told == [HandResult("ok", own.id)]


async def test_a_text_like_an_unfinished_row_does_not_touch_that_row(intake, session_factory):
    """С чужой брошенной строкой вставленный текст не сливается: её доберёт
    подбор недоразобранного, а человек получает свою."""
    brought_earlier = vacancy_row(raw_text="Ищем повара", is_parsed=False)
    await put(session_factory, brought_earlier)
    intake.similar_id = brought_earlier.id
    intake.unparsed = True

    await _pasted(intake, "Ищем повара")

    assert brought_earlier.id not in [row_id for row_id, _, _, _ in parse_calls(intake)]
    assert len(await all_rows(session_factory, Vacancy)) == 2


async def test_a_silent_provider_is_told_apart_from_a_text_that_did_not_count(
    intake, session_factory, silent_embedder
):
    """Молчащий поставщик отпечатков не роняет заведение, а отвечает бедой."""
    await _pasted(intake, "Ищем сварщика")

    assert intake.told == [HandResult("embed")]
    assert await all_rows(session_factory, Vacancy) == []


async def test_a_text_without_an_embedding_leaves_no_half_made_row(
    intake, session_factory, monkeypatch
):
    """Без отпечатка строка не заводится вовсе: она молча вышла бы из отсева
    перепостов."""

    async def no_answer(client, model, text):
        return None

    monkeypatch.setattr("adapters.lm_embed.embed", no_answer)

    await _pasted(intake, "Ищем Python-разработчика")

    assert intake.told == [HandResult("embed")]
    assert await all_rows(session_factory, Vacancy) == []


async def test_the_bottom_bar_names_the_parse(intake):
    """Имя хода окно ловит по строке: опечатайся оно, человек увидел бы внизу
    пустую полосу без слова о том, что идёт."""
    steps = []
    intake.on_progress = lambda *step: steps.append(step)

    await _pasted(intake, "Ищем повара")

    assert steps[0] == ("pasted", "Разбор объявления", 0, 0)


async def test_the_profile_and_the_blacklist_are_reloaded_before_the_parse(intake):
    """Слепки наполняет только перечитывание, а зовёт его обход каналов: разбери
    по пустым — и балл выйдет нулевым."""
    await _pasted(intake, "Ищем Python-разработчика")

    assert intake.parsed[0] == "слепки"


async def test_a_parse_that_did_not_happen_is_not_called_a_success(intake):
    """Не дошедший разбор удачей не зовут: строка неразобранная, и в списке её нет."""
    intake.parse_done = False

    await _pasted(intake, "Ищем повара")

    assert [one.outcome for one in intake.told] == ["llm"]


async def test_without_the_switch_the_vacancy_is_only_filed(intake):
    """Переключатель выключен — заводится в New, и больше ничего."""
    await _pasted(intake, "Ищем повара", hands_over=False)

    assert intake.applied == []


async def test_with_the_switch_the_window_hears_before_the_applier_starts(intake, session_factory):
    """Переключатель включён — откликатель по режиму отклика; весть «заведено»
    уходит до отклика: окно ждёт New, а не конца отклика."""
    await _pasted(intake, "Ищем повара", hands_over=True)

    saved = await only_row(session_factory, Vacancy)
    assert intake.applied == [[saved.id]]
    assert intake.order == ["весть", "отклик"]
