"""Следствия скачивания вложения из входящего сообщения.

Скачанное кладётся в место, вычисленное из номеров собеседника и сообщения, и
уже лежащий там файл второй раз не качается: обработчик входящего и ручная
отправка могут прийти к одному вложению одновременно.

Сбой скачивания вложения не роняет обработку сообщения целиком — текст всё
равно сохранится, просто без файла.
"""

import pytest

from backend.bot.client import MEDIA_DIR, _download_media
from tests.fakes.telegram import FakeTelegramClient, document, message


async def test_a_message_without_media_downloads_nothing():
    """Сообщение без вложения скачивать нечего, и клиент не трогается."""
    client = FakeTelegramClient()

    assert await _download_media(client, message(id=42), 7) is None
    assert client.download_calls == []


async def test_a_photo_is_saved_as_a_jpeg():
    """Картинка сохраняется с расширением jpeg: Telegram отдаёт их только так."""
    client = FakeTelegramClient()
    msg = message(id=42, photo=object())

    got = await _download_media(client, msg, 7)

    assert got == "7/42.jpg"
    assert client.download_calls == [msg]
    assert client.download_paths == [str(MEDIA_DIR / "7" / "42.jpg")]


async def test_a_document_keeps_the_extension_of_its_name():
    """Документ сохраняется с расширением из своего имени."""
    client = FakeTelegramClient()
    msg = message(id=42, photo=None, document=document("Тестовое.pdf"))

    assert await _download_media(client, msg, 7) == "7/42.pdf"


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
    client = FakeTelegramClient()
    msg = message(id=42, photo=None, document=document(name))

    assert await _download_media(client, msg, 7) == "7/42.bin"


async def test_an_already_downloaded_file_is_not_fetched_again():
    """Уже скачанный файл второй раз не качается.

    Обработчик входящего и ручная отправка приходят к одному вложению
    одновременно, и качать его дважды — лишний трафик и гонка за файл.
    """
    target = MEDIA_DIR / "7" / "42.jpg"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes("уже здесь".encode())
    client = FakeTelegramClient()

    got = await _download_media(client, message(id=42, photo=object()), 7)

    assert got == "7/42.jpg"
    assert client.download_calls == []
    assert target.read_bytes() == "уже здесь".encode()


async def test_a_failed_download_does_not_break_the_message():
    """Сбой скачивания вложения сообщение не роняет.

    Текст сообщения сохранится и без файла: потерять переписку из-за
    неудачной загрузки картинки было бы хуже.
    """
    client = FakeTelegramClient(fails={"download_media": OSError("диск отвалился")})

    assert await _download_media(client, message(id=42, photo=object()), 7) is None


async def test_a_download_that_returned_nothing_yields_nothing():
    """Скачивание, ничего не вернувшее, вложения не даёт."""
    client = FakeTelegramClient(media=None)

    assert await _download_media(client, message(id=42, photo=object()), 7) is None
