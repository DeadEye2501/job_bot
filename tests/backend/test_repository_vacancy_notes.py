"""Следствия правки заметки вакансии.

Заметку пишет пользователь в поле на экране, и каждое нажатие клавиши шлёт
сохранение. Отсюда две особенности записи, которые здесь и закрепляются:
пустое приводится к отсутствию, а пробелы внутри непустого сохраняются буква
в букву.

Прочитать записанное нечем, кроме карточки вакансии, поэтому проверки читают
через неё — но предмет здесь запись, а не чтение.
"""

from backend.repository.vacancies_card import get_vacancy_detail, update_vacancy_notes
from tests.dbio import put
from tests.factories import vacancy_row


async def test_notes_of_a_missing_vacancy_are_not_written(session, session_factory):
    """Заметку несуществующей вакансии записать нельзя, и вызов об этом сообщает."""
    await put(session_factory, vacancy_row())

    assert await update_vacancy_notes(session, 10_000, "что-то") is False


async def test_notes_are_stored_as_given(session, session_factory):
    """Заметка сохраняется и видна при следующем чтении."""
    vacancy = vacancy_row(notes=None)
    await put(session_factory, vacancy)

    assert await update_vacancy_notes(session, vacancy.id, "созвон в четверг") is True

    card = await get_vacancy_detail(session, vacancy.id)
    assert card.vacancy.notes == "созвон в четверг"


async def test_notes_of_only_whitespace_are_stored_as_absence(
    session, session_factory
):
    """Заметка из одних пробелов записывается как отсутствие, а не как пустая строка.

    Пустая строка и `NULL` для базы разные значения, а для пользователя —
    одно и то же: он стёр текст. Экран отличает «комментария нет» от
    «комментарий есть, но пуст», и второе состояние не должно возникать.
    """
    vacancy = vacancy_row(notes="было что-то")
    await put(session_factory, vacancy)

    assert await update_vacancy_notes(session, vacancy.id, "   \n  ") is True

    card = await get_vacancy_detail(session, vacancy.id)
    assert card.vacancy.notes is None


async def test_clearing_notes_with_none_also_stores_absence(session, session_factory):
    """Явное «ничего» тоже стирает заметку."""
    vacancy = vacancy_row(notes="было что-то")
    await put(session_factory, vacancy)

    assert await update_vacancy_notes(session, vacancy.id, None) is True

    card = await get_vacancy_detail(session, vacancy.id)
    assert card.vacancy.notes is None


async def test_whitespace_around_real_notes_is_kept_verbatim(session, session_factory):
    """Пробелы вокруг непустой заметки сохраняются как есть, без обрезки.

    Экран сравнивает сохранённое с тем, что в поле ввода, чтобы не слать
    правку на каждое нажатие клавиши. Обрезка на записи ломала бы это
    сравнение, и один и тот же текст сохранялся бы снова и снова.
    """
    vacancy = vacancy_row()
    await put(session_factory, vacancy)

    await update_vacancy_notes(session, vacancy.id, "  созвон  ")

    card = await get_vacancy_detail(session, vacancy.id)
    assert card.vacancy.notes == "  созвон  "
