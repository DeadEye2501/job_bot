"""Следствия таблицы «каналы»: что канал прислал и сколько из этого мусор.

Мусор считается из двух мест, и это не прихоть: при обычном разборе такой пост
удаляется из вакансий целиком, и след от него остаётся отдельной отметкой, а
при повторном разборе строка сохраняется с пометкой в причине отказа.

Воронка того же канала и доли по ней — предмет соседа,
`test_repository_stats_funnel.py`: он про то, что с присланным стало дальше.
"""

from backend.domain.verdict import EMPTY_SKIP_REASON
from backend.models import TrashEvent, VacancyStatus
from backend.repository.stats_pipeline import get_stats_channels_pipeline
from tests.backend.fixtures.stats import rows_by_channel
from tests.dbio import put
from tests.factories import channel_row, days_ago, status_history_row, vacancy_row


async def test_an_empty_database_gives_no_rows(session):
    """На пустой базе таблица пуста."""
    got = await get_stats_channels_pipeline(session, period="all")

    assert got == {"period": "all", "channels": []}


async def test_a_channel_that_never_sent_anything_is_absent(
    session, session_factory
):
    """Канал, от которого не было ничего никогда, в таблицу не попадает."""
    silent = channel_row(username="silent", title="Молчит")
    active = channel_row(username="active", title="Работает")
    await put(session_factory, silent, active)
    await put(session_factory, vacancy_row(source_channel_id=active.id))

    assert list(await rows_by_channel(session, period="all")) == [active.id]


async def test_a_channel_silent_within_the_window_drops_out_of_it(
    session, session_factory
):
    """Канал, молчавший в окне, из таблицы за период выпадает.

    Это не то же, что «не присылал никогда»: строки у него есть, и за всё
    время он в таблице стоит. Проверено ревью: прежняя проверка звалась про
    окно, а звала таблицу за всё время и потому окна не касалась вовсе.
    """
    stale = channel_row(username="stale", title="Замолчал")
    fresh = channel_row(username="fresh", title="Пишет")
    await put(session_factory, stale, fresh)
    await put(
        session_factory,
        vacancy_row(source_channel_id=stale.id, created_at=days_ago(40)),
        vacancy_row(source_channel_id=fresh.id, created_at=days_ago(1)),
    )

    assert list(await rows_by_channel(session, period="week")) == [fresh.id]
    assert set(await rows_by_channel(session, period="all")) == {stale.id, fresh.id}





async def test_a_row_carries_what_the_window_names_the_channel_by(
    session, session_factory
):
    """Строка несёт название и ник канала как есть: подпись собирает окно
    тем же правилом, что в Контактах, куда таблица ведёт по нажатию."""
    channel = channel_row(username="ch", title="Канал")
    await put(session_factory, channel)
    await put(session_factory, vacancy_row(source_channel_id=channel.id), vacancy_row())

    rows = await rows_by_channel(session, period="all")

    assert (rows[channel.id]["title"], rows[channel.id]["username"]) == ("Канал", "ch")
    assert (rows[None]["title"], rows[None]["username"]) == (None, None)

async def test_the_deleted_junk_counts_towards_what_the_channel_sent(
    session, session_factory
):
    """Удалённый при разборе мусор всё равно считается присланным.

    Иначе канал, чьи посты почти все отсеиваются, выглядел бы тихим и
    аккуратным: строки-то из вакансий пропали.
    """
    channel = channel_row(username="noisy", title="Шумный")
    await put(session_factory, channel)
    await put(
        session_factory,
        vacancy_row(source_channel_id=channel.id),
        TrashEvent(source_channel_id=channel.id, source_msg_id=1, reason="реклама"),
        TrashEvent(source_channel_id=channel.id, source_msg_id=2, reason="реклама"),
    )

    row = (await rows_by_channel(session, period="all"))[channel.id]

    assert row["total"] == 3
    assert row["trash"] == 2
    assert row["fit"] == 1


