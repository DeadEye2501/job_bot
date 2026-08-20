"""Следствия сноса данных: что остаётся в каталоге после «удалить всё».

Слот окна дальше первого шага в прогоне не пускают — он убивает процесс, — а
само удаление проверяется здесь, поверх настоящего каталога данных: подменяется
только то, где этот каталог лежит. Перечень имён при этом настоящий, из
`config`: подмени его — проверка стала бы зелёной и на усечённом перечне,
то есть ровно на той беде, ради которой слайс делался.
"""

import logging

import pytest

from backend.single_instance import hold_the_only_copy, release_the_lock
from backend.wipe import wipe_all


@pytest.fixture(autouse=True)
def lock_let_go():
    """Отпускает замок после проверки.

    Не удавшийся снос оставляет замок взятым нарочно — приложение после него
    продолжает работать, — и без этого файл замка пережил бы свой временный
    каталог: открытый дескриптор достался бы следующим проверкам.
    """
    yield
    release_the_lock()


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    """Каталог данных на время одной проверки."""
    monkeypatch.setenv("APPDATA", str(tmp_path))
    import config

    monkeypatch.setattr(config, "_user_data_dir", lambda: tmp_path / "wipe")
    return config.get_data_dir()


def held_by_someone_else(monkeypatch, what: str) -> None:
    """Пусть система откажет в удалении так, как отказывает Windows на занятом.

    Занять файл может антивирус или открытый просмотрщик, и повторяется это
    в четырёх проверках подряд. `what` — полное имя того, чем сносят:
    `pathlib.Path.unlink` у файла, `shutil.rmtree` у папки. Дороги в боевом
    коде у них разные, и перехват у каждой свой.
    """

    def _refuse(*args, **kwargs):
        raise PermissionError(32, "used by another process")

    monkeypatch.setattr(what, _refuse)


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


async def test_a_file_held_by_someone_else_is_reported(
    data_dir, monkeypatch, caplog
):
    """Файл, который не отдал кто-то чужой, попадает в беды и в журнал.

    Занять базу может антивирус или открытый просмотрщик. Промолчи снос —
    человек увидел бы «готово» и остался бы с данными на диске.

    Трассировка нужна отдельно от строки беды: мост схлопывает подробности в
    одну фразу «файлы открыты в другом процессе», и журнал — единственное
    место, где видно, какая система и на чём именно отказала.
    """
    (data_dir / "jobbot.db").write_text("данные", encoding="utf-8")

    held_by_someone_else(monkeypatch, "pathlib.Path.unlink")

    with caplog.at_level(logging.ERROR):
        troubles = await wipe_all(None)

    assert any("jobbot.db" in trouble for trouble in troubles)
    assert "Traceback (most recent call last)" in caplog.text
    assert "PermissionError" in caplog.text


async def test_a_folder_held_by_someone_else_is_reported_too(
    data_dir, monkeypatch, caplog
):
    """Папка, которую не отдали, попадает в беды и в журнал наравне с файлом.

    Вложения и сеансы сносятся другим способом, чем файлы, и отказ у них своя
    дорога: перехват там свой, и написан он отдельной строкой. Сторож у файла
    её не задевает вовсе — сними у папки запись, и набор остался бы зелёным,
    а причина отказа не осела бы нигде.
    """
    (data_dir / "media").mkdir()
    (data_dir / "media" / "1.jpg").write_bytes(b"\x00")

    held_by_someone_else(monkeypatch, "shutil.rmtree")

    with caplog.at_level(logging.ERROR):
        troubles = await wipe_all(None)

    assert any("media/" in trouble for trouble in troubles)
    assert "Traceback (most recent call last)" in caplog.text
    assert "PermissionError" in caplog.text


