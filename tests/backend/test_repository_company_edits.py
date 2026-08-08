"""Следствия правки полей компании.

Правка различает «не трогать» и «стереть» — у каждого поля своя метка «не
задано». Особняком стоит имя: стереть его нельзя, и попытка отменяет весь
вызов, а не одно поле.
"""

from backend.repository.companies_card import get_company_detail, update_company_fields
from tests.dbio import put
from tests.factories import company_row


async def test_fields_of_a_missing_company_are_not_written(session):
    """Поля несуществующей компании не пишутся, и вызов об этом сообщает."""
    assert await update_company_fields(session, 10_000, name="кто-то") is False


async def test_an_unnamed_field_is_left_untouched(session, session_factory):
    """Не названное в вызове поле остаётся прежним."""
    company = company_row(
        name="Контур", website="https://kontur.ru", notes="заметка", aliases=["K"]
    )
    await put(session_factory, company)

    assert await update_company_fields(session, company.id, notes="новая") is True

    card = await get_company_detail(session, company.id)
    assert card.company.name == "Контур"
    assert card.company.website == "https://kontur.ru"
    assert card.company.aliases == ["K"]
    assert card.company.notes == "новая"


async def test_an_empty_name_is_refused_and_nothing_else_is_written(
    session, session_factory
):
    """Пустое имя правку отменяет целиком, а не стирает имя.

    Имя обязательно и уникально: без него строку не отличить от других.
    Вызов возвращает отказ, и соседние поля из того же вызова тоже не
    записываются.
    """
    company = company_row(name="Контур", notes="было")
    await put(session_factory, company)

    assert await update_company_fields(
        session, company.id, name="   ", notes="стало"
    ) is False

    card = await get_company_detail(session, company.id)
    assert card.company.name == "Контур"
    assert card.company.notes == "было"


async def test_the_website_and_notes_can_be_erased(session, session_factory):
    """Сайт и заметку стереть можно — в отличие от имени."""
    company = company_row(name="Контур", website="https://kontur.ru", notes="заметка")
    await put(session_factory, company)

    await update_company_fields(session, company.id, website=None, notes="  ")

    card = await get_company_detail(session, company.id)
    assert card.company.website is None
    assert card.company.notes is None


async def test_aliases_lose_repeats_blanks_and_wrong_types(session, session_factory):
    """Список написаний чистится: пустые, повторы и не-строки выбрасываются.

    Повтор ищется без учёта регистра, а первое написание сохраняется как
    введено: список показывают пользователю.
    """
    company = company_row(name="Контур", aliases=[])
    await put(session_factory, company)

    await update_company_fields(
        session,
        company.id,
        aliases=["  Kontur  ", "kontur", "", "   ", 42, None, "СКБ Контур"],
    )

    card = await get_company_detail(session, company.id)
    assert card.company.aliases == ["Kontur", "СКБ Контур"]


async def test_aliases_can_be_emptied(session, session_factory):
    """Список написаний можно очистить целиком."""
    company = company_row(name="Контур", aliases=["Kontur"])
    await put(session_factory, company)

    await update_company_fields(session, company.id, aliases=None)

    card = await get_company_detail(session, company.id)
    assert card.company.aliases == []
