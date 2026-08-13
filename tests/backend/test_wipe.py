"""Следствия сноса данных: что остаётся в каталоге после «удалить всё».

Слот окна дальше первого шага в прогоне не пускают — он убивает процесс, — а
само удаление проверяется здесь, поверх настоящего каталога данных: подменяется
только то, где этот каталог лежит. Перечень имён при этом настоящий, из
`config`: подмени его — проверка стала бы зелёной и на усечённом перечне,
то есть ровно на той беде, ради которой слайс делался.
"""

import logging

import pytest

from backend.wipe import wipe_all


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    """Каталог данных на время одной проверки."""
    monkeypatch.setenv("APPDATA", str(tmp_path))
    import config

    monkeypatch.setattr(config, "_user_data_dir", lambda: tmp_path / "wipe")
    return config.get_data_dir()


async def test_the_journal_does_not_survive_the_wipe(data_dir):
    """Журнал и его повёрнутые копии уходят вместе со всем остальным.

    В журнале лежит переписка человека — имена, ники, тексты писем. Переживи
    он «удалить всё», человек, отдавший ноутбук или начавший с чистого листа,
    оставил бы всё это на диске, будучи уверенным в обратном.
    """
    for name in ("jobbot.log", "jobbot.log.1", "jobbot.log.3"):
        (data_dir / name).write_text("Мария писала: ...", encoding="utf-8")

    assert await wipe_all(None) == []
    assert list(data_dir.iterdir()) == []


async def test_the_lock_and_the_database_go_too(data_dir):
    """Файл замка и база со спутниками уходят тем же движением.

    Замок держит сам работающий процесс, база — движок; оставь снос любого из
    них, и следующий запуск нашёл бы старые данные там, где обещана пустота.
    """
    for name in (
        "jobbot.db", "jobbot.db-shm", "jobbot.db-wal", "jobbot.lock",
    ):
        (data_dir / name).write_text("данные", encoding="utf-8")
    (data_dir / "media").mkdir()
    (data_dir / "media" / "1.jpg").write_bytes(b"\x00")
    (data_dir / "sessions").mkdir()

    assert await wipe_all(None) == []
    assert list(data_dir.iterdir()) == []


async def test_a_file_held_by_someone_else_is_reported(data_dir, monkeypatch):
    """Файл, который не отдал кто-то чужой, попадает в беды, а не в тишину.

    Занять базу может антивирус или открытый просмотрщик. Промолчи снос —
    человек увидел бы «готово» и остался бы с данными на диске.
    """
    (data_dir / "jobbot.db").write_text("данные", encoding="utf-8")

    def _refuse(self, *args, **kwargs):
        raise PermissionError(32, "used by another process")

    monkeypatch.setattr("pathlib.Path.unlink", _refuse)

    troubles = await wipe_all(None)

    assert any("jobbot.db" in trouble for trouble in troubles)


async def test_the_journal_is_let_go_before_the_files_are_removed(data_dir):
    """Обработчики журнала закрываются до удаления — иначе Windows файл не отдаст.

    Держит его сам процесс, и снос без этого молча оставлял бы на диске
    единственное, что человек точно считает своим.
    """
    root = logging.getLogger()
    handler = logging.FileHandler(data_dir / "jobbot.log", encoding="utf-8")
    root.addHandler(handler)
    try:
        await wipe_all(None)
        assert handler not in root.handlers
    finally:
        root.removeHandler(handler)
