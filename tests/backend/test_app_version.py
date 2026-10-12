"""Новее ли релиз, чем запущенное приложение: по тегу вида `v1.2.3`."""

import pytest

from backend import app_version
from backend.app_version import newer_version


@pytest.fixture
def running_1_9_0(monkeypatch):
    """Запущена версия 1.9.0: на ней видно, что номера сравниваются числами."""
    monkeypatch.setattr(app_version, "VERSION", "1.9.0")


@pytest.mark.parametrize(("tag", "shown"), [
    ("v1.9.1", "1.9.1"), ("v1.10.0", "1.10.0"), ("v2.0.0", "2.0.0"),
])
def test_a_higher_number_is_newer_and_named_without_the_prefix(running_1_9_0, tag, shown):
    assert newer_version(tag) == shown


@pytest.mark.parametrize("tag", ["v1.9.0", "v1.8.9", "v0.99.99"])
def test_the_same_or_lower_number_is_not_newer(running_1_9_0, tag):
    assert newer_version(tag) is None


@pytest.mark.parametrize("tag", ["latest", "", "v1.10", "v1.10.0-beta"])
def test_a_tag_that_is_not_a_version_is_not_newer(running_1_9_0, tag):
    """Тег, который не разбирается как номер, обновлением не считается — а не роняет проверку."""
    assert newer_version(tag) is None
