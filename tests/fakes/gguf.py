"""Подделка движка эмбеддингов: настоящая модель в тестах не грузится.

Общая для тестов адаптера, моста и потока приёма: каждому нужна модель,
которая отвечает сразу и помнит, сколько раз её грузили.
"""

from adapters import gguf_embed


class Model:
    """Модель-подделка: пишет в журнал загрузки и закрытия, вектор — длина текста."""

    def __init__(self, journal: list, *, per_token: bool = False) -> None:
        self.journal = journal
        self.per_token = per_token
        journal.append("загружена")

    def embed(self, text: str) -> list:
        """Вектор текста; `per_token` — вектор на каждый токен, как у чат-модели."""
        if self.per_token:
            return [[1.0, 0.0] for _ in text]
        return [float(len(text)), 1.0]

    def close(self) -> None:
        self.journal.append("закрыта")


def model_file(folder) -> str:
    """Пустышка `*.gguf` на диске: файл есть, движок его не читает."""
    path = folder / "модель.gguf"
    path.write_bytes(b"GGUF")
    return str(path)


def engine(monkeypatch, load) -> None:
    """Подставить движку свою загрузку: `load(path)` отдаёт модель или бросает."""
    monkeypatch.setattr(gguf_embed, "_open_model", load)


def failing_engine(monkeypatch, trouble: BaseException) -> None:
    """Движок, который файл не грузит, а бросает `trouble`."""

    def load(_path):
        raise trouble

    engine(monkeypatch, load)


def engine_journal(monkeypatch) -> list[str]:
    """Подставить движок, который грузит подделку; вернуть журнал её загрузок."""
    happened: list[str] = []
    engine(monkeypatch, lambda _path: Model(happened))
    return happened

