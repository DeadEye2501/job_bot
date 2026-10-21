import sys

import pytest

from client import trouble_macos
from macos.tests.fake_run import recorded_runs


def test_trouble_text_goes_as_argument(monkeypatch):
    calls = recorded_runs(monkeypatch)
    text = 'Нет "ключа"'

    trouble_macos.show_trouble(text)

    assert calls[0][0] == "osascript"
    assert calls[0][-1] == text


def test_failed_alert_does_not_raise(monkeypatch):
    recorded_runs(monkeypatch, fails=True)

    trouble_macos.show_trouble("беда")


@pytest.mark.skipif(sys.platform != "darwin", reason="только macOS")
def test_start_trouble_reaches_the_alert(monkeypatch):
    from client.trouble_box import show_trouble

    calls = recorded_runs(monkeypatch)

    show_trouble("беда")

    assert calls[0][0] == "osascript"
