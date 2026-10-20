"""Настоящий exe Claude Code рядом с npm-обёрткой Windows."""

from pathlib import Path


def executable(found: str) -> str:
    beside = Path(found).parent / "node_modules" / "@anthropic-ai" / "claude-code" / "bin" / "claude.exe"
    return str(beside) if beside.is_file() else found
