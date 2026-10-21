import os

from adapters import app_tied_macos


def test_children_matched_by_mac_name(monkeypatch):
    me = os.getpid()
    monkeypatch.setattr(app_tied_macos, "process_table", lambda _column: [
        (21, me, "/opt/homebrew/bin/node"),
        (22, me, "/bin/zsh"),
        (23, 1, "/opt/homebrew/bin/node"),
    ])
    tied = []
    monkeypatch.setattr(app_tied_macos, "tie_to_app", tied.append)

    assert app_tied_macos.tie_children_named("node.exe") == 1
    assert tied == [21]
