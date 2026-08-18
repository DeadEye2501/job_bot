"""Следствия сверки удалённого при догоне переписки.

Telegram не переигрывает пропущенные оповещения об удалении после
переподключения: строка, попавшая в вытянутое окно, но отсутствующая в ответе,
удалена, пока нас не было. Здесь проверяется само окно сверки.

Границ у окна две, и обе нужны. Ниже нижней лежит переписка, до которой хвост
не достал; выше верхней — письмо, пришедшее живым обработчиком, пока догон
читал. В ответе Telegram нет ни того, ни другого, и похоронить их значило бы
поставить надгробие поверх целого письма.
"""

from backend.models import Message
from tests.backend.fixtures.backfill import catch_up, catch_up_everyone, theirs
from tests.dbio import all_rows, only_row, put
from tests.factories import message_row
from tests.fakes.telegram import FakeTelegramClient


async def test_a_message_deleted_while_offline_is_tombstoned(
    known_hr, session_factory
):
    """Удалённое, пока приложение было закрыто, метится удалённым.

    Telegram оповещения об удалении после переподключения не
    переигрывает: строка, попавшая в вытянутое окно, но отсутствующая в
    ответе, — и есть удалённая.
    """
    await put(
        session_factory,
        message_row(
            hr_id=known_hr.id, is_incoming=True, tg_message_id=11, text="стёрли"
        ),
    )
    client = FakeTelegramClient()
    client.history = [theirs(12, "осталось"), theirs(10, "тоже осталось")]

    await catch_up(client, known_hr, session_factory)

    by_id = {m.tg_message_id: m for m in await all_rows(session_factory, Message)}
    assert by_id[11].is_deleted is True
    assert by_id[11].read_at is not None
    assert by_id[10].is_deleted is False


async def test_a_message_older_than_the_window_is_left_alone(
    known_hr, session_factory
):
    """Строка старше вытянутого окна удалённой не метится.

    Её в ответе нет просто потому, что окно до неё не достало, а не
    потому, что её стёрли.
    """
    await put(
        session_factory,
        message_row(
            hr_id=known_hr.id, is_incoming=True, tg_message_id=5, text="давнее"
        ),
    )
    client = FakeTelegramClient()
    client.history = [theirs(10, "свежее")]

    await catch_up(client, known_hr, session_factory)

    by_id = {m.tg_message_id: m for m in await all_rows(session_factory, Message)}
    assert by_id[5].is_deleted is False


async def test_the_newest_message_is_buried_when_it_stops_coming_back(
    known_hr, session_factory
):
    """Удалённое последнее письмо хоронится наравне с прочими.

    Верх хвоста — самое ходовое, что удаляют: HR стёр написанное минуту
    назад. Других путей у этой строки нет — пропущенных оповещений об
    удалении Telegram не переигрывает, — и не похорони её сверка,
    надгробия не поставит уже никто.
    """
    for number in (10, 11, 42):
        await put(
            session_factory,
            message_row(
                hr_id=known_hr.id, is_incoming=True, tg_message_id=number, text="было"
            ),
        )
    client = FakeTelegramClient()
    client.history = [theirs(11, "осталось"), theirs(10, "осталось")]

    await catch_up_everyone(client, session_factory)

    by_id = {m.tg_message_id: m for m in await all_rows(session_factory, Message)}
    assert by_id[42].is_deleted is True


class _WritesWhileReading(FakeTelegramClient):
    """Клиент, заводящий строку уже после того, как отдал хвост.

    Так выглядит письмо, пришедшее живым обработчиком, пока догон читал: в
    ответе Telegram его нет, потому что ответ собран раньше, а в базе оно
    появляется посреди прохода. Положи такую строку до прогона — и проверка
    стерегла бы соседний случай, удалённое последнее письмо.
    """

    def __init__(self, *, arrival, session_factory, **kwargs) -> None:
        super().__init__(**kwargs)
        self._arrival = arrival
        self.session_factory = session_factory

    async def get_chat_history(self, target, limit=100):
        async for msg in super().get_chat_history(target, limit):
            yield msg
        await put(self.session_factory, self._arrival)


async def test_a_message_that_arrived_mid_walk_is_left_alone(
    known_hr, session_factory
):
    """Письмо, пришедшее во время догона, удалённым не метится.

    Его номер больше всех вытянутых, и в ответе Telegram его нет по той же
    причине, по какой нет удалённого. Похорони его сверка — и в переписке
    появилось бы надгробие поверх только что пришедшего письма, да ещё и
    помеченное прочитанным.
    """
    await put(
        session_factory,
        message_row(
            hr_id=known_hr.id, is_incoming=True, tg_message_id=10, text="хвост"
        ),
    )
    client = _WritesWhileReading(
        arrival=message_row(
            hr_id=known_hr.id, is_incoming=True, tg_message_id=99, text="пришло сейчас"
        ),
        session_factory=session_factory,
    )
    client.history = [theirs(10, "хвост")]

    await catch_up_everyone(client, session_factory)

    by_id = {m.tg_message_id: m for m in await all_rows(session_factory, Message)}
    assert by_id[99].is_deleted is False
    assert by_id[99].read_at is None


async def test_an_empty_history_tombstones_nothing(known_hr, session_factory):
    """Пустой ответ Telegram ничего не метит удалённым.

    Пустым он бывает и когда переписка недоступна; принять это за
    удаление значило бы разом похоронить весь разговор.
    """
    await put(
        session_factory,
        message_row(
            hr_id=known_hr.id, is_incoming=True, tg_message_id=10, text="цело"
        ),
    )
    client = FakeTelegramClient()

    await catch_up(client, known_hr, session_factory)

    assert (await only_row(session_factory, Message)).is_deleted is False
