"""Что бот делает с объявлением, вставленным человеком.

Предмет — второй вход в тот же конвейер: текст объявления человек приносит
сам, потому что нашёл его глазами — на бирже, в почте, по наводке. Дальше
строка идёт обычной дорогой поста канала: отпечаток, отсев перепостов, разбор
моделью, балл и приговор. Отличие одно — источника нет, и всё, что о нём
знали, приходится не знать.

Приём поста проверяется своим слайсом (`test_flows_post_intake`): там предмет
— курсор канала и дочитывание статьи по ссылке, и общего у двух приёмов только
отпечаток.
"""

from datetime import datetime, timezone

import httpx
import pytest

from backend.flows import cleanup
from backend.flows import parse as parse_mod
from backend.flows import pasted
from backend.models import Vacancy, VacancyEvent
from tests.dbio import all_rows, only_row, put
from tests.factories import vacancy_row


@pytest.fixture
async def intake(make_pipeline, monkeypatch):
    """Конвейер с подставным переводом в вектор и подставным разбором."""
    pipeline = await make_pipeline()
    pipeline.parsed = []
    pipeline.similar_id = None

    async def embed(client, model, text):
        pipeline.embedded = text
        return [0.1, 0.2]

    pipeline.reloaded = 0
    pipeline.parse_done = True
    pipeline.unparsed = False
    pipeline.parse_drops = False

    async def unparsed(pipeline_arg, vacancy_id):
        return pipeline.unparsed

    async def reload_resources():
        pipeline.reloaded += 1
        # Отметка ложится в тот же список, что и зовы разбора: по её месту в
        # нём и видно, что слепки перечитаны до разбора, а не после.
        pipeline.parsed.append("слепки")

    monkeypatch.setattr(pipeline, "reload_resources", reload_resources)
    monkeypatch.setattr("adapters.lm_embed.embed", embed)
    monkeypatch.setattr(
        pipeline.embeddings,
        "match",
        lambda vector, threshold: pipeline.similar_id,
    )
    async def parse(pipeline_arg, vacancy_id, text, username, *, allow_delete=True):
        pipeline.parsed.append((vacancy_id, text, username, allow_delete))
        if pipeline.parse_drops:
            # Тем же, чем сносит непригодное настоящий разбор: строки не
            # стало, событий её тоже, а ответ — «дошло».
            await cleanup.delete_vacancy_as_trash(
                pipeline, vacancy_id, reason="реклама"
            )
        return pipeline.parse_done

    monkeypatch.setattr(parse_mod, "parse_and_update_vacancy", parse)
    monkeypatch.setattr(parse_mod, "is_unparsed_vacancy", unparsed)
    return pipeline


def parse_calls(intake) -> list[tuple]:
    """Зовы разбора без отметок о перечитывании слепков.

    В один список ложатся оба: по их порядку и видно, что слепки перечитаны
    до разбора, — а проверкам про сам разбор отметка мешает.
    """
    return [one for one in intake.parsed if isinstance(one, tuple)]


async def test_the_pasted_text_becomes_a_row_and_goes_to_the_parser(
    intake, session_factory
):
    """Вставленный текст ложится строкой и уходит на разбор.

    Текст сохраняется целиком: по нему потом судят повторный прогон и подбор
    недоразобранного, и строка без исходника для них всё равно что пустая.
    """
    assert await pasted.ingest_pasted_text(intake, "Ищем Python-разработчика", None) == "ok"

    saved = await only_row(session_factory, Vacancy)
    assert saved.raw_text == "Ищем Python-разработчика"
    assert saved.embedding == [0.1, 0.2]
    assert [(text, username) for _, text, username, _ in parse_calls(intake)] == [
        ("Ищем Python-разработчика", None)
    ]


async def test_the_new_vector_joins_the_cache(intake, session_factory):
    """Отпечаток заведённой строки встаёт в кэш отсева сразу.

    Кэш и есть то, чем отсекают перепосты. Не встань вектор в него, тот же
    текст, вставленный второй раз или пришедший следом из канала, завёл бы
    вторую строку — и список забился бы одним объявлением в двух видах.
    """
    await pasted.ingest_pasted_text(intake, "Ищем Python-разработчика", None)

    saved = await only_row(session_factory, Vacancy)
    assert intake.embeddings.ids.tolist() == [saved.id]


async def test_a_post_the_parser_threw_out_is_not_called_a_success(
    intake, session_factory
):
    """Снесённое разбором удачей не зовут.

    Разбор отвечает «дошло» и тогда, когда сам же снёс строку: пост оказался
    резюме, рекламой или пустышкой. Скажи человеку «объявление заведено» —
    он пойдёт искать в списке то, чего там нет и не будет.
    """
    intake.parse_drops = True

    assert await pasted.ingest_pasted_text(intake, "Реклама курсов", None) == "trash"

    assert await all_rows(session_factory, Vacancy) == []


async def test_the_timeline_says_the_vacancy_came_from_a_human(intake, session_factory):
    """Лента говорит, что вакансию принёс человек, а не обход каналов.

    Лента объясняет, откуда строка взялась, и у вставленной источника нет
    вовсе: пустая, она читалась бы как потерянный след обхода.
    """
    await pasted.ingest_pasted_text(intake, "Ищем повара", None)

    event = await only_row(session_factory, VacancyEvent)
    assert event.kind == "created_by_hand"


async def test_a_pasted_vacancy_has_no_channel_behind_it(intake, session_factory):
    """У вставленной вакансии источника нет, и притворяться им нечему.

    Колонки канала и поста держат связь со своим каналом: положи туда чужое
    или выдуманное, и статистика канала посчитает эту строку своей, а отбор по
    источнику покажет её среди пришедших из Telegram.
    """
    await pasted.ingest_pasted_text(intake, "Ищем флориста", None)

    saved = await only_row(session_factory, Vacancy)
    assert saved.source_channel_id is None
    assert saved.source_msg_id is None
    # Дату тоже не выдумывают: проставленное «сегодня» подняло бы всякую
    # вставленную вакансию наверх в отборе за последние дни.
    assert saved.posted_at is None


