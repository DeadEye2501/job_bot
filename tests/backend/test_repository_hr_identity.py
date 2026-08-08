"""Следствия опознания отправителя входящего сообщения.

Опознание идёт по идентификатору Telegram, а если его в записи ещё нет — по
нику. Ник у Telegram меняется свободно и может достаться другому человеку,
поэтому при споре он уступает.
"""

from backend.repository.hr_identify import find_known_hr, refresh_hr_username
from tests.dbio import put
from tests.factories import hr_row


async def test_an_hr_is_found_by_telegram_id(session, session_factory):
    """HR находится по идентификатору Telegram."""
    await put(
        session_factory,
        hr_row(name="Мария", telegram_user_id=111, telegram_username="maria"),
        hr_row(name="Ольга", telegram_user_id=222, telegram_username="olga"),
    )

    found = await find_known_hr(session, 222)

    assert found.name == "Ольга"


async def test_an_hr_added_by_username_is_found_before_the_id_is_known(
    session, session_factory
):
    """HR, заведённый одним ником, находится по нику, пока идентификатора нет.

    Так бывает у тех, кого добавили руками с экрана контактов: идентификатор
    появляется только с первым входящим сообщением.

    Рядом лежит второй такой же безымянный по идентификатору — иначе запасной
    путь вернул бы единственную строку, какой бы ник ни искали, и сравнение
    по нику осталось бы непроверенным.
    """
    await put(
        session_factory,
        hr_row(name="Мария", telegram_user_id=None, telegram_username="maria"),
        hr_row(name="Ольга", telegram_user_id=None, telegram_username="olga"),
    )

    assert (await find_known_hr(session, 111, "maria")).name == "Мария"
    assert (await find_known_hr(session, 111, "olga")).name == "Ольга"


async def test_the_telegram_id_wins_over_the_username(session, session_factory):
    """При споре идентификатор перевешивает ник.

    Ник у Telegram меняется свободно и мог достаться другому человеку;
    идентификатор — нет.
    """
    await put(
        session_factory,
        hr_row(name="по идентификатору", telegram_user_id=111, telegram_username="old"),
        hr_row(name="по нику", telegram_user_id=999, telegram_username="maria"),
    )

    found = await find_known_hr(session, 111, "maria")

    assert found.name == "по идентификатору"


async def test_an_unknown_sender_is_not_found(session, session_factory):
    """Незнакомый отправитель не находится, и это не ошибка."""
    await put(session_factory, hr_row(telegram_user_id=111, telegram_username="maria"))

    assert await find_known_hr(session, 222) is None
    assert await find_known_hr(session, 222, "olga") is None


def test_a_changed_username_is_picked_up():
    """Сменившийся ник подхватывается из входящего сообщения."""
    hr = hr_row(telegram_username="old")

    refresh_hr_username(hr, "new")

    assert hr.telegram_username == "new"


def test_an_absent_username_does_not_erase_the_stored_one():
    """Отсутствие ника в сообщении не стирает сохранённый.

    У пользователя Telegram ника может не быть вовсе, а у нас он записан с
    прошлого раза — терять его незачем.
    """
    hr = hr_row(telegram_username="maria")

    refresh_hr_username(hr, None)
    refresh_hr_username(hr, "")

    assert hr.telegram_username == "maria"
