"""Следствия выбора способа отправки файла и места для скачанного.

Отправить картинкой Telegram позволяет не всякое изображение: сервер принимает
только три расширения, а на прочих падает. Всё остальное уходит документом —
пусть без предпросмотра, зато дойдёт.

Место для скачанного вычисляется из номера собеседника и номера сообщения, а
не придумывается: обработчик входящего и ручная отправка могут скачивать одно
и то же одновременно, и общий путь сводит их к одному файлу вместо двух.
"""

from pathlib import Path

import pytest

from backend.bot.media import MEDIA_DIR, classify_media, looks_like_photo, media_cache_path, media_path_for_db
from tests.factories import photo_head
from tests.fakes.telegram import document, message


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        pytest.param("снимок.jpg", True, id="jpeg"),
        pytest.param("СНИМОК.JPG", True, id="в верхнем регистре"),
        pytest.param("снимок.jpeg", True, id="jpeg полным написанием"),
        pytest.param("снимок.png", True, id="png"),
        pytest.param("снимок.webp", True, id="webp"),
        pytest.param("снимок.heic", False, id="изображение, но не принимается"),
        pytest.param("снимок.bmp", False, id="старый формат"),
        pytest.param("движение.gif", False, id="движущаяся картинка"),
        pytest.param("резюме.pdf", False, id="не изображение"),
        pytest.param("безымянный", False, id="без расширения"),
    ],
)
def test_only_three_formats_go_as_a_picture(tmp_path, name, expected):
    """Картинкой уходят только три формата, остальное — документом.

    Telegram принимает в отправку картинкой лишь их, а на прочих падает уже
    на своей стороне — и файл не доходит вовсе.
    """
    path = tmp_path / name
    # Непринимаемому расширению достаётся содержимое настоящей картинки:
    # иначе отказ приходил бы от проверки содержимого, и отсев по расширению
    # не наблюдал бы никто.
    path.write_bytes((photo_head(path.suffix) or photo_head(".jpg")).ljust(12, b"\0"))

    assert looks_like_photo(path) is expected


def test_a_renamed_executable_goes_as_a_document(tmp_path):
    """Переименованный .exe уходит документом, а не картинкой.

    По одному расширению файл ушёл бы в send_photo, и Telegram отказал бы
    уже на своей стороне — то есть не дошёл бы вовсе. Документом доходит.
    """
    path = tmp_path / "вирус.exe.jpg"
    path.write_bytes(b"MZ\x90\x00" + bytes(8))

    assert looks_like_photo(path) is False


def test_a_riff_container_that_is_not_a_picture_goes_as_a_document(tmp_path):
    """Контейнер RIFF, который не картинка, уходит документом.

    У WEBP подпись разорвана: `RIFF`, четыре байта длины, и только потом
    `WEBP`. Проверь одно начало — и переименованный звук прошёл бы картинкой.
    """
    path = tmp_path / "звук.webp"
    path.write_bytes(b"RIFF" + bytes(4) + b"WAVE")

    assert looks_like_photo(path) is False


def test_an_unreadable_file_goes_as_a_document(tmp_path):
    """Нечитаемое уходит документом, а не роняет выбор способа.

    Беду с файлом разбирает вызывающий: он читает размер следом и сообщает
    о ней внятно. Выбор между картинкой и документом на этом падать не должен.
    """
    path = tmp_path / "папка.jpg"
    path.mkdir()

    assert looks_like_photo(path) is False


@pytest.mark.parametrize(
    ("msg", "expected"),
    [
        pytest.param(message(photo=object()), ("photo", None), id="картинка"),
        pytest.param(message(photo=None, document=None), (None, None), id="ни то ни то"),
        pytest.param(message(voice=object()), (None, None), id="голосовое"),
    ],
)
def test_a_message_is_classified_by_what_it_carries(msg, expected):
    """Сообщение опознаётся по тому, что при нём пришло.

    Хранятся только картинки и документы; всё прочее становится пузырём с
    подписью вместо вложения.
    """
    assert classify_media(msg) == expected


def test_a_document_is_classified_with_its_name():
    """У документа запоминается имя файла: его показывают в переписке."""
    msg = message(document=document("Тестовое.pdf"))

    assert classify_media(msg) == ("document", "Тестовое.pdf")


def test_a_document_without_a_name_is_still_a_document():
    """Документ без имени остаётся документом, а не пропадает."""
    assert classify_media(message(document=document(None))) == ("document", None)


def test_the_cache_path_is_derived_from_the_message():
    """Место для скачанного выводится из собеседника и номера сообщения.

    Обработчик входящего и ручная отправка могут скачивать одно и то же
    одновременно: общий путь сводит их к одному файлу вместо двух осиротевших.
    """
    got = media_cache_path(7, 42, ".jpg")

    assert got == MEDIA_DIR / "7" / "42.jpg"
    assert media_cache_path(7, 42, ".jpg") == got


def test_a_cached_path_is_stored_relative_to_its_folder():
    """Путь в базу пишется относительно папки вложений.

    Абсолютный путь привязал бы записи к машине, а папка переезжает вместе
    с настройками пользователя.
    """
    absolute = MEDIA_DIR / "7" / "42.jpg"

    assert media_path_for_db(absolute) == "7/42.jpg"


def test_a_path_outside_the_folder_is_stored_whole():
    """Путь вне папки вложений пишется целиком.

    Так быть не должно — всё скачанное идёт через общее место, — но
    обрезать до бессмыслицы хуже, чем сохранить как есть.
    """
    outside = Path(MEDIA_DIR).resolve().parent / "чужое.jpg"

    assert media_path_for_db(outside) == outside.as_posix()
