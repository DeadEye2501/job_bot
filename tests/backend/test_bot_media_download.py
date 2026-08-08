"""Следствия скачивания вложения из входящего сообщения.

Скачанное кладётся в место, вычисленное из номеров собеседника и сообщения, и
уже лежащий там файл второй раз не качается: обработчик входящего и ручная
отправка могут прийти к одному вложению одновременно.

Сбой скачивания вложения не роняет обработку сообщения целиком — текст всё
равно сохранится, просто без файла.
"""

import shutil
from pathlib import Path

import pytest

from backend.bot import MEDIA_DIR, _download_media
from tests.fakes.telegram import message


@pytest.fixture(autouse=True)
def empty_media_dir():
    """Пустая папка вложений на каждый тест.

    Пропуск повторного скачивания смотрит на файл: остаток от соседнего
    теста подменял бы «скачали» на «уже было» и красил проверки зелёным
    в зависимости от порядка запуска.
    """
    if MEDIA_DIR.exists():
        shutil.rmtree(MEDIA_DIR)
    yield
    if MEDIA_DIR.exists():
        shutil.rmtree(MEDIA_DIR)


class _Downloader:
    """Подделка клиента: пишет файл туда, куда просят, и запоминает вызовы."""

    def __init__(self, *, error=None, returns_nothing=False):
        self._error = error
        self._returns_nothing = returns_nothing
        self.calls: list[tuple[int, str]] = []

    async def download_media(self, msg, file_name):
        self.calls.append((msg.id, file_name))
        if self._error is not None:
            raise self._error
        if self._returns_nothing:
            return None
        Path(file_name).write_bytes(b"file")
        return file_name


def _document(name: str | None):
    """Сообщение с документом заданного имени."""
    doc = type("Doc", (), {"file_name": name})()
    return message(id=42, photo=None, document=doc)


async def test_a_message_without_media_downloads_nothing():
    """Сообщение без вложения скачивать нечего, и клиент не трогается."""
    client = _Downloader()

    assert await _download_media(client, message(id=42), 7) is None
    assert client.calls == []


async def test_a_photo_is_saved_as_a_jpeg():
    """Картинка сохраняется с расширением jpeg: Telegram отдаёт их только так."""
    client = _Downloader()

    got = await _download_media(client, message(id=42, photo=object()), 7)

    assert got == "7/42.jpg"
    assert client.calls == [(42, str(MEDIA_DIR / "7" / "42.jpg"))]


async def test_a_document_keeps_the_extension_of_its_name():
    """Документ сохраняется с расширением из своего имени."""
    client = _Downloader()

    got = await _download_media(client, _document("Тестовое.pdf"), 7)

    assert got == "7/42.pdf"


@pytest.mark.parametrize(
    "name",
    [
        pytest.param(None, id="имени нет"),
        pytest.param("", id="имя пустое"),
        pytest.param("безымянный", id="имя без расширения"),
    ],
)
async def test_a_document_without_a_usable_name_gets_a_neutral_extension(name):
    """Документ без пригодного имени получает нейтральное расширение.

    Файл без расширения вовсе неудобен пользователю, а угадывать по
    содержимому здесь нечем.
    """
    client = _Downloader()

    got = await _download_media(client, _document(name), 7)

    assert got == "7/42.bin"


async def test_an_already_downloaded_file_is_not_fetched_again():
    """Уже скачанный файл второй раз не качается.

    Обработчик входящего и ручная отправка приходят к одному вложению
    одновременно, и качать его дважды — лишний трафик и гонка за файл.
    """
    target = MEDIA_DIR / "7" / "42.jpg"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes("уже здесь".encode())
    client = _Downloader()

    got = await _download_media(client, message(id=42, photo=object()), 7)

    assert got == "7/42.jpg"
    assert client.calls == []
    assert target.read_bytes() == "уже здесь".encode()


async def test_a_failed_download_does_not_break_the_message():
    """Сбой скачивания вложения сообщение не роняет.

    Текст сообщения сохранится и без файла: потерять переписку из-за
    неудачной загрузки картинки было бы хуже.
    """
    client = _Downloader(error=OSError("диск отвалился"))

    assert await _download_media(client, message(id=42, photo=object()), 7) is None


async def test_a_download_that_returned_nothing_yields_nothing():
    """Скачивание, ничего не вернувшее, вложения не даёт."""
    client = _Downloader(returns_nothing=True)

    assert await _download_media(client, message(id=42, photo=object()), 7) is None
