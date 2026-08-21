"""Следствия опознания отправителя входящего сообщения.

Опознание идёт по идентификатору Telegram, а если его в записи ещё нет — по
нику. Ник у Telegram меняется свободно и может достаться другому человеку,
поэтому при споре он уступает, а запись с чужим идентификатором запасной путь
не берёт вовсе.

Здесь же заслон дополнения записи на пустом нике: остальное, что дописывается с
первым письмом, наблюдается по дороге переписки.
"""

from backend.models import HR
from backend.repository.hr_identify import find_known_hr, refresh_hr_from_telegram
from tests.dbio import put
from tests.factories import hr_row
from tests.fakes.telegram import user


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


async def test_a_username_written_in_another_case_is_the_same_username(
    session, session_factory
):
    """Ник, записанный в другом регистре, — тот же самый ник.

    В Telegram он регистра не различает: `Anna_HR` и `anna_hr` — один человек.
    Запись в карточку приходит как её набрали (ссылкой, заглавными, со
    вставки), а во входящем письме — как её отдаёт Telegram. Сличай их
    посимвольно, и первое же письмо от знакомого HR заведёт вторую его запись,
    а набранная руками карточка останется сиротой без переписки.

    Рядом лежит второй безымянный по идентификатору — иначе запасной путь
    вернул бы единственную строку, какой бы ник ни искали.
    """
    await put(
        session_factory,
        hr_row(name="Мария", telegram_user_id=None, telegram_username="Maria_HR"),
        hr_row(name="Ольга", telegram_user_id=None, telegram_username="olga"),
    )

    assert (await find_known_hr(session, 111, "maria_hr")).name == "Мария"


async def test_the_telegram_id_wins_over_the_username(session, session_factory):
    """При споре идентификатор перевешивает ник.

    Ник у Telegram меняется свободно и мог достаться другому человеку;
    идентификатор — нет.

    Соперник по нику взят без идентификатора нарочно: с чужим идентификатором
    запасной путь его не берёт вовсе, спорить стало бы не с кем, и порядок
    двух путей остался бы непроверенным.
    """
    await put(
        session_factory,
        hr_row(name="по идентификатору", telegram_user_id=111, telegram_username="old"),
        hr_row(name="по нику", telegram_user_id=None, telegram_username="maria"),
    )

    found = await find_known_hr(session, 111, "maria")

    assert found.name == "по идентификатору"


async def test_a_username_taken_over_by_someone_else_leads_nowhere(
    session, session_factory
):
    """Ник, доставшийся другому человеку, к старой записи не приводит.

    Идентификатор Telegram не меняется, ник — свободно. Запись с чужим
    идентификатором под тем же ником принадлежит другому, и письмо нового
    владельца ника не должно попасть в её переписку.
    """
    await put(
        session_factory,
        hr_row(name="Мария", telegram_user_id=999, telegram_username="maria"),
    )

    assert await find_known_hr(session, 222, "maria") is None


async def test_an_unknown_sender_is_not_found(session, session_factory):
    """Незнакомый отправитель не находится, и это не ошибка."""
    await put(session_factory, hr_row(telegram_user_id=111, telegram_username="maria"))

    assert await find_known_hr(session, 222) is None
    assert await find_known_hr(session, 222, "olga") is None


async def test_an_absent_username_does_not_erase_the_stored_one(session, session_factory):
    """Отсутствие ника в сообщении не стирает сохранённый.

    У пользователя Telegram ника может не быть вовсе, а у нас он записан с
    прошлого раза — терять его незачем.
    """
    hr = hr_row(telegram_username="maria")
    await put(session_factory, hr)
    stored = await session.get(HR, hr.id)

    await refresh_hr_from_telegram(
        session, stored, user(id=777, username=None), avatar=None
    )
    await refresh_hr_from_telegram(
        session, stored, user(id=777, username=""), avatar=None
    )

    assert stored.telegram_username == "maria"
