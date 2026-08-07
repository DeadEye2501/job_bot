"""Следствия опознания или заведения HR по данным из Telegram.

Вызов возвращает не только запись, но и признак «завели только что»: по нему
запускают догоняющий разбор переписки. Без этого признака новый HR, появившийся
при работающем боте, остался бы с пустым чатом до перезапуска.
"""

from backend.repository import find_or_create_hr
from tests.dbio import put
from tests.factories import hr_row
from tests.fakes.telegram import user


async def test_an_unknown_sender_becomes_a_new_record(session):
    """Незнакомый отправитель заводится новой записью, и об этом сообщается."""
    hr, created = await find_or_create_hr(
        session, user(id=111, username="maria", first_name="Мария", last_name="Иванова")
    )

    assert created is True
    assert hr.telegram_user_id == 111
    assert hr.telegram_username == "maria"
    assert hr.name == "Мария Иванова"


async def test_a_sender_without_a_last_name_gets_the_first_one_alone(session):
    """Без фамилии именем становится одно имя, без лишнего пробела."""
    hr, _ = await find_or_create_hr(
        session, user(id=111, username=None, first_name="Мария", last_name=None)
    )

    assert hr.name == "Мария"


async def test_a_sender_without_any_name_gets_none(session):
    """Отправитель вовсе без имени остаётся безымянным, а не с пустой строкой."""
    hr, _ = await find_or_create_hr(
        session, user(id=111, username=None, first_name=None, last_name=None)
    )

    assert hr.name is None


async def test_a_known_sender_is_not_created_twice(session, session_factory):
    """Знакомый по идентификатору отправитель второй записи не получает."""
    known = hr_row(name="Мария", telegram_user_id=111, telegram_username="maria")
    other = hr_row(name="Ольга", telegram_user_id=222, telegram_username="olga")
    await put(session_factory, known, other)

    hr, created = await find_or_create_hr(
        session, user(id=111, username="maria", first_name="Мария", last_name=None)
    )

    assert created is False
    assert hr.id == known.id


async def test_a_handmade_record_gets_its_telegram_id_on_first_contact(
    session, session_factory
):
    """Заведённая руками запись получает идентификатор с первым сообщением.

    Рядом лежит вторая безымянная по идентификатору — иначе запасной путь
    вернул бы единственную строку, каким бы ни был ник.
    """
    handmade = hr_row(name="Мария", telegram_user_id=None, telegram_username="maria")
    another = hr_row(name="Ольга", telegram_user_id=None, telegram_username="olga")
    await put(session_factory, handmade, another)

    hr, created = await find_or_create_hr(
        session, user(id=111, username="maria", first_name="Мария", last_name=None)
    )

    assert created is False
    assert hr.id == handmade.id
    assert hr.telegram_user_id == 111


async def test_a_record_already_holding_an_id_is_not_matched_by_username(
    session, session_factory
):
    """Запись с чужим идентификатором по нику не подхватывается.

    Ник в Telegram освобождается и достаётся другому человеку. Совпадение
    ника при уже известном и другом идентификаторе — это два разных
    человека, а не один.
    """
    taken = hr_row(name="прежний владелец", telegram_user_id=999, telegram_username="maria")
    await put(session_factory, taken)

    hr, created = await find_or_create_hr(
        session, user(id=111, username="maria", first_name="Новая", last_name=None)
    )

    assert created is True
    assert hr.id != taken.id


async def test_a_changed_username_is_written_back(session, session_factory):
    """Сменившийся ник записывается в известную запись."""
    known = hr_row(name="Мария", telegram_user_id=111, telegram_username="old")
    await put(session_factory, known)

    hr, _ = await find_or_create_hr(
        session, user(id=111, username="new", first_name="Мария", last_name=None)
    )

    assert hr.telegram_username == "new"


async def test_a_missing_name_is_filled_in_but_an_existing_one_is_kept(
    session, session_factory
):
    """Пустое имя заполняется из Telegram, а введённое пользователем остаётся."""
    nameless = hr_row(name=None, telegram_user_id=111, telegram_username="maria")
    named = hr_row(name="как я записал", telegram_user_id=222, telegram_username="olga")
    await put(session_factory, nameless, named)

    filled, _ = await find_or_create_hr(
        session, user(id=111, username="maria", first_name="Из", last_name="Телеграма")
    )
    kept, _ = await find_or_create_hr(
        session, user(id=222, username="olga", first_name="Из", last_name="Телеграма")
    )

    assert filled.name == "Из Телеграма"
    assert kept.name == "как я записал"


async def test_an_avatar_fills_an_empty_slot_but_never_replaces_one(
    session, session_factory
):
    """Аватар записывается только в пустое место, поверх имеющегося — нет.

    Иначе свежескачанное изображение затиралось бы устаревшим из более
    позднего, но медленного вызова.
    """
    empty = hr_row(name="без картинки", telegram_user_id=111, avatar=None)
    filled = hr_row(name="с картинкой", telegram_user_id=222, avatar="старая".encode())
    await put(session_factory, empty, filled)

    got_new, _ = await find_or_create_hr(
        session,
        user(id=111, username=None, first_name=None, last_name=None),
        avatar="свежая".encode(),
    )
    kept_old, _ = await find_or_create_hr(
        session,
        user(id=222, username=None, first_name=None, last_name=None),
        avatar="свежая".encode(),
    )

    assert got_new.avatar == "свежая".encode()
    assert kept_old.avatar == "старая".encode()
