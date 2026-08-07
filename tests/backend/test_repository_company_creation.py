"""Следствия заведения компании вручную.

Имя обязательно и уникально на уровне базы — это единственный признак, по
которому компанию отличают от других. Остальное необязательно.
"""

import pytest

from backend.repository import create_company, get_company_detail


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
