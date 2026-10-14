"""Следствия обращения к оболочке: что окно отдаёт системе, а что нет.

Предмет один — дошло ли до оболочки то, что просили, и не ушло ли к ней
лишнее. Дорог наружу две, и заслоны у них разные: у ссылки разбирается схема,
у вложения — расширение и то, лежит ли оно в каталоге медиа. Копирование в
буфер сюда больше не входит: оно было написано на Qt, а страница кладёт текст
в буфер сама.

Два сторожа в конце исполняют само тело `open_in_system`, а не подменяют его у
зовущего. До них тело не исполнялось ни одним тестом — а это ровно та функция,
которую ревью А2.4 нашло написанной неверно. Красной фазы у них не было:
дописаны по находке, доверие заслужат итоговым проходом.
"""

import logging

import pytest

from client.bridge.desktop import chosen_path, open_in_system
from client.serving import MEDIA_PREFIX


@pytest.fixture
def opened(monkeypatch) -> list:
    """Ловит адреса вместо того, чтобы открывать их системой."""
    addresses: list[str] = []
    monkeypatch.setattr(
        "client.bridge.desktop.open_in_system",
        lambda target: addresses.append(target) or True,
    )
    return addresses


@pytest.fixture
def refused_by_the_system(monkeypatch) -> None:
    """Система берёт цель, но открыть не может.

    Так она отвечает на снесённый ярлык, на файл без сопоставленной программы
    и на занятую цель: зов проходит, а `False` возвращается. Перевод этого
    `False` в отказ — своя ветка у ссылки и своя у вложения, и приманкой,
    отвечающей «открыли», она не исполняется ни разу.
    """
    monkeypatch.setattr("client.bridge.desktop.open_in_system", lambda target: False)


@pytest.fixture
def media(monkeypatch, tmp_path):
    """Каталог медиа на время теста: вложения ищут файл именно в нём.

    Своим подкаталогом, а не самим `tmp_path`: заслон проверяется тем, что
    выше каталога есть куда уйти и там лежит настоящий файл.
    """
    inside_tmp = tmp_path / "медиа"
    inside_tmp.mkdir()
    monkeypatch.setattr("backend.bot.media.MEDIA_DIR", inside_tmp)
    return inside_tmp


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


async def test_a_link_of_a_stranger_scheme_is_not_handed_over(api, ask, opened):
    """Ссылка чужой схемы системе не отдаётся вовсе.

    Схема решает, чем система откроет ссылку, и `file:` открывает не браузер,
    а то, на что путь указывает: строка из карточки, набранная кем угодно,
    запустила бы программу с диска одним нажатием на «Открыть сайт».
    """
    answer = await ask(api.system.open_url, "file:///C:/Windows/system32/calc.exe")

    assert answer["fail"] == "denied"
    assert opened == []


async def test_a_telegram_link_opens(api, ask, opened):
    """Ссылка в само приложение Telegram открывается тоже.

    Схема у неё не `http`, и заслон, знающий только про браузерные, отбил бы
    её вместе с чужими.
    """
    answer = await ask(api.system.open_url, "tg://resolve?domain=ivanov")

    assert "ok" in answer
    assert opened == ["tg://resolve?domain=ivanov"]


async def test_a_mail_and_a_phone_contact_open_too(api, ask, opened):
    """Контакт вакансии бывает почтой и телефоном: письмо и звонок система
    открывает своими программами, как ссылку — браузером."""
    mail = await ask(api.system.open_url, "mailto:hr@example.test")
    phone = await ask(api.system.open_url, "tel:+79001234567")

    assert "ok" in mail and "ok" in phone
    assert opened == ["mailto:hr@example.test", "tel:+79001234567"]


async def test_a_link_the_system_would_not_open_is_named_a_refusal(
    api, ask, refused_by_the_system
):
    """Ссылку, которую система не открыла, окно называет отказом.

    Иначе окно отвечает «открыли» на ссылку, которую никто не открыл, и
    человек ждёт чужого окна, которого не будет.
    """
    answer = await ask(api.system.open_url, "https://example.test/vacancy")

    assert answer["fail"] == "denied"
    assert answer["detail"] == "Не удалось открыть ссылку"


