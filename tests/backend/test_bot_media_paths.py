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

from backend.bot import (
    MEDIA_DIR,
    _classify_media,
    _looks_like_photo,
    _media_cache_path,
    _media_path_for_db,
    _shares_provider,
)
from tests.fakes.telegram import message


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
def test_only_three_formats_go_as_a_picture(name, expected):
    """Картинкой уходят только три формата, остальное — документом.

    Telegram принимает в отправку картинкой лишь их, а на прочих падает уже
    на своей стороне — и файл не доходит вовсе.
    """
    assert _looks_like_photo(Path(name)) is expected


def test_a_renamed_file_does_not_slip_through_as_a_picture():
    """Переименованный файл картинкой не пройдёт.

    Расширения мало: под ним может лежать что угодно. Совпасть должно и то,
    что о содержимом говорит его вид.
    """
    assert _looks_like_photo(Path("вирус.exe.jpg")) is True
    assert _looks_like_photo(Path("вирус.jpg.exe")) is False


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
    assert _classify_media(msg) == expected


def test_a_document_is_classified_with_its_name():
    """У документа запоминается имя файла: его показывают в переписке."""
    doc = type("Doc", (), {"file_name": "Тестовое.pdf"})()

    assert _classify_media(message(document=doc)) == ("document", "Тестовое.pdf")


def test_a_document_without_a_name_is_still_a_document():
    """Документ без имени остаётся документом, а не пропадает."""
    doc = type("Doc", (), {"file_name": None})()

    assert _classify_media(message(document=doc)) == ("document", None)


def test_the_cache_path_is_derived_from_the_message():
    """Место для скачанного выводится из собеседника и номера сообщения.

    Обработчик входящего и ручная отправка могут скачивать одно и то же
    одновременно: общий путь сводит их к одному файлу вместо двух осиротевших.
    """
    got = _media_cache_path(7, 42, ".jpg")

    assert got == MEDIA_DIR / "7" / "42.jpg"
    assert _media_cache_path(7, 42, ".jpg") == got


def test_a_cached_path_is_stored_relative_to_its_folder():
    """Путь в базу пишется относительно папки вложений.

    Абсолютный путь привязал бы записи к машине, а папка переезжает вместе
    с настройками пользователя.
    """
    absolute = MEDIA_DIR / "7" / "42.jpg"

    assert _media_path_for_db(absolute) == "7/42.jpg"


def test_a_path_outside_the_folder_is_stored_whole():
    """Путь вне папки вложений пишется целиком.

    Так быть не должно — всё скачанное идёт через общее место, — но
    обрезать до бессмыслицы хуже, чем сохранить как есть.
    """
    outside = Path(MEDIA_DIR).resolve().parent / "чужое.jpg"

    assert _media_path_for_db(outside) == outside.as_posix()


class _Provider:
    """Настройка провайдера в том виде, в каком её сравнивают."""

    def __init__(self, base_url, api_key, model="qwen"):
        self.base_url = base_url
        self.api_key = api_key
        self.model = model


@pytest.mark.parametrize(
    ("a", "b", "expected"),
    [
        pytest.param(
            _Provider("http://a", "ключ"), _Provider("http://a", "ключ"), True,
            id="совпадают",
        ),
        pytest.param(
            _Provider("http://a", "ключ"), _Provider("http://b", "ключ"), False,
            id="разные адреса",
        ),
        pytest.param(
            _Provider("http://a", "ключ"), _Provider("http://a", "другой"), False,
            id="разные ключи",
        ),
        pytest.param(
            _Provider("http://a", "ключ", "qwen"),
            _Provider("http://a", "ключ", "llama"),
            True,
            id="разные модели — всё равно один",
        ),
        pytest.param(None, _Provider("http://a", "ключ"), False, id="первого нет"),
        pytest.param(_Provider("http://a", "ключ"), None, False, id="второго нет"),
        pytest.param(None, None, False, id="нет обоих"),
    ],
)
def test_two_providers_share_a_client_when_the_endpoint_and_key_match(a, b, expected):
    """Две настройки делят одно соединение, если совпали адрес и ключ.

    Модель не сравнивается нарочно: она задаётся на каждый запрос, а не на
    соединение, и разводить из-за неё два клиента было бы расточительством.
    """
    assert _shares_provider(a, b) is expected
