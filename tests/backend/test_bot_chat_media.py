"""Следствия отправки файла HR из вкладки «Контакты».

Способ отправки выбирается по виду файла: три расширения уходят картинкой,
всё прочее — документом. От выбора зависит и предел размера, и то, запомнится
ли имя файла: у картинки его не показывают.

Ушедший файл копируется в свою папку под тем же именем, какое дал бы ему
обработчик входящих. Так встречная загрузка находит его готовым и не тянет
с серверов Telegram то, что и так лежит на диске.

Отказы совпадают с теми, что у обычного сообщения, — здесь проверено, что
они и правда те же, а не разошлись между двумя путями отправки.
"""

import pytest

from backend.bot.media import MEDIA_DIR
from backend.models import BotMode, Message
from tests.dbio import only_row, put
from tests.factories import blacklist_row, message_row
from tests.fakes.telegram import SENT_AT


def _file(tmp_path, name: str, size: int = 4):
    """Файл заданного имени и размера."""
    path = tmp_path / name
    path.write_bytes(b"\0" * size)
    return path


async def test_a_picture_goes_as_a_photo(
    chatting, session_factory, sending_unlocked, tmp_path
):
    """Картинка уходит картинкой, и имя файла у неё не запоминается.

    В переписке у картинки показывают её саму, а не подпись с именем.
    """
    bot, client, hr = await chatting()
    src = _file(tmp_path, "снимок.png")

    row = await bot.send_to_hr_media(hr.id, str(src))

    assert client.outgoing == [("send_photo", "maria", str(src))]
    assert row.media_kind == "photo"
    assert row.media_name is None
    assert row.text == ""
    assert row.sent_at == SENT_AT


async def test_anything_else_goes_as_a_document_under_its_name(
    chatting, session_factory, sending_unlocked, tmp_path
):
    """Прочее уходит документом, и его имя запоминается для переписки."""
    bot, client, hr = await chatting()
    src = _file(tmp_path, "Резюме.pdf")

    row = await bot.send_to_hr_media(hr.id, str(src))

    assert client.outgoing == [("send_document", "maria", str(src))]
    assert row.media_kind == "document"
    assert row.media_name == "Резюме.pdf"


@pytest.mark.parametrize(
    ("name", "ext"),
    [
        pytest.param("снимок.png", ".jpg", id="картинка"),
        pytest.param("Резюме.pdf", ".pdf", id="документ"),
    ],
)
async def test_the_sent_file_lands_in_the_media_folder(
    chatting, sending_unlocked, tmp_path, name, ext
):
    """Ушедший файл ложится в папку вложений под ожидаемым именем.

    Встречная загрузка того же сообщения вычисляет этот путь сама и,
    найдя файл, не тянет его с серверов Telegram заново.
    """
    bot, client, hr = await chatting()
    src = _file(tmp_path, name)

    row = await bot.send_to_hr_media(hr.id, str(src))

    copied = MEDIA_DIR / str(hr.id) / f"{client.last_message_id}{ext}"
    assert copied.exists()
    assert row.media_path == f"{hr.id}/{client.last_message_id}{ext}"


async def test_a_failed_copy_does_not_lose_the_message(
    chatting, sending_unlocked, tmp_path
):
    """Неудачная копия сообщение не теряет: файл в Telegram уже ушёл.

    В переписке он покажется без предпросмотра — это хуже, чем с ним, но
    несравнимо лучше, чем строка, пропавшая целиком.
    """
    bot, client, hr = await chatting()
    src = _file(tmp_path, "снимок.png")

    async def vanishes(answer):
        src.unlink()

    client.on_send = vanishes

    row = await bot.send_to_hr_media(hr.id, str(src))

    assert row.media_kind == "photo"
    assert row.media_path is None


async def test_a_file_where_the_folder_belongs_loses_the_sent_message(
    chatting, sending_unlocked, tmp_path
):
    """Файл на месте папки вложений теряет уже отправленное сообщение.

    Создание папки стоит снаружи разбора ошибок, и его сбой пробивает
    наружу необработанным: файл у HR уже есть, а строки в переписке нет
    и не будет — окно покажет ошибку, будто отправка не состоялась.

    Тест закрепляет сегодняшнее поведение: при починке он покраснеет.
    """
    bot, client, hr = await chatting()
    src = _file(tmp_path, "снимок.png")
    MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    (MEDIA_DIR / str(hr.id)).write_bytes(b"")

    with pytest.raises(FileExistsError):
        await bot.send_to_hr_media(hr.id, str(src))

    assert client.outgoing == [("send_photo", "maria", str(src))]


