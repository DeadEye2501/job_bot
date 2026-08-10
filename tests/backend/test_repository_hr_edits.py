"""Следствия правки полей HR.

Правка устроена вокруг различия «не трогать» и «стереть»: экран шлёт только
те поля, которые пользователь менял, и отсутствие поля не должно означать
пустое значение. Поэтому у каждого поля своя метка «не задано», отличная
от `None`.
"""

import pytest

from backend.repository.hr_card import get_hr_detail, update_hr_fields
from tests.dbio import put
from tests.factories import hr_row


async def test_fields_of_a_missing_hr_are_not_written(session, session_factory):
    """Поля несуществующего HR не пишутся, и вызов об этом сообщает."""
    assert await update_hr_fields(session, 10_000, name="кто-то") is False


async def test_an_unnamed_field_is_left_untouched(session, session_factory):
    """Не названное в вызове поле остаётся прежним.

    Это и есть предмет метки «не задано»: экран шлёт только изменённое, и
    отсутствие поля обязано значить «не трогай», а не «сотри».
    """
    hr = hr_row(name="Мария", telegram_username="maria", notes="заметка")
    await put(session_factory, hr)

    assert await update_hr_fields(session, hr.id, name="Ольга") is True

    card = await get_hr_detail(session, hr.id)
    assert card.hr.name == "Ольга"
    assert card.hr.telegram_username == "maria"
    assert card.hr.notes == "заметка"


async def test_a_field_set_to_nothing_is_erased(session, session_factory):
    """Явно переданное «ничего» стирает любое из трёх полей.

    Ник проверяется здесь же, а не только через строку с собачкой: у него
    своя ветка стирания, и без этой проверки её можно было бы выбросить
    целиком.
    """
    hr = hr_row(name="Мария", telegram_username="maria", notes="заметка")
    await put(session_factory, hr)

    await update_hr_fields(
        session, hr.id, name=None, telegram_username=None, notes=None
    )

    card = await get_hr_detail(session, hr.id)
    assert card.hr.name is None
    assert card.hr.notes is None
    assert card.hr.telegram_username is None


async def test_a_field_of_only_whitespace_is_erased_too(session, session_factory):
    """Поле из одних пробелов стирается так же, как явно пустое."""
    hr = hr_row(name="Мария", notes="заметка")
    await put(session_factory, hr)

    await update_hr_fields(session, hr.id, name="   ", notes="  \n ")

    card = await get_hr_detail(session, hr.id)
    assert card.hr.name is None
    assert card.hr.notes is None


async def test_surrounding_whitespace_is_trimmed_from_a_real_value(
    session, session_factory
):
    """У непустого значения пробелы по краям срезаются.

    Новое имя нарочно отличается от того, что построитель ставит по
    умолчанию: совпади они — и проверка прошла бы даже при записи, которая
    вообще ничего не делает.
    """
    hr = hr_row(name="Мария", notes=None)
    await put(session_factory, hr)

    await update_hr_fields(session, hr.id, name="  Ольга  ", notes="  заметка  ")

    card = await get_hr_detail(session, hr.id)
    assert card.hr.name == "Ольга"
    assert card.hr.notes == "заметка"


async def test_a_username_typed_with_an_at_sign_is_stored_without_it(
    session, session_factory
):
    """Ник, введённый с собачкой, сохраняется без неё.

    Telegram отдаёт ник голым, и запись с собачкой не совпала бы с тем, что
    приходит во входящем сообщении, — HR перестал бы опознаваться.
    """
    hr = hr_row(telegram_username=None)
    await put(session_factory, hr)

    await update_hr_fields(session, hr.id, telegram_username="  @maria  ")

    card = await get_hr_detail(session, hr.id)
    assert card.hr.telegram_username == "maria"


async def test_a_pasted_link_is_saved_as_the_bare_handle(session, session_factory):
    """Вставленная в правку ссылка сохраняется голым ником.

    Ник копируют ссылкой из шапки чата, и правка карточки — тот же ввод,
    что и заведение. Легла бы ссылка как есть — отправка пошла бы искать
    собеседника с именем «t.me/maria_hr» и не нашла никого.
    """
    hr = hr_row(telegram_username=None)
    await put(session_factory, hr)

    await update_hr_fields(session, hr.id, telegram_username="https://t.me/maria_hr")

    card = await get_hr_detail(session, hr.id)
    assert card.hr.telegram_username == "maria_hr"


async def test_a_username_that_is_not_a_handle_is_refused(session, session_factory):
    """Не телеграмовское в правке отвергается, а прежний ник остаётся цел.

    Молча записанное имя человека или номер телефона обнаружились бы
    только в тот миг, когда отправка перестала находить собеседника, — и
    прежний рабочий ник к тому времени был бы уже затёрт.
    """
    hr = hr_row(telegram_username="maria_hr")
    await put(session_factory, hr)

    with pytest.raises(ValueError):
        await update_hr_fields(session, hr.id, telegram_username="Мария Иванова")

    card = await get_hr_detail(session, hr.id)
    assert card.hr.telegram_username == "maria_hr"


async def test_a_username_of_only_an_at_sign_is_erased(session, session_factory):
    """Ник из одной собачки стирается, а не сохраняется пустым."""
    hr = hr_row(telegram_username="maria")
    await put(session_factory, hr)

    await update_hr_fields(session, hr.id, telegram_username="@")

    card = await get_hr_detail(session, hr.id)
    assert card.hr.telegram_username is None
