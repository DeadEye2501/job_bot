"""Следствия слияния двух записей об одной компании.

Одна компания заводится дважды легко: объявления называют её по-разному, и
если автоматическое сопоставление не сработало, в базе оказываются «Контур» и
«СКБ Контур». Слияние необратимо, поэтому имя поглощённой не пропадает, а
уходит в написания оставшейся: по нему её найдут в следующий раз.
"""

import pytest
from sqlalchemy import select

from backend.models import Company, Vacancy
from backend.repository.companies_card import merge_company
from tests.dbio import put
from tests.factories import company_row, vacancy_row


async def test_merging_a_record_into_itself_is_refused(session, session_factory):
    """Слить запись саму с собой нельзя: это стёрло бы её без остатка."""
    company = company_row()
    await put(session_factory, company)

    with pytest.raises(ValueError, match="absorbed_id == survivor_id"):
        await merge_company(session, absorbed_id=company.id, survivor_id=company.id)


async def test_merging_with_a_missing_record_is_refused(session, session_factory):
    """Слияние с несуществующей записью не проходит молча."""
    company = company_row()
    await put(session_factory, company)

    with pytest.raises(ValueError, match="not found"):
        await merge_company(session, absorbed_id=company.id, survivor_id=10_000)


async def test_vacancies_of_both_records_end_up_on_the_survivor(
    session, session_factory
):
    """Вакансии обеих записей достаются оставшейся, а поглощённая исчезает."""
    absorbed = company_row(name="Контур")
    survivor = company_row(name="СКБ Контур")
    await put(session_factory, absorbed, survivor)
    await put(
        session_factory,
        vacancy_row(title="от дубля", company_id=absorbed.id),
        vacancy_row(title="от основной", company_id=survivor.id),
    )

    await merge_company(session, absorbed_id=absorbed.id, survivor_id=survivor.id)

    rows = (await session.scalars(select(Vacancy))).all()
    assert {v.title: v.company_id for v in rows} == {
        "от дубля": survivor.id,
        "от основной": survivor.id,
    }
    assert [c.name for c in (await session.scalars(select(Company))).all()] == [
        "СКБ Контур"
    ]


async def test_the_absorbed_name_and_aliases_move_into_the_survivors_aliases(
    session, session_factory
):
    """Имя и написания поглощённой уходят в написания оставшейся.

    Именно ими объявления и называли компанию: выбросив их, мы завели бы тот
    же дубль в следующий раз.
    """
    absorbed = company_row(name="Контур", aliases=["Kontur"])
    survivor = company_row(name="СКБ Контур", aliases=["SKB"])
    await put(session_factory, absorbed, survivor)

    await merge_company(session, absorbed_id=absorbed.id, survivor_id=survivor.id)

    kept = await session.get(Company, survivor.id)
    assert kept.aliases == ["SKB", "Kontur", "Контур"]


async def test_a_spelling_already_known_is_not_added_twice(session, session_factory):
    """Уже известное написание вторым разом не добавляется.

    Совпадение ищется без учёта регистра: «Kontur» и «kontur» — одно и то же
    написание, и держать оба незачем.
    """
    absorbed = company_row(name="kontur", aliases=["SKB"])
    survivor = company_row(name="СКБ Контур", aliases=["Kontur", "skb"])
    await put(session_factory, absorbed, survivor)

    await merge_company(session, absorbed_id=absorbed.id, survivor_id=survivor.id)

    kept = await session.get(Company, survivor.id)
    assert kept.aliases == ["Kontur", "skb"]


async def test_a_spelling_equal_to_the_survivors_own_name_is_still_added(
    session, session_factory
):
    """Написание, совпадающее с именем оставшейся, всё равно попадает в список.

    Совпадение ищут только среди уже записанных написаний, а собственное имя
    в этот набор не входит. В списке заводится написание, слово в слово
    повторяющее имя рядом, — на экране это видно как пустая строка-дубль.
    Тест закрепляет сегодняшнее поведение: при починке он покраснеет.
    """
    absorbed = company_row(name="СКБ КОНТУР", aliases=[])
    survivor = company_row(name="СКБ Контур", aliases=[])
    await put(session_factory, absorbed, survivor)

    await merge_company(session, absorbed_id=absorbed.id, survivor_id=survivor.id)

    kept = await session.get(Company, survivor.id)
    assert kept.aliases == ["СКБ КОНТУР"]


async def test_a_website_is_taken_only_when_the_survivor_has_none(
    session, session_factory
):
    """Сайт забирается у поглощённой, только если у оставшейся его нет."""
    absorbed = company_row(name="Контур", website="https://kontur.ru")
    empty = company_row(name="СКБ Контур", website=None)
    await put(session_factory, absorbed, empty)

    await merge_company(session, absorbed_id=absorbed.id, survivor_id=empty.id)

    assert (await session.get(Company, empty.id)).website == "https://kontur.ru"


async def test_an_existing_website_is_not_overwritten(session, session_factory):
    """Сайт оставшейся чужим не затирается."""
    absorbed = company_row(name="Контур", website="https://kontur.ru")
    survivor = company_row(name="СКБ Контур", website="https://kontur.dev")
    await put(session_factory, absorbed, survivor)

    await merge_company(session, absorbed_id=absorbed.id, survivor_id=survivor.id)

    assert (await session.get(Company, survivor.id)).website == "https://kontur.dev"


async def test_notes_of_both_records_are_kept(session, session_factory):
    """Заметки обеих записей склеиваются: слияние необратимо, и терять нечего."""
    absorbed = company_row(name="Контур", notes="писали в марте")
    survivor = company_row(name="СКБ Контур", notes="долго отвечают")
    await put(session_factory, absorbed, survivor)

    await merge_company(session, absorbed_id=absorbed.id, survivor_id=survivor.id)

    assert (await session.get(Company, survivor.id)).notes == (
        "долго отвечают\n---\nписали в марте"
    )
