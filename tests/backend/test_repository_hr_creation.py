"""Следствия заведения HR вручную с экрана контактов.

Список тут не проверяется на повторы нарочно: экран уже показал пользователю
всех, кого знает, и раз он выбрал «создать нового», значит так и хотел.
"""

from backend.repository.hr_card import get_hr_detail
from backend.repository.hr_identify import create_hr


async def test_a_new_hr_is_stored_with_the_given_fields(session):
    """Заведённый вручную HR сохраняется с тем, что ввели."""
    hr = await create_hr(
        session,
        name="Мария",
        telegram_username="maria",
        telegram_user_id=111,
        notes="звонила в четверг",
    )

    card = await get_hr_detail(session, hr.id)
    assert card.hr.name == "Мария"
    assert card.hr.telegram_username == "maria"
    assert card.hr.telegram_user_id == 111
    assert card.hr.notes == "звонила в четверг"


async def test_empty_strings_are_stored_as_absence_on_creation(session):
    """Пустые строки при заведении записываются как отсутствие.

    Пустая строка и `NULL` для базы разные значения, а для поиска по нику —
    нет: пустой ник совпал бы с другим пустым ником.
    """
    hr = await create_hr(session, name="", telegram_username="", notes="")

    card = await get_hr_detail(session, hr.id)
    assert card.hr.name is None
    assert card.hr.telegram_username is None
    assert card.hr.notes is None
