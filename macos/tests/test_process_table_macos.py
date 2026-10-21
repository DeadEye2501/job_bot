from adapters import process_table_macos
from macos.tests.fake_run import recorded_runs

_PS = (
    "    1     0 /sbin/launchd\n"
    "  512     1 /Applications/Google Chrome.app/Contents/MacOS/Google Chrome\n"
)


def test_rows_keep_spaces_in_value(monkeypatch):
    asked = recorded_runs(monkeypatch, stdout=_PS)

    rows = process_table_macos.process_table("comm")

    assert asked == [["ps", "-A", "-o", "pid=,ppid=,comm="]]
    assert rows == [
        (1, 0, "/sbin/launchd"),
        (512, 1, "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
    ]