async def test_the_journal_is_let_go_before_the_files_are_removed(data_dir):
    """Обработчик журнала закрывается **до** удаления, а не после.

    Держит файл сам процесс: закрой его позже — Windows не отдаст файл, и
    снос молча оставит на диске единственное, что человек точно считает
    своим. Порядок и наблюдаем: обработчик запоминает, лежал ли файл на
    месте в тот миг, когда его закрывали.
    """
    log = data_dir / "jobbot.log"
    root = logging.getLogger()

    class Remembering(logging.FileHandler):
        """Обработчик, который помнит, был ли файл на месте при закрытии."""

        file_was_there: bool | None = None

        def close(self) -> None:
            self.file_was_there = log.exists()
            super().close()

    handler = Remembering(log, encoding="utf-8")
    root.addHandler(handler)
    try:
        await wipe_all(None)
    finally:
        root.removeHandler(handler)

    assert handler.file_was_there is True, "журнал закрыли уже после удаления"
    assert not log.exists()


async def test_the_database_is_let_go_before_it_is_deleted(data_dir):
    """Движок отпускает базу до сноса, а не после.

    Windows не отдаёт файл, пока за него держится хоть один открытый движок,
    и снос без этого не удаляет ровно то, ради чего его и зовут. Беда при этом
    не молчит — она доедет до человека отдельной строкой, — но «удалить всё»
    не сработает, а человек будет считать иначе.
    """
    import config
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    db = config.data_files()[0]
    engine = create_async_engine(f"sqlite+aiosqlite:///{db.as_posix()}")
    async with engine.connect() as connection:
        await connection.execute(text("select 1"))

    assert await wipe_all(engine) == []
    assert not db.exists()


async def test_the_lock_comes_back_when_something_survives(data_dir, monkeypatch):
    """Не удавшийся снос возвращает замок единственной копии на место.

    Замок отпускают ради удаления его же файла, но приложение после неудачи
    остаётся жить: человек читает беду и продолжает работать. Оставь замок
    отпущенным — рядом запустилась бы вторая копия, а её и сторожат: две копии
    делят один журнал и одну базу.
    """
    import config

    lock = config.get_lock_path()
    (data_dir / "jobbot.db").write_text("данные", encoding="utf-8")
    assert hold_the_only_copy(lock) is not None

    held_by_someone_else(monkeypatch, "pathlib.Path.unlink")

    troubles = await wipe_all(None)

    assert troubles
    assert hold_the_only_copy(lock) is None, "замок остался отпущенным"


async def test_a_lock_that_will_not_come_back_is_not_passed_over(
    data_dir, monkeypatch, caplog
):
    """Замок, который не удалось взять обратно, молча не проходит.

    Вернуться ему мешает чужая копия, занявшая его в этот самый миг. Про
    недоступный каталог пишет сам замок, и сюда такая беда не доходит.
    Приложение после неудавшегося сноса продолжает работать — уже без
    сторожа, — и увидеть это человек может только в журнале: файлы журнала к
    этому мигу закрыты, а экран журнала кормит буфер.
    """
    (data_dir / "jobbot.db").write_text("данные", encoding="utf-8")

    held_by_someone_else(monkeypatch, "pathlib.Path.unlink")
    monkeypatch.setattr("backend.wipe.hold_the_only_copy", lambda lock_path: None)

    await wipe_all(None)

    assert [one for one in caplog.records if "unguarded" in one.getMessage()], (
        "приложение осталось без сторожа единственной копии молча"
    )


async def test_a_journal_that_will_not_close_leaves_a_trace(data_dir, caplog):
    """Не закрывшийся файл журнала оставляет после себя трассировку.

    Одной строкой в ответе окну беда не разбирается: там имя файла и текст
    ошибки, а почему дескриптор не отдался — видно только по трассировке, и
    записать её больше некому.
    """
    log = data_dir / "jobbot.log"
    root = logging.getLogger()

    class Stubborn(logging.FileHandler):
        """Обработчик, который отдаёт файл с руганью."""

        def close(self) -> None:
            super().close()
            raise OSError("файл журнала не отпустил дескриптор")

    handler = Stubborn(log, encoding="utf-8")
    root.addHandler(handler)
    try:
        troubles = await wipe_all(None)
    finally:
        root.removeHandler(handler)

    assert any("журнал" in trouble for trouble in troubles)
    assert [record for record in caplog.records if record.exc_info], (
        "беда журнала ушла без трассировки"
    )
