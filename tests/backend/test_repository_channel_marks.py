"""Следствия записи канала в чёрный список.

У канала один опознавательный признак — ник, — и записывают его с собачкой,
ровно в том виде, в каком его пишет кнопка на экране.
"""

from backend.repository.channels import channel_blacklist_candidates, channel_blacklist_preferred_value
from tests.factories import channel_row


def test_a_channel_is_listed_by_its_username():
    """В чёрном списке канал записывают ником с собачкой."""
    assert channel_blacklist_candidates(channel_row(username="pyjobs")) == ["@pyjobs"]
    assert channel_blacklist_preferred_value(channel_row(username="pyjobs")) == "@pyjobs"


def test_a_channel_without_a_username_cannot_be_listed():
    """Канал без ника в чёрный список записать нечем."""
    assert channel_blacklist_candidates(channel_row(username=None)) == []
    assert channel_blacklist_preferred_value(channel_row(username=None)) is None