async def test_an_attachment_the_system_would_not_open_is_named_a_refusal(
    api, ask, media, refused_by_the_system
):
    """И вложение, которое система не открыла, — по той же причине.

    Своя ветка у своего слота: у ссылки и у файла общее только то, что оба
    уходят системе, а отказы у них разные и по словам, и по месту.
    """
    (media / "1").mkdir()
    (media / "1" / "42.pdf").write_bytes(b"%PDF-1.4")

    answer = await ask(api.system.open_attachment, f"{MEDIA_PREFIX}1/42.pdf")

    assert answer["fail"] == "denied"
    assert answer["detail"] == "Не удалось открыть вложение"


async def test_an_attachment_we_do_not_open_is_shown_in_the_folder(
    api, ask, opened, media, monkeypatch
):
    """Вложение, которое приложение не открывает, оно показывает в папке.

    Открывать самим нельзя: имя файла называет собеседник, и «Оферта.pdf.exe»
    в ленте выглядит документом — род вложения у него «документ», значок тот
    же, — а по нажатию исполнилась бы присланная чужим человеком программа.

    Прятать тоже незачем: файл прислали человеку, и добраться до него он
    вправе. Проводник показывает его выделенным и не запускает ничего — что
    делать дальше, решает сам человек.
    """
    (media / "1").mkdir()
    (media / "1" / "42.exe").write_bytes(b"MZ")
    shown: list = []
    monkeypatch.setattr(
        "client.bridge.desktop.subprocess.Popen", lambda args: shown.append(args)
    )

    answer = await ask(api.system.open_attachment, f"{MEDIA_PREFIX}1/42.exe")

    assert "ok" in answer
    # Показан, а не запущен: система получила проводник с отбором, а не сам файл.
    assert opened == []
    assert shown == [["explorer", f"/select,{media / '1' / '42.exe'}"]]


async def test_a_document_attachment_opens(api, ask, opened, media):
    """Присланный документ открывается тем, чем его открывает система.

    Ради этого кнопка и нарисована: резюме, оферту и описание вакансии человек
    читает не в переписке, а в своей программе для документов.
    """
    (media / "1").mkdir()
    (media / "1" / "42.pdf").write_bytes(b"%PDF-1.4")

    answer = await ask(api.system.open_attachment, f"{MEDIA_PREFIX}1/42.pdf")

    assert "ok" in answer
    assert opened == [str(media / "1" / "42.pdf")]


async def test_an_attachment_outside_the_media_folder_is_not_opened(
    api, ask, opened, media, tmp_path
):
    """Путь, ведущий выше каталога медиа, наружу не выпускают.

    Адрес вложения приезжает от окна обратно, и приведи его кто-нибудь к
    «..» — открылся бы любой файл с диска.

    Файл по этому пути настоящий, читаемый и с безобидным расширением: не будь
    заслона, он бы и открылся. Лежит он вне каталога медиа нарочно — положенный
    внутрь, он сделал бы тест зелёным по ветке «такого файла нет».
    """
    (tmp_path / "секрет.pdf").write_bytes(b"%PDF-1.4")

    answer = await ask(api.system.open_attachment, f"{MEDIA_PREFIX}1/../../секрет.pdf")

    assert answer["fail"] == "denied"
    assert opened == []


async def test_a_missing_attachment_is_named_missing(api, ask, opened, media):
    """Вложения, которого нет на диске, не выдают за открытое.

    Скачивает бот не всё, а строка о письме остаётся: ответь мост «открыли»,
    человек ждал бы окна, которого не будет.
    """
    answer = await ask(api.system.open_attachment, f"{MEDIA_PREFIX}1/42.pdf")

    assert answer["fail"] == "denied"
    assert opened == []


def test_a_file_is_chosen_without_a_deprecated_dialog_name(caplog):
    """Диалог выбора файла открывается нынешним именем pywebview: устаревшее
    оставляет пометку в журнале на каждый выбор и уйдёт в следующей версии."""
    asked = []

    class Window:
        def create_file_dialog(self, kind, file_types=()):
            # Род диалога читается, как читает его настоящее окно: устаревшее
            # имя у pywebview ленивое и пишет пометку именно при чтении.
            asked.append((int(kind), file_types))
            return ["C:/резюме.pdf"]

    with caplog.at_level(logging.WARNING):
        chosen = chosen_path(Window(), "PDF (*.pdf)")

    assert chosen == "C:/резюме.pdf"
    assert asked == [(10, ("PDF (*.pdf)",))]
    assert "deprecated" not in caplog.text


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
