"""Следствия чтения переписки страницами.

Переписка листается вверх составным указателем «время и номер строки», а не
одним номером. Догоняющий разбор доливает старые сообщения после свежих, и
номер строки у более старого по времени сообщения оказывается больше — чистое
листание по номеру тогда либо пропускает строки, либо показывает их дважды.
"""

from backend.repository import list_messages_for_hr
from tests.dbio import put
from tests.factories import at, hr_row, message_row


async def texts(session, hr_id, **kwargs) -> tuple[list[str], bool]:
    """Тексты страницы переписки и признак «есть ещё старее»."""
    rows, has_more = await list_messages_for_hr(session, hr_id, **kwargs)
    return [m.text for m in rows], has_more


async def test_the_chat_reads_oldest_first_from_the_tail(session, session_factory):
    """Переписка отдаётся от старого к новому, начиная с хвоста разговора.

    Экран показывает разговор сверху вниз, а грузит его с конца — поэтому
    выбирается самое новое, а отдаётся перевёрнутым.
    """
    hr = hr_row()
    await put(session_factory, hr)
    await put(
        session_factory,
        message_row(hr_id=hr.id, text="второе", sent_at=at(20)),
        message_row(hr_id=hr.id, text="первое", sent_at=at(10)),
        message_row(hr_id=hr.id, text="третье", sent_at=at(30)),
    )

    got, has_more = await texts(session, hr.id)

    assert got == ["первое", "второе", "третье"]
    assert has_more is False


async def test_messages_of_the_same_moment_keep_the_order_they_arrived(
    session, session_factory
):
    """Два сообщения одной секунды показываются в порядке появления.

    Времена приходят от Telegram с точностью до секунды, и переписка в
    несколько реплик подряд легко получает одно значение на всех. Без
    разрешителя по номеру строки порядок задавала бы база, и реплики
    менялись бы местами от загрузки к загрузке.

    Проверено мутацией: набор для указателя эту ветку не задевал — там
    разрешитель работает в условии отбора, а не в порядке выдачи.
    """
    hr = hr_row()
    await put(session_factory, hr)
    await put(
        session_factory,
        message_row(hr_id=hr.id, text="сначала", sent_at=at(20)),
        message_row(hr_id=hr.id, text="потом", sent_at=at(20)),
        message_row(hr_id=hr.id, text="раньше всех", sent_at=at(10)),
    )

    got, _ = await texts(session, hr.id)

    assert got == ["раньше всех", "сначала", "потом"]


async def test_a_full_page_reports_that_there_is_more(session, session_factory):
    """Полная страница сообщает, что старее ещё есть."""
    hr = hr_row()
    await put(session_factory, hr)
    await put(
        session_factory,
        *[
            message_row(hr_id=hr.id, text=f"сообщение {n}", sent_at=at(n))
            for n in (30, 10, 20)
        ],
    )

    got, has_more = await texts(session, hr.id, limit=2)

    assert got == ["сообщение 20", "сообщение 30"]
    assert has_more is True


async def test_the_last_page_reports_that_there_is_nothing_older(
    session, session_factory
):
    """Последняя страница сообщает, что старее уже ничего нет."""
    hr = hr_row()
    await put(session_factory, hr)
    await put(
        session_factory,
        message_row(hr_id=hr.id, text="одно", sent_at=at(10)),
        message_row(hr_id=hr.id, text="другое", sent_at=at(20)),
    )

    got, has_more = await texts(session, hr.id, limit=2)

    assert got == ["одно", "другое"]
    assert has_more is False


async def test_the_cursor_moves_strictly_older(session, session_factory):
    """Указатель отдаёт строго то, что старее его самого."""
    hr = hr_row()
    await put(session_factory, hr)
    older = message_row(hr_id=hr.id, text="старое", sent_at=at(10))
    edge = message_row(hr_id=hr.id, text="край", sent_at=at(20))
    newer = message_row(hr_id=hr.id, text="новое", sent_at=at(30))
    await put(session_factory, older, edge, newer)

    got, _ = await texts(
        session, hr.id, before_id=edge.id, before_sent_at=edge.sent_at
    )

    assert got == ["старое"]


