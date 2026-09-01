"""Следствия заведения компании вручную.

Имя обязательно и уникально на уровне базы — это единственный признак, по
которому компанию отличают от других. Остальное необязательно.
"""

import pytest

from backend.repository.companies_card import create_company, get_company_detail


async def test_a_new_company_is_stored_with_the_given_fields(session):
    """Заведённая компания сохраняется с тем, что ввели."""
    company = await create_company(
        session,
        name="  Ромашка  ",
        website="https://kontur.ru",
        aliases=["Kontur"],
        notes="через знакомых",
    )

    card = await get_company_detail(session, company.id)
    assert card.company.name == "Ромашка"
    assert card.company.website == "https://kontur.ru"
    assert card.company.aliases == ["Kontur"]
    assert card.company.notes == "через знакомых"


async def test_the_spellings_of_a_new_company_lose_their_repeats(session):
    """Повторы среди написаний не ложатся в колонку и при заведении.

    Правило у написаний компании одно на всех, кто пишет колонку: правку
    карточки, слияние, разбор вакансии и заведение. Разделители при этом не
    схлопываются — «Сбер-Тех» и «Сбер Тех» разные, — а вот регистр не
    считается: список человек набирает руками, и «Контур» с «контур» в нём
    одно и то же.
    """
    company = await create_company(
        session, name="Ромашка", aliases=["Контур", "контур", "Kontur"]
    )

    assert company.aliases == ["Контур", "Kontur"]


async def test_a_company_without_a_name_is_refused(session):
    """Компанию без имени завести нельзя: имя — её единственный признак."""
    with pytest.raises(ValueError, match="name is required"):
        await create_company(session, name="   ")


async def test_a_new_company_without_extras_gets_absence_not_emptiness(session):
    """Незаполненные поля новой компании остаются пустыми, а список — пустым списком."""
    company = await create_company(session, name="Ромашка")

    card = await get_company_detail(session, company.id)
    assert card.company.website is None
    assert card.company.notes is None
    assert card.company.aliases == []


async def test_a_new_company_gets_its_name_with_a_capital_letter(session):
    """Название компании ложится в базу с заглавной буквы."""
    company = await create_company(session, name="  ромашка  ")

    card = await get_company_detail(session, company.id)
    assert card.company.name == "Ромашка"


async def test_a_brand_spelling_of_a_new_company_survives(session):
    """Написание бренда переживает заведение.

    Вторая буква заглавная при маленькой первой — так бренд пишет себя сам, и
    поднятая первая буква сделала бы из него другое имя.
    """
    company = await create_company(session, name="eBay")

    card = await get_company_detail(session, company.id)
    assert card.company.name == "eBay"
