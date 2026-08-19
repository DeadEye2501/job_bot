"""Кого бот слушает во входящих личных сообщениях, а кого нет.

В личку пишут не только HR: боты, знакомые, рассылки. Сохранять всё подряд
значило бы завалить вкладку «Контакты» посторонним, поэтому пишется только то,
что пришло от уже заведённого HR.

Первое письмо от HR ещё и дописывает его карточку: до него строка может знать
один лишь ник, а номер собеседника узнаётся ровно в этот миг. Заодно
подтягиваются имя и аватар — но только в пустое место: записанное руками в окне
точнее того, как собеседник назвался сам.
"""

import pytest

from backend.bot.media import MEDIA_DIR
from backend.models import HR, Message
from tests.dbio import all_rows, only_row, put
from tests.factories import EPOCH, blacklist_row, hr_row, message_row
from tests.fakes.telegram import (
    FakeTelegramClient,
    incoming,
    message,
    photo,
    user,
)


async def test_a_letter_from_a_known_hr_is_saved(session_factory, deliver):
    """Письмо от заведённого HR сохраняется в переписку."""
    await put(session_factory, hr_row(telegram_user_id=777))
    hr = await only_row(session_factory, HR)

    await deliver(incoming())

    saved = await only_row(session_factory, Message)
    assert saved.hr_id == hr.id
    assert saved.is_incoming is True
    assert saved.text == "здравствуйте"
    assert saved.tg_message_id == 10
    assert saved.sent_at == EPOCH


@pytest.mark.parametrize(
    "msg",
    [
        pytest.param(message(text="ниоткуда", from_user=None), id="без отправителя"),
        pytest.param(
            incoming(from_user=user(id=777, is_bot=True)), id="от бота"
        ),
    ],
)
async def test_a_letter_nobody_could_have_written_is_ignored(session_factory, deliver, msg):
    """Письмо, которого не писал человек, не сохраняется.

    Отправителя не бывает у служебных записей, а боты пишут рассылками —
    ни то ни другое в переписку с HR не относится.
    """
    await put(session_factory, hr_row(telegram_user_id=777))

    await deliver(msg)

    assert await all_rows(session_factory, Message) == []


async def test_the_taken_letter_names_its_correspondent(session_factory, deliver):
    """Принятое письмо называет собеседника, чьё оно.

    По этому номеру окно узнаёт, какую переписку перерисовать. Спрашивать его
    второй раз, уже в слое оповещений, значило бы завести там свою сессию —
    а обработчик оповещений отстреливает на каждое событие сервера.
    """
    await put(session_factory, hr_row(telegram_user_id=777))
    hr = await only_row(session_factory, HR)

    assert await deliver(incoming()) == hr.id


async def test_a_letter_nobody_writes_back_to_names_nobody(session_factory, deliver):
    """Письмо незнакомца собеседника не называет: окну говорить не о чем."""
    await put(session_factory, hr_row(telegram_user_id=777))

    assert await deliver(incoming(user_id=999)) is None


async def test_a_letter_from_a_stranger_is_not_saved(session_factory, deliver):
    """Письмо от незаведённого собеседника не сохраняется.

    В личку пишут знакомые и рассылки; складывать их в «Контакты»
    значило бы завалить вкладку посторонним.
    """
    await put(session_factory, hr_row(telegram_user_id=777))

    await deliver(incoming(user_id=999))

    assert await all_rows(session_factory, Message) == []


async def test_a_letter_from_a_blacklisted_hr_is_dropped(session_factory, deliver):
    """Письмо от HR из чёрного списка не сохраняется вовсе.

    Переписка с ним глохнет в обе стороны: исходящее уже заперто, и
    входящее тоже не должно ни попадать в ленту, ни двигать статусы.
    """
    await put(
        session_factory,
        hr_row(telegram_user_id=777, telegram_username="maria"),
        blacklist_row("hr", "@maria"),
    )

    await deliver(incoming())

    assert await all_rows(session_factory, Message) == []


