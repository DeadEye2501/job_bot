import subprocess

from adapters import process_table_macos

_PS = (
    "    1     0 /sbin/launchd\n"
    "  512     1 /Applications/Google Chrome.app/Contents/MacOS/Google Chrome\n"
)


def test_rows_keep_spaces_in_value(monkeypatch):
    asked = []

    def ps(args, **_kwargs):
        asked.append(args)
        return subprocess.CompletedProcess(args, 0, stdout=_PS)

    monkeypatch.setattr(subprocess, "run", ps)

    rows = process_table_macos.process_table("comm")

    assert asked == [["ps", "-A", "-o", "pid=,ppid=,comm="]]
    assert rows == [
        (1, 0, "/sbin/launchd"),
        (512, 1, "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
    ]
