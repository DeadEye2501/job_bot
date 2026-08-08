"""Следствия поиска канала по нику.

Ник — то, чем канал назван в подписке пользователя, и по нему же его находят
при разборе входящего поста.
"""

from backend.repository.channels import find_channel_by_username
from tests.dbio import put
from tests.factories import channel_row


async def test_a_channel_is_found_by_its_username(session, session_factory):
    """Канал находится по нику, а незнакомый — не находится."""
    await put(
        session_factory,
        channel_row(username="pyjobs", title="Питон"),
        channel_row(username="jsjobs", title="Фронтенд"),
    )

    assert (await find_channel_by_username(session, "jsjobs")).title == "Фронтенд"
    assert await find_channel_by_username(session, "nobody") is None


async def test_the_username_is_matched_regardless_of_case(session, session_factory):
    """Регистр ника при поиске не важен.

    Ник приходит то из подписки пользователя, то из ссылки в посте, и
    написание там разное: Telegram сам регистр не различает.
    """
    await put(session_factory, channel_row(username="PyJobs", title="Питон"))

    assert (await find_channel_by_username(session, "pyjobs")).title == "Питон"
    assert (await find_channel_by_username(session, "PYJOBS")).title == "Питон"