async def test_two_messages_of_the_same_moment_are_split_by_row_number(
    session, session_factory
):
    """Два сообщения одного момента разделяются номером строки.

    Времена приходят от Telegram с точностью до секунды, и два сообщения
    подряд легко получают одно значение. Без второй половины указателя одно
    из них выпало бы или показалось дважды.
    """
    hr = hr_row()
    await put(session_factory, hr)
    first = message_row(hr_id=hr.id, text="первое той же секунды", sent_at=at(20))
    second = message_row(hr_id=hr.id, text="второе той же секунды", sent_at=at(20))
    await put(session_factory, first, second)

    got, _ = await texts(
        session, hr.id, before_id=second.id, before_sent_at=second.sent_at
    )

    assert got == ["первое той же секунды"]


async def test_an_older_message_with_a_higher_row_number_is_not_skipped(
    session, session_factory
):
    """Старое сообщение с большим номером строки не пропускается.

    Так выглядит догоняющий разбор: свежие сообщения уже сохранены, а
    исторические доливаются после них и получают номера выше. Листание по
    одному номеру потеряло бы их все.
    """
    hr = hr_row()
    await put(session_factory, hr)
    shown = message_row(hr_id=hr.id, text="уже показано", sent_at=at(30))
    await put(session_factory, shown)
    backfilled = message_row(hr_id=hr.id, text="долито разбором", sent_at=at(10))
    await put(session_factory, backfilled)

    assert backfilled.id > shown.id

    got, _ = await texts(
        session, hr.id, before_id=shown.id, before_sent_at=shown.sent_at
    )

    assert got == ["долито разбором"]


async def test_a_cursor_without_a_time_falls_back_to_the_row_number(
    session, session_factory
):
    """Указатель без времени работает по одному номеру строки.

    Так ведут себя старые сборки экрана, не присылающие время. Поведение
    оставлено ради них, и именно на нём видна беда, ради которой указатель
    стал составным: долитое разбором старое сообщение с большим номером в
    выдачу не попадает.
    """
    hr = hr_row()
    await put(session_factory, hr)
    shown = message_row(hr_id=hr.id, text="уже показано", sent_at=at(30))
    await put(session_factory, shown)
    backfilled = message_row(hr_id=hr.id, text="долито разбором", sent_at=at(10))
    await put(session_factory, backfilled)

    got, _ = await texts(session, hr.id, before_id=shown.id)

    assert got == []


async def test_a_time_without_a_row_number_moves_nothing(session, session_factory):
    """Время без номера строки указателем не считается — отдаётся вся переписка.

    Половинчатый указатель отсекать нечем: сравнение по паре требует обеих
    её частей, а запасной путь по одному номеру без номера не работает.
    Экран такого не шлёт, и ветка существует лишь как следствие устройства
    охраны. Тест закрепляет сегодняшнее поведение.
    """
    hr = hr_row()
    await put(session_factory, hr)
    older = message_row(hr_id=hr.id, text="старое", sent_at=at(10))
    edge = message_row(hr_id=hr.id, text="край", sent_at=at(20))
    await put(session_factory, older, edge)

    got, _ = await texts(session, hr.id, before_sent_at=edge.sent_at)

    assert got == ["старое", "край"]


async def test_a_neighbouring_chat_stays_out(session, session_factory):
    """Чужая переписка в выдачу не попадает."""
    mine = hr_row(name="Анна")
    other = hr_row(name="Борис")
    await put(session_factory, mine, other)
    await put(
        session_factory,
        message_row(hr_id=mine.id, text="моё", sent_at=at(10)),
        message_row(hr_id=other.id, text="чужое", sent_at=at(20)),
    )

    got, _ = await texts(session, mine.id)

    assert got == ["моё"]
