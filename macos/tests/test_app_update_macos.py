import sys

from client.bridge.app_update import AppUpdate


def test_mac_build_is_updatable(monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "platform", "darwin")

    assert AppUpdate().version()["ok"]["updatable"] is True
