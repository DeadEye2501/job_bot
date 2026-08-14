"""Следствия обращения к оболочке: чем открывают ссылку из карточки.

Предмет один — дошло ли до оболочки то, что просили, и не ушло ли к ней
лишнее. Копирование в буфер сюда больше не входит: оно было написано на Qt, а
страница кладёт текст в буфер сама.
"""

import pytest


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
