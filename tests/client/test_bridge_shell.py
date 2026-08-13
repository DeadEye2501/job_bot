"""Следствия обращений к оболочке: открыть ссылку и положить текст в буфер.

Предмет — два слота, у которых нет ни ответа, ни записи: всё, что они делают,
происходит за пределами приложения. Наблюдать тут можно одно — дошло ли до
оболочки то, что просили, и не ушло ли к ней лишнее.
"""

import pytest
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QApplication


@pytest.fixture
def opened(monkeypatch) -> list:
    """Ловит адреса вместо того, чтобы открывать их в браузере."""
    addresses: list[str] = []
    monkeypatch.setattr(
        QDesktopServices, "openUrl", lambda url: addresses.append(url.toString())
    )
    return addresses


@pytest.fixture
def clipboard(monkeypatch) -> list:
    """Подставляет буфер обмена, которого без поднятого приложения нет."""
    copied: list[str] = []

    class Buffer:
        def setText(self, text: str) -> None:
            copied.append(text)

    monkeypatch.setattr(QApplication, "clipboard", lambda: Buffer())
    return copied


async def test_an_address_reaches_the_browser_as_it_was_given(main_api, opened):
    """Ссылка уходит в браузер той же, какой пришла из окна.

    Ссылки ведут на объявление и на переписку, и в них бывает и якорь, и
    хвост с отметками. Подправь мост адрес — открылась бы не та страница.
    """
    main_api.open_external_url("https://t.me/pyjobs/42")

    assert opened == ["https://t.me/pyjobs/42"]


async def test_an_empty_address_is_not_opened_at_all(main_api, opened):
    """Пустой адрес не открывают вовсе.

    Ссылки в карточках бывают пустыми — источник её не прислал. Уйди пустое
    в оболочку, открылось бы окно браузера с пустой страницей, и человек
    решил бы, что приложение сломалось.
    """
    main_api.open_external_url("")

    assert opened == []


async def test_the_copied_text_reaches_the_buffer(main_api, clipboard):
    """Скопированное ложится в буфер тем же текстом.

    Копируют ник и ссылку, чтобы вставить их в другое место; молчаливая
    правка по дороге вскрылась бы уже там, где вставили.
    """
    main_api.copy_to_clipboard("@maria")

    assert clipboard == ["@maria"]
