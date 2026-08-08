"""Кого бот слушает во входящих личных сообщениях, а кого нет.

В личку пишут не только HR: боты, знакомые, рассылки. Сохранять всё подряд
значило бы завалить вкладку «Контакты» посторонним, поэтому пишется только то,
что пришло от уже заведённого HR.

Первое письмо от HR ещё и дописывает его карточку: до него строка может знать
одно лишь имя, а номер собеседника узнаётся ровно в этот миг. Заодно
подтягивается аватар — но только если своего у карточки ещё нет.
"""

import pytest

from backend.flows import process_dm
from backend.models import HR, Message
from tests.dbio import all_rows, only_row, put
from tests.factories import blacklist_row, hr_row, message_row
from tests.fakes.telegram import SENT_AT, FakeTelegramClient, message, photo, user


def _incoming(
    *, user_id=777, username=None, is_bot=False, msg_id=10, avatar=None, **extra
):
    """Входящее сообщение от собеседника."""
    return message(
        id=msg_id,
        text="здравствуйте",
        date=SENT_AT,
        from_user=user(
            id=user_id,
            username=username,
            is_bot=is_bot,
            photo=photo(small_file_id=avatar) if avatar else None,
        ),
        photo=None,
        document=None,
        **extra,
    )


async def _deliver(session_factory, msg, client=None):
    """Проводит сообщение через разбор входящего."""
    await process_dm(msg, None, "qwen", session_factory, client=client)


async def test_a_letter_from_a_known_hr_is_saved(session_factory):
    """Письмо от заведённого HR сохраняется в переписку."""
    await put(session_factory, hr_row(telegram_user_id=777))
    hr = await only_row(session_factory, HR)

    await _deliver(session_factory, _incoming())

    saved = await only_row(session_factory, Message)
    assert saved.hr_id == hr.id
    assert saved.is_incoming is True
    assert saved.text == "здравствуйте"
    assert saved.tg_message_id == 10
    assert saved.sent_at == SENT_AT


@pytest.mark.parametrize(
    "msg",
    [
        pytest.param(message(text="ниоткуда", from_user=None), id="без отправителя"),
        pytest.param(_incoming(is_bot=True), id="от бота"),
    ],
)
async def test_a_letter_nobody_could_have_written_is_ignored(session_factory, msg):
    """Письмо, которого не писал человек, не сохраняется.

    Отправителя не бывает у служебных записей, а боты пишут рассылками —
    ни то ни другое в переписку с HR не относится.
    """
    await put(session_factory, hr_row(telegram_user_id=777))

    await _deliver(session_factory, msg)

    assert await all_rows(session_factory, Message) == []


async def test_a_letter_from_a_stranger_is_not_saved(session_factory):
    """Письмо от незаведённого собеседника не сохраняется.

    В личку пишут знакомые и рассылки; складывать их в «Контакты»
    значило бы завалить вкладку посторонним.
    """
    await put(session_factory, hr_row(telegram_user_id=777))

    await _deliver(session_factory, _incoming(user_id=999))

    assert await all_rows(session_factory, Message) == []


async def test_a_letter_from_a_blacklisted_hr_is_dropped(session_factory):
    """Письмо от HR из чёрного списка не сохраняется вовсе.

    Переписка с ним глохнет в обе стороны: исходящее уже заперто, и
    входящее тоже не должно ни попадать в ленту, ни двигать статусы.
    """
    await put(
        session_factory,
        hr_row(telegram_user_id=777, telegram_username="maria"),
        blacklist_row("hr", "@maria"),
    )

    await _deliver(session_factory, _incoming())

    assert await all_rows(session_factory, Message) == []


async def test_the_first_letter_pins_the_correspondent_number(session_factory):
    """Первое письмо дописывает в карточку номер собеседника.

    Карточку заводят по имени из окна «Контакты», а номер узнаётся
    только когда HR напишет сам. С ним последующий поиск идёт по прямому
    попаданию, а не по имени, которое собеседник волен сменить.
    """
    await put(session_factory, hr_row(telegram_username="maria", telegram_user_id=None))

    await _deliver(session_factory, _incoming(username="maria"))

    assert (await only_row(session_factory, HR)).telegram_user_id == 777


async def test_a_renamed_correspondent_is_renamed_in_the_card(session_factory):
    """Сменивший имя собеседник переименовывается и в карточке.

    Иначе в окне остаётся имя, по которому его больше не найти.
    """
    await put(session_factory, hr_row(telegram_user_id=777, telegram_username="maria"))

    await _deliver(session_factory, _incoming(username="maria_hr"))

    assert (await only_row(session_factory, HR)).telegram_username == "maria_hr"


async def test_a_card_without_a_picture_gets_one(session_factory):
    """Карточке без картинки подтягивается аватар собеседника."""
    await put(session_factory, hr_row(telegram_user_id=777, avatar=None))
    client = FakeTelegramClient(avatar=b"\x89PNG")

    await _deliver(
        session_factory,
        _incoming(avatar="кар"),
        client=client,
    )

    assert (await only_row(session_factory, HR)).avatar == b"\x89PNG"


async def test_a_card_that_already_has_a_picture_keeps_it(session_factory):
    """Карточка со своей картинкой чужую не берёт.

    Пользователь мог поставить её руками; перетирать её на каждом письме
    значило бы отменять его выбор.
    """
    await put(session_factory, hr_row(telegram_user_id=777, avatar=b"\x89OWN"))
    client = FakeTelegramClient(avatar=b"\x89PNG")

    await _deliver(
        session_factory,
        _incoming(avatar="кар"),
        client=client,
    )

    assert (await only_row(session_factory, HR)).avatar == b"\x89OWN"
    assert client.download_calls == []


async def test_a_duplicate_letter_is_not_saved_twice(session_factory):
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

    await _deliver(session_factory, _incoming())

    assert (await only_row(session_factory, Message)).text == "уже было"