async def test_junk_marked_at_a_second_pass_counts_too(session, session_factory):
    """Мусор, помеченный при повторном разборе, тоже идёт в счёт мусора.

    Такая строка остаётся в вакансиях со статусом «не подходит», и отличает
    её от честного отсева только пометка в причине отказа.
    """
    channel = channel_row(username="noisy", title="Шумный")
    await put(session_factory, channel)
    await put(
        session_factory,
        vacancy_row(
            source_channel_id=channel.id,
            status=VacancyStatus.NOT_FIT,
            skip_reason="trash: реклама курсов",
        ),
        vacancy_row(
            source_channel_id=channel.id,
            status=VacancyStatus.NOT_FIT,
            skip_reason="язык не тот",
        ),
        vacancy_row(
            source_channel_id=channel.id,
            status=VacancyStatus.NOT_FIT,
            skip_reason=None,
        ),
        vacancy_row(source_channel_id=channel.id, status=VacancyStatus.NEW),
    )

    row = (await rows_by_channel(session, period="all"))[channel.id]

    assert row["total"] == 4
    assert row["trash"] == 1
    assert row["not_fit"] == 2
    assert row["fit"] == 1


async def test_an_empty_post_marked_at_a_second_pass_is_junk_too(
    session, session_factory
):
    """Пустышка с повторного разбора идёт в мусор, а не в «не подошло».

    При обычном разборе такой пост удаляют вместе со строкой, и он ложится в
    отметки мусора. При повторном строка остаётся с другой меткой в причине
    отказа — и уходила в соседнюю колонку, хотя пост тот же самый.
    """
    channel = channel_row(username="noisy", title="Шумный")
    await put(session_factory, channel)
    await put(
        session_factory,
        vacancy_row(
            source_channel_id=channel.id,
            status=VacancyStatus.NOT_FIT,
            skip_reason=EMPTY_SKIP_REASON,
        ),
        vacancy_row(
            source_channel_id=channel.id,
            status=VacancyStatus.NOT_FIT,
            skip_reason="язык не тот",
        ),
    )

    row = (await rows_by_channel(session, period="all"))[channel.id]

    assert row["trash"] == 1
    assert row["not_fit"] == 1


async def test_the_leftover_is_zero_when_everything_was_junk(
    session, session_factory
):
    """Когда всё присланное оказалось мусором, годного остаётся ноль.

    Ниже нуля остаток не уходит по построению самой формулы, и заход за
    ноль отсюда недостижим: обе половины мусора входят в присланное. Охрана
    в коде остаётся страховкой на случай, если счётчики разойдутся по
    времени, а тест закрепляет границу.
    """
    channel = channel_row(username="noisy", title="Шумный")
    await put(session_factory, channel)
    await put(
        session_factory,
        vacancy_row(
            source_channel_id=channel.id,
            status=VacancyStatus.NOT_FIT,
            skip_reason="trash: реклама",
        ),
        TrashEvent(source_channel_id=channel.id, source_msg_id=1, reason="реклама"),
    )

    row = (await rows_by_channel(session, period="all"))[channel.id]

    assert row["total"] == 2
    assert row["trash"] == 2
    assert row["fit"] == 0


async def test_a_channel_pulled_in_by_the_funnel_alone_looks_like_the_others(
    session, session_factory
):
    """Канал, попавший в окно только воронкой, показан так же, как с рядами.

    Вакансия у него старая — в окно она не попадает, — а вот отклик по ней
    отправлен внутри окна, и это как раз прогресс за период. Строка ему
    собирается отдельной веткой добора, и без общей сборки у неё разъехались
    бы и подпись, и счётчики: сравнивается она здесь с соседом, у которого
    ряды в окне есть.
    """
    quiet = channel_row(username="quiet", title=None)
    loud = channel_row(username="loud", title=None)
    await put(session_factory, quiet, loud)
    old = vacancy_row(source_channel_id=quiet.id, created_at=days_ago(40))
    fresh = vacancy_row(source_channel_id=loud.id, created_at=days_ago(1))
    await put(session_factory, old, fresh)
    await put(
        session_factory,
        status_history_row(
            old.id, status=VacancyStatus.APPLIED, changed_at=days_ago(1)
        ),
    )

    rows = await rows_by_channel(session, period="week")

    assert set(rows) == {quiet.id, loud.id}
    assert (rows[quiet.id]["total"], rows[quiet.id]["trash"]) == (0, 0)
    assert rows[quiet.id]["sent"] == 1