async def test_the_named_publication_date_lands_in_the_row(intake, session_factory):
    """Названная дата публикации ложится в строку, а неназванная не выдумывается.

    По дате идёт отбор «за последние дни» и сортировка списка: выдуманная
    подняла бы старое объявление наверх, а пустая честно оставит его без
    места в этой выдаче.
    """
    when = datetime(2026, 8, 20, tzinfo=timezone.utc)
    await pasted.ingest_pasted_text(intake, "Ищем сварщика", when)

    saved = await only_row(session_factory, Vacancy)
    assert saved.posted_at.date() == when.date()


async def test_a_text_that_repeats_a_known_vacancy_does_not_start_a_second_row(
    intake, session_factory
):
    """Объявление, уже заведённое, вторую строку не заводит.

    То же правило, что и у перепоста в канале: одно объявление — одна строка,
    иначе список забивается одним и тем же в нескольких видах. Человеку об
    этом говорят словом, а не молчанием: он вставил текст и вправе знать, что
    строки не прибавилось.
    """
    intake.similar_id = 42

    assert await pasted.ingest_pasted_text(intake, "Ищем Python-разработчика", None) == "duplicate"

    assert await all_rows(session_factory, Vacancy) == []
    assert parse_calls(intake) == []


async def test_a_text_matching_an_unfinished_row_finishes_it_instead_of_refusing(
    intake, session_factory
):
    """Похожая, но недоразобранная строка дорзабирается вставленным текстом.

    Так делает и приём поста канала: иначе брошенная на полпути вакансия
    пропускалась бы вечно. Ответь мы «уже заведено», человек пошёл бы искать
    её в списке — а там показывают только разобранные, и он не нашёл бы
    ничего.
    """
    brought_earlier = vacancy_row(raw_text="Ищем повара", is_parsed=False)
    await put(session_factory, brought_earlier)
    intake.similar_id = brought_earlier.id
    intake.unparsed = True

    assert await pasted.ingest_pasted_text(intake, "Ищем повара", None) == "ok"

    assert [row_id for row_id, _, _, _ in parse_calls(intake)] == [brought_earlier.id]
    # Второй строки не завелось: дорзабрали ту, что уже была.
    assert len(await all_rows(session_factory, Vacancy)) == 1


async def test_a_silent_provider_is_told_apart_from_a_text_that_did_not_count(
    intake, session_factory, monkeypatch
):
    """Молчащий поставщик отпечатков не роняет заведение, а отвечает бедой.

    Отличать его от несчитанного текста надо здесь, у самого обращения: выше
    видно один и тот же пустой отпечаток. Пропусти бросок — и человек вместо
    «Модель отпечатков не ответила» прочтёт общее «не удалось завести».
    """

    async def silent(client, model, text):
        raise httpx.ConnectError("поставщик не поднят")

    monkeypatch.setattr("adapters.lm_embed.embed", silent)

    assert await pasted.ingest_pasted_text(intake, "Ищем сварщика", None) == "embed"

    assert await all_rows(session_factory, Vacancy) == []


async def test_a_text_without_an_embedding_leaves_no_half_made_row(
    intake, session_factory, monkeypatch
):
    """Без отпечатка строка не заводится вовсе.

    Отпечаток — то, чем эту вакансию потом узнают среди перепостов. Строка без
    него молча вышла бы из отсева, и то же объявление, пришедшее из канала,
    завелось бы второй раз. Человеку отвечают бедой, а не тишиной: он ждёт
    ответа на своё нажатие.
    """

    async def no_answer(client, model, text):
        return None

    monkeypatch.setattr("adapters.lm_embed.embed", no_answer)

    assert await pasted.ingest_pasted_text(intake, "Ищем Python-разработчика", None) == "embed"

    assert await all_rows(session_factory, Vacancy) == []


async def test_the_parser_may_drop_a_pasted_post_it_finds_unfit(intake):
    """Разбору дано право убрать непригодное — то же, что и на приёме поста.

    Судьбу мусора решает он сам, а вставленный текст ничем не надёжнее
    опубликованного: оставленный след от рекламы засорял бы список.
    """
    await pasted.ingest_pasted_text(intake, "Реклама курсов", None)

    assert [allow_delete for _, _, _, allow_delete in parse_calls(intake)] == [True]


async def test_the_profile_and_the_blacklist_are_reloaded_before_the_parse(intake):
    """Перед разбором конвейер перечитывает анкету, навыки и чёрный список.

    Слепки эти наполняет только перечитывание, а зовёт его обход каналов — то
    есть в режимах «Выключен» и «Только диалоги» они пусты. Разбери по пустым:
    балл выйдет нулевым, чёрный список не сработает вовсе, а приговор о
    пригодности вынесут по анкете, в которой ничего нет. Человек увидит
    «Не подходит» на любой вакансии и причины не узнает.
    """
    await pasted.ingest_pasted_text(intake, "Ищем Python-разработчика", None)

    assert intake.parsed[0] == "слепки"


async def test_a_parse_that_did_not_happen_is_not_called_a_success(intake):
    """Не дошедший разбор удачей не зовут.

    Модель молчит — строка остаётся неразобранной, и в списке её нет:
    человеку показывают только разобранные. Скажи ему «Объявление заведено»,
    и он пойдёт искать в списке то, чего там не появится.
    """
    intake.parse_done = False

    assert await pasted.ingest_pasted_text(intake, "Ищем повара", None) == "llm"
