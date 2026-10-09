"""Claude Code как водитель агента: процесс, его инструменты, его итог."""

from dataclasses import dataclass


@dataclass(frozen=True)
class AgentEnd:
    """Итог процесса агента: дошёл ли он до конца, что сказал, исчерпан ли лимит подписки."""

    ok: bool
    detail: str
    limit_exhausted: bool
