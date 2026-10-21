"""Подмена `subprocess.run` в мак-тестах: записывает зовы, отвечает как настоящий.

Сбой отдаётся так же, как у настоящего: с `check=True` — исключением, без него —
ненулевым кодом. Иначе код, забывший `check=True`, проходил бы тесты зелёным,
а на маке считал бы неоткрывшееся открытым.
"""

import subprocess


def recorded_runs(monkeypatch, stdout: str = "", fails: bool = False) -> list[list[str]]:
    """Подменить `subprocess.run`; ответ — список аргументов каждого зова."""
    calls = []

    def run(args, check=False, **_kwargs):
        calls.append(args)
        code = 1 if fails else 0
        if code and check:
            raise subprocess.CalledProcessError(code, args)
        return subprocess.CompletedProcess(args, code, stdout=stdout)

    monkeypatch.setattr(subprocess, "run", run)
    return calls