async def test_the_first_letter_pins_the_correspondent_number(session_factory, deliver):
    """Первое письмо дописывает в карточку номер собеседника.

    Карточку заводят по имени из окна «Контакты», а номер узнаётся
    только когда HR напишет сам. С ним последующий поиск идёт по прямому
    попаданию, а не по имени, которое собеседник волен сменить.
    """
    await put(session_factory, hr_row(telegram_username="maria", telegram_user_id=None))

    await deliver(incoming(username="maria"))

    assert (await only_row(session_factory, HR)).telegram_user_id == 777


async def test_a_renamed_correspondent_is_renamed_in_the_card(session_factory, deliver):
    """Сменивший имя собеседник переименовывается и в карточке.

    Иначе в окне остаётся имя, по которому его больше не найти.
    """
    await put(session_factory, hr_row(telegram_user_id=777, telegram_username="maria"))

    await deliver(incoming(username="maria_hr"))

    assert (await only_row(session_factory, HR)).telegram_username == "maria_hr"


async def test_a_card_without_a_name_gets_the_one_from_telegram(
    session_factory, deliver
):
    """Карточке без имени первое письмо дописывает имя собеседника.

    Карточку заводят одним ником из окна «Контакты», и до первого письма
    показать в ней некого: в списке она стоит пустой строкой. Имя приходит
    в том же сообщении, что и номер собеседника.
    """
    await put(session_factory, hr_row(name=None, telegram_user_id=777))

    await deliver(
        incoming(from_user=user(id=777, first_name="Мария", last_name="Ким"))
    )

    assert (await only_row(session_factory, HR)).name == "Мария Ким"


async def test_a_card_with_a_name_keeps_it(session_factory, deliver):
    """Своё имя карточки письмо не перебивает.

    Имя правят руками в окне, и оно точнее того, как собеседник назвался
    в Telegram.
    """
    await put(session_factory, hr_row(name="Мария из Контура", telegram_user_id=777))

    await deliver(
        incoming(from_user=user(id=777, first_name="Мария", last_name="Ким"))
    )

    assert (await only_row(session_factory, HR)).name == "Мария из Контура"


async def test_a_card_without_a_picture_gets_one(session_factory, deliver):
    """Карточке без картинки подтягивается аватар собеседника."""
    await put(session_factory, hr_row(telegram_user_id=777, avatar=None))
    client = FakeTelegramClient(avatar=b"\x89PNG")

    await deliver(
        incoming(from_user=user(id=777, photo=photo(small_file_id="кар"))),
        client=client,
    )

    assert (await only_row(session_factory, HR)).avatar == b"\x89PNG"


async def test_a_picture_that_would_not_come_does_not_cost_the_letter(
    session_factory, deliver, monkeypatch
):
    """Сорвавшаяся картинка письма не уносит.

    Картинка — украшение карточки, а письмо — то, ради чего всё. Своей
    сделкой она идёт уже после того, как строка легла, и её беда не должна
    ни отменять записанное, ни мешать разбору: догон гоняет два десятка
    переписок разом, и запертая на запись база там обычное дело.
    """
    await put(session_factory, hr_row(telegram_user_id=777, avatar=None))
    client = FakeTelegramClient(avatar=b"PNG")

    async def refuses(*_args):
        raise RuntimeError("база занята")

    monkeypatch.setattr("backend.flows.dm.fetch_telegram_avatar", refuses)

    got = await deliver(
        incoming(from_user=user(id=777, photo=photo(small_file_id="кар"))),
        client=client,
    )

    assert got is not None
    assert (await only_row(session_factory, Message)).tg_message_id == 10


async def test_a_letter_already_in_the_chat_costs_no_picture(
    session_factory, deliver
):
    """За уже лежащее письмо картинкой собеседника не платят.

    Догон приносит переписку целиком, и почти вся она уже лежит. Пока
    картинку спрашивали до записи, за неё платили на каждом старом письме и
    тут же выбрасывали откатом: строка не легла — не легла и картинка.
    """
    await put(session_factory, hr_row(telegram_user_id=777, avatar=None))
    hr = await only_row(session_factory, HR)
    await put(
        session_factory,
        message_row(hr_id=hr.id, is_incoming=True, tg_message_id=10),
    )
    client = FakeTelegramClient(avatar=b"\x89PNG")

    await deliver(
        incoming(id=10, from_user=user(id=777, photo=photo(small_file_id="кар"))),
        client=client,
    )

    assert client.download_calls == []