async def test_a_channel_known_only_by_its_junk_still_appears(
    session, session_factory
):
    """Канал, от которого остались одни отметки о мусоре, в таблице есть.

    Строк вакансий у него нет вовсе, и без отдельного добора он выпал бы —
    а это как раз тот канал, о котором пользователю стоит знать.

    Заголовка у него нет нарочно: подпись такому каналу собирается в своей,
    отдельной ветке добора, и на канале с заголовком её отступ к нику был бы
    непроверяем.
    """
    channel = channel_row(username="allspam", title=None)
    await put(session_factory, channel)
    await put(
        session_factory,
        TrashEvent(source_channel_id=channel.id, source_msg_id=1, reason="реклама"),
    )

    row = (await rows_by_channel(session, period="all"))[channel.id]

    assert row["total"] == 1
    assert row["trash"] == 1
    assert row["not_fit"] == 0
    assert row["fit"] == 0




async def test_vacancies_without_a_channel_gather_in_their_own_row(
    session, session_factory
):
    """Вакансии не из канала — вставленные, заведённые руками, найденные на
    сайте — собираются своей строкой, а не пропадают из таблицы.

    Канал рядом нужен, чтобы строка без канала не слилась с его строкой.
    """
    channel = channel_row(username="ch", title="Канал")
    await put(session_factory, channel)
    await put(
        session_factory,
        vacancy_row(source_channel_id=channel.id),
        vacancy_row(),
        vacancy_row(status=VacancyStatus.NOT_FIT, skip_reason="язык не тот"),
        TrashEvent(source_channel_id=None, source_msg_id=None, reason="реклама"),
    )

    rows = await rows_by_channel(session, period="all")

    assert rows[channel.id]["total"] == 1
    no_channel = rows[None]
    assert (no_channel["total"], no_channel["trash"], no_channel["not_fit"]) == (3, 1, 1)
    assert no_channel["fit"] == 1


async def test_vacancies_without_a_channel_reach_the_funnel(session, session_factory):
    """Отклик по вакансии не из канала, ушедший в окне, виден в воронке.

    Сама вакансия старая и в окно ингеста не попадает: строку ей даёт только
    воронка.
    """
    old = vacancy_row(created_at=days_ago(40))
    await put(session_factory, old)
    await put(
        session_factory,
        status_history_row(old.id, status=VacancyStatus.APPLIED, changed_at=days_ago(1)),
    )

    row = (await rows_by_channel(session, period="week"))[None]

    assert (row["total"], row["sent"]) == (0, 1)


async def test_an_unparsed_vacancy_is_not_counted(session, session_factory):
    """Недоразобранная вакансия в счёт присланного не идёт."""
    channel = channel_row(username="ch", title="Канал")
    await put(session_factory, channel)
    await put(
        session_factory,
        vacancy_row(source_channel_id=channel.id, is_parsed=True),
        vacancy_row(source_channel_id=channel.id, is_parsed=True),
        vacancy_row(source_channel_id=channel.id, is_parsed=False),
    )

    row = (await rows_by_channel(session, period="all"))[channel.id]

    # Разобранных две против одной неразобранной нарочно: на равном наборе
    # перевёрнутый отбор дал бы то же число, и подмена осталась бы незаметной.
    assert row["total"] == 2