@pytest.mark.parametrize(
    ("name", "limit_mb"),
    [
        pytest.param("снимок.png", 10, id="картинка"),
        pytest.param("Резюме.pdf", 50, id="документ"),
    ],
)
async def test_an_oversized_file_is_refused_before_sending(
    chatting, sending_unlocked, tmp_path, name, limit_mb
):
    """Слишком большой файл отклоняется до отправки, с названным пределом.

    Пределы у картинки и документа разные; Telegram отказал бы сам, но
    после долгой заливки и без внятного объяснения.
    """
    bot, client, hr = await chatting()
    src = _file(tmp_path, name, size=limit_mb * 1024 * 1024 + 1)

    with pytest.raises(RuntimeError, match=f"лимит {limit_mb} MB"):
        await bot.send_to_hr_media(hr.id, str(src))

    assert client.outgoing == []


async def test_a_file_at_the_limit_still_goes(
    chatting, session_factory, sending_unlocked, tmp_path
):
    """Файл ровно по пределу ещё уходит: предел включительный."""
    bot, client, hr = await chatting()
    src = _file(tmp_path, "снимок.png", size=10 * 1024 * 1024)

    await bot.send_to_hr_media(hr.id, str(src))

    assert client.outgoing == [("send_photo", "maria", str(src))]


@pytest.mark.parametrize(
    "name",
    [pytest.param("нет.pdf", id="файла нет"), pytest.param("", id="это папка")],
)
async def test_a_path_that_is_not_a_file_is_refused(
    chatting, session_factory, sending_unlocked, tmp_path, name
):
    """Путь, за которым нет файла, отклоняется с указанием пути."""
    bot, client, hr = await chatting()
    target = tmp_path / name

    with pytest.raises(RuntimeError, match="Файл не найден"):
        await bot.send_to_hr_media(hr.id, str(target))

    assert client.outgoing == []


async def test_a_switched_off_bot_sends_no_files(
    chatting, session_factory, tmp_path
):
    """Выключенный бот файлов не шлёт — так же, как и сообщений."""
    bot, client, hr = await chatting(mode=BotMode.OFF)
    src = _file(tmp_path, "снимок.png")

    with pytest.raises(RuntimeError, match="Бот выключен"):
        await bot.send_to_hr_media(hr.id, str(src))

    assert client.outgoing == []


async def test_the_send_guard_stops_files_too(chatting, session_factory, tmp_path):
    """Защита от случайной отправки останавливает и файлы."""
    bot, client, hr = await chatting()
    src = _file(tmp_path, "снимок.png")

    with pytest.raises(RuntimeError, match="защита от случайной отправки"):
        await bot.send_to_hr_media(hr.id, str(src))

    assert client.outgoing == []


async def test_a_blacklisted_hr_gets_no_files_either(
    chatting, session_factory, sending_unlocked, tmp_path
):
    """HR из чёрного списка файла не получает, и запись названа в отказе."""
    await put(session_factory, blacklist_row("hr", "@maria"))
    bot, client, hr = await chatting()
    src = _file(tmp_path, "снимок.png")

    with pytest.raises(RuntimeError, match="@maria"):
        await bot.send_to_hr_media(hr.id, str(src))

    assert client.outgoing == []


async def test_an_hr_without_an_address_gets_no_files_either(
    chatting, session_factory, sending_unlocked, tmp_path
):
    """HR без адреса файла не получает: отправлять некуда."""
    bot, client, hr = await chatting(
        telegram_username=None, telegram_user_id=None
    )
    src = _file(tmp_path, "снимок.png")

    with pytest.raises(RuntimeError, match="нечем отправить"):
        await bot.send_to_hr_media(hr.id, str(src))

    assert client.outgoing == []


async def test_a_missing_hr_gets_no_files_either(
    chatting, session_factory, sending_unlocked, tmp_path
):
    """Отказ по несуществующему HR называет, кого не нашли."""
    bot, client, _ = await chatting()
    src = _file(tmp_path, "снимок.png")

    with pytest.raises(RuntimeError, match="id=404"):
        await bot.send_to_hr_media(404, str(src))

    assert client.outgoing == []


async def test_a_file_the_handler_already_saved_is_not_doubled(
    chatting, session_factory, sending_unlocked, tmp_path
):
    """Файл, который успел сохранить обработчик, не удваивается в переписке."""
    bot, client, hr = await chatting()
    src = _file(tmp_path, "снимок.png")

    async def saved_by_the_handler(answer):
        await put(
            session_factory,
            message_row(
                hr_id=hr.id,
                is_incoming=False,
                tg_message_id=answer.id,
                text="сохранено обработчиком",
            ),
        )

    client.on_send = saved_by_the_handler

    row = await bot.send_to_hr_media(hr.id, str(src))

    assert row.text == "сохранено обработчиком"
    assert (await only_row(session_factory, Message)).id == row.id