async def test_a_picture_that_arrived_while_downloading_is_not_overwritten(
    session_factory, deliver
):
    """Картинка, появившаяся пока шло скачивание, чужой не затирается.

    Между чтением карточки и записью проходит время скачивания, и за него
    карточку мог заполнить сосед: разбор второго сообщения от того же
    собеседника или опознание HR, которое тоже кладёт аватар. Поэтому
    «картинки ещё нет» проверяется дважды: до скачивания и перед записью.
    """
    hr = hr_row(telegram_user_id=777, avatar=None)
    await put(session_factory, hr)
    client = FakeTelegramClient(avatar=b"\x89PNG")

    async def fill_it_meanwhile(_file_name):
        async with session_factory() as other:
            row = await other.get(HR, hr.id)
            row.avatar = b"\x89OWN"
            await other.commit()

    client.on_download = fill_it_meanwhile

    await deliver(
        incoming(from_user=user(id=777, photo=photo(small_file_id="кар"))),
        client=client,
    )

    assert (await only_row(session_factory, HR)).avatar == b"\x89OWN"


async def test_a_card_that_already_has_a_picture_keeps_it(session_factory, deliver):
    """Карточка со своей картинкой чужую не берёт.

    Пользователь мог поставить её руками; перетирать её на каждом письме
    значило бы отменять его выбор.
    """
    await put(session_factory, hr_row(telegram_user_id=777, avatar=b"\x89OWN"))
    client = FakeTelegramClient(avatar=b"\x89PNG")

    await deliver(
        incoming(from_user=user(id=777, photo=photo(small_file_id="кар"))),
        client=client,
    )

    assert (await only_row(session_factory, HR)).avatar == b"\x89OWN"
    assert client.download_calls == []


async def test_a_duplicate_letter_is_not_saved_twice(session_factory, deliver):
    """То же письмо второй раз в переписку не попадает.

    Живой обработчик и догон пропущенного приходят к одному сообщению;
    два одинаковых пузыря пользователь заметит сразу.
    """
    await put(session_factory, hr_row(telegram_user_id=777))
    hr = await only_row(session_factory, HR)
    await put(
        session_factory,
        message_row(hr_id=hr.id, is_incoming=True, tg_message_id=10, text="уже было"),
    )

    await deliver(incoming())

    assert (await only_row(session_factory, Message)).text == "уже было"


async def test_a_letter_survives_a_file_where_the_media_folder_belongs(
    session_factory, deliver
):
    """Письмо с вложением доходит до переписки, даже если место занято.

    Если по пути `media/<hr_id>` лежит файл, а не папка, скачать вложение
    некуда. Само письмо от этого пропасть не должно: текст и отправитель
    известны и без файла, а потерянное входящее не восстановить ничем.
    """
    await put(session_factory, hr_row(telegram_user_id=777))
    hr = await only_row(session_factory, HR)
    MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    (MEDIA_DIR / str(hr.id)).write_bytes(b"")

    await deliver(incoming(photo=photo()), client=FakeTelegramClient())

    saved = await only_row(session_factory, Message)
    assert saved.media_kind == "photo"
    assert saved.media_path is None
    assert saved.text == "здравствуйте"


async def test_a_stranger_costs_nothing_to_ignore(session_factory, deliver):
    """Вложение от незаведённого собеседника даже не скачивается.

    Отсев стоит раньше загрузки нарочно: рассылки приходят с картинками,
    и качать их с серверов Telegram ради того, чтобы тут же выбросить, —
    трафик и место на диске впустую.
    """
    await put(session_factory, hr_row(telegram_user_id=777))
    client = FakeTelegramClient()

    await deliver(incoming(user_id=999, photo=object()), client=client)

    assert client.download_calls == []
    assert await all_rows(session_factory, Message) == []
