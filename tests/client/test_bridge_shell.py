"""Следствия обращения к оболочке: чем открывают ссылку из карточки.

Предмет один — дошло ли до оболочки то, что просили, и не ушло ли к ней
лишнее. Копирование в буфер сюда больше не входит: оно было написано на Qt, а
страница кладёт текст в буфер сама.

Два нижних сторожа исполняют само тело `open_in_system`, а не подменяют его у
зовущего. До них тело не исполнялось ни одним тестом — а это ровно та функция,
которую ревью А2.4 нашло написанной неверно. Красной фазы у них не было:
дописаны по находке, доверие заслужат итоговым проходом.
"""

import logging

import pytest

from client.bridge.desktop import open_in_system


@pytest.fixture
def opened(monkeypatch) -> list:
    """Ловит адреса вместо того, чтобы открывать их системой."""
    addresses: list[str] = []
    monkeypatch.setattr(
        "client.bridge.desktop.open_in_system",
        lambda target: addresses.append(target) or True,
    )
    return addresses


async def test_an_address_reaches_the_shell_as_it_was_given(api, ask, opened):
    """Ссылка уходит в оболочку той же, какой пришла со страницы.

    Ссылки ведут на объявление и на переписку, и в них бывает и якорь, и
    хвост с отметками. Подправь мост адрес — открылась бы не та страница.
    """
    answer = await ask(api.system.open_url, "https://t.me/pyjobs/42")

    assert "ok" in answer
    assert opened == ["https://t.me/pyjobs/42"]


async def test_an_empty_address_is_not_opened_at_all(api, ask, opened):
    """Пустой адрес не открывают вовсе, а отбивают словами.

    Ссылки в карточках бывают пустыми — источник её не прислал. Уйди пустое
    в оболочку, открылось бы окно браузера с пустой страницей, и человек
    решил бы, что приложение сломалось.
    """
    answer = await ask(api.system.open_url, "")

    assert answer["fail"] == "denied"
    assert opened == []


def test_the_system_gets_the_target_and_says_it_went_through(monkeypatch):
    """Открытое системой названо открытым, и открыто именно то, что просили.

    Окна человек в этот миг не видит — оно поднимается чужим приложением, — и
    «дошло» от «не дошло» он отличает только по нашему ответу.
    """
    handed: list[str] = []
    monkeypatch.setattr(
        "client.bridge.desktop.os.startfile", handed.append, raising=False
    )

    assert open_in_system("C:/резюме.pdf") is True
    assert handed == ["C:/резюме.pdf"]


def test_a_refusal_from_the_system_is_named_and_written_down(monkeypatch, caplog):
    """Отказ системы возвращается «не смогли» и уходит в журнал с трассировкой.

    Отказывает она по-разному: нет приложения под расширение, файл занят, путь
    ведёт в никуда. Человеку хватает «не удалось», а разбирать это потом
    придётся по трассировке — без неё в журнале осталось бы одно слово.
    """
    def refuse(target: str) -> None:
        raise OSError("нет приложения для .pdf")

    monkeypatch.setattr(
        "client.bridge.desktop.os.startfile", refuse, raising=False
    )

    with caplog.at_level(logging.ERROR, logger="client.bridge.desktop"):
        assert open_in_system("C:/резюме.pdf") is False

    # След пришпилен к своему источнику: `any` по всем записям прошёл бы и от
    # чужой трассировки, случившейся в том же тесте.
    assert [
        record.name for record in caplog.records if record.exc_info
    ] == ["client.bridge.desktop"]
