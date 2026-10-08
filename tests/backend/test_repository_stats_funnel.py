"""Следствия воронки канала на экране статистики: шаги и доли.

Шаг воронки считается по первому переходу вакансии, а не по последнему: канал
привёл её тогда, когда она дошла до шага впервые. Доли считаются от
отправленных этим каналом, и период режет приход и воронку каждый своей датой.

Что канал прислал и сколько из этого мусор — предмет соседа,
`test_repository_stats_pipeline.py`.
"""

from backend.models import VacancyStatus
from tests.backend.fixtures.stats import rows_by_channel
from tests.dbio import put
from tests.factories import channel_row, days_ago, status_history_row, vacancy_row


async def test_the_funnel_counts_the_first_move_of_each_vacancy(
    session, session_factory
):
    """Воронка считает вакансии по первому переходу в нужный набор статусов.

    Наборы вложены друг в друга: дошедшая до приглашения считается и
    ответившей, а до отказа — только ответившей.

    Все шесть статусов, считающихся ответом, и все три, считающихся
    продвижением, названы поимённо: с двумя-тремя выпадение любого из
    остальных прошло бы незамеченным.
    """
    channel = channel_row(username="ch", title="Канал")
    await put(session_factory, channel)
    answered_only = [VacancyStatus.ANSWERED, VacancyStatus.DECLINE]
    promoted = [
        VacancyStatus.INVITATION,
        VacancyStatus.IN_PROGRESS,
        VacancyStatus.OFFER,
    ]
    silent = vacancy_row(source_channel_id=channel.id)
    await put(session_factory, silent)
    await put(
        session_factory, status_history_row(silent.id, status=VacancyStatus.APPLIED)
    )
    for status in [VacancyStatus.TEST, *answered_only, *promoted]:
        vacancy = vacancy_row(source_channel_id=channel.id)
        await put(session_factory, vacancy)
        await put(
            session_factory,
            status_history_row(vacancy.id, status=VacancyStatus.APPLIED),
            status_history_row(vacancy.id, status=status),
        )

    row = (await rows_by_channel(session, period="all"))[channel.id]

    assert row["sent"] == 7
    assert row["answered"] == 6
    assert row["invite_plus"] == 3
    assert row["decline"] == 1


async def test_the_funnel_of_one_channel_does_not_leak_into_another(
    session, session_factory
):
    """Воронка одного канала в соседний не протекает.

    У ингеста разделение по каналам проверено, а у воронки счёт идёт своим
    путём — через историю статусов, — и совпадение там не гарантировано.
    """
    mine = channel_row(username="mine", title="Мой")
    other = channel_row(username="other", title="Чужой")
    await put(session_factory, mine, other)
    ours = vacancy_row(source_channel_id=mine.id)
    theirs = vacancy_row(source_channel_id=other.id)
    orphan = vacancy_row(source_channel_id=None)
    await put(session_factory, ours, theirs, orphan)
    await put(
        session_factory,
        status_history_row(ours.id, status=VacancyStatus.APPLIED),
        status_history_row(theirs.id, status=VacancyStatus.APPLIED),
        status_history_row(theirs.id, status=VacancyStatus.OFFER),
        status_history_row(orphan.id, status=VacancyStatus.APPLIED),
    )

    rows = await rows_by_channel(session, period="all")

    assert (rows[mine.id]["sent"], rows[mine.id]["invite_plus"]) == (1, 0)
    assert (rows[other.id]["sent"], rows[other.id]["invite_plus"]) == (1, 1)


async def test_the_conversions_are_shares_of_what_was_sent(
    session, session_factory
):
    """Доли считаются от отправленного, а не от присланного каналом."""
    channel = channel_row(username="ch", title="Канал")
    await put(session_factory, channel)
    answered = vacancy_row(source_channel_id=channel.id)
    silent = vacancy_row(source_channel_id=channel.id)
    unsent = vacancy_row(source_channel_id=channel.id)
    await put(session_factory, answered, silent, unsent)
    await put(
        session_factory,
        status_history_row(answered.id, status=VacancyStatus.APPLIED),
        status_history_row(answered.id, status=VacancyStatus.INVITATION),
        status_history_row(silent.id, status=VacancyStatus.APPLIED),
    )

    row = (await rows_by_channel(session, period="all"))[channel.id]

    assert row["total"] == 3
    assert row["sent"] == 2
    assert row["conv_answ_sent"] == 50.0
    assert row["conv_invite_sent"] == 50.0


async def test_a_share_counts_only_those_who_were_sent_in_the_window(
    session, session_factory
):
    """Доля считается по одной когорте — по тем, кого отправили в окне.

    Вакансия, отклик на которую ушёл до окна, а ответ пришёл внутри, в
    знаменатель не попадает. Считай мы её в числителе — доля перевалила бы
    за сотню, и полоска на экране вылезла бы из ячейки.
    """
    channel = channel_row(username="ch", title="Канал")
    await put(session_factory, channel)
    old = vacancy_row(title="откликнулись давно", source_channel_id=channel.id)
    fresh = vacancy_row(title="откликнулись в окне", source_channel_id=channel.id)
    await put(session_factory, old, fresh)
    await put(
        session_factory,
        status_history_row(
            old.id, status=VacancyStatus.APPLIED, changed_at=days_ago(40)
        ),
        status_history_row(
            old.id, status=VacancyStatus.ANSWERED, changed_at=days_ago(1)
        ),
        status_history_row(
            fresh.id, status=VacancyStatus.APPLIED, changed_at=days_ago(2)
        ),
    )

    row = (await rows_by_channel(session, period="month"))[channel.id]

    assert row["sent"] == 1
    assert row["answered"] == 1
    assert row["conv_answ_sent"] == 0.0


async def test_without_a_single_application_there_are_no_shares(
    session, session_factory
):
    """Без единого отправленного отклика долей нет вовсе, а не ноль."""
    channel = channel_row(username="ch", title="Канал")
    await put(session_factory, channel)
    await put(session_factory, vacancy_row(source_channel_id=channel.id))

    row = (await rows_by_channel(session, period="all"))[channel.id]

    assert row["sent"] == 0
    assert row["conv_answ_sent"] is None
    assert row["conv_invite_sent"] is None


async def test_the_window_cuts_ingest_and_funnel_by_their_own_dates(
    session, session_factory
):
    """Окно отсекает присланное по дате появления, а воронку — по дате перехода.

    Отклик, отправленный на этой неделе по вакансии месячной давности, в
    недельную сводку попадает: считается работа, сделанная в период.
    """
    channel = channel_row(username="ch", title="Канал")
    await put(session_factory, channel)
    stale = vacancy_row(source_channel_id=channel.id, created_at=days_ago(40))
    fresh = vacancy_row(source_channel_id=channel.id, created_at=days_ago(1))
    await put(session_factory, stale, fresh)
    await put(
        session_factory,
        status_history_row(
            stale.id, status=VacancyStatus.APPLIED, changed_at=days_ago(2)
        ),
    )

    within = (await rows_by_channel(session, period="week"))[channel.id]
    lifetime = (await rows_by_channel(session, period="all"))[channel.id]

    assert within["total"] == 1
    assert within["sent"] == 1
    assert lifetime["total"] == 2
    assert lifetime["sent"] == 1


async def test_an_unparsed_vacancy_walks_no_funnel_step(
    session, session_factory
):
    """Неразобранная вакансия не идёт ни по одной ступени воронки.

    Отбор «только разобранные» объявлен один на всю статистику, но
    применяет его каждая ступень сама: пропустит одна — «откликнулись» у
    канала разойдётся с шапкой статистики молча.
    """
    channel = channel_row(username="ch", title="Канал")
    await put(session_factory, channel)
    parsed = vacancy_row(source_channel_id=channel.id, is_parsed=True)
    unparsed = vacancy_row(source_channel_id=channel.id, is_parsed=False)
    await put(session_factory, parsed, unparsed)
    await put(
        session_factory,
        status_history_row(parsed.id, status=VacancyStatus.APPLIED),
        status_history_row(unparsed.id, status=VacancyStatus.APPLIED),
        status_history_row(unparsed.id, status=VacancyStatus.INVITATION),
        status_history_row(unparsed.id, status=VacancyStatus.DECLINE),
    )

    row = (await rows_by_channel(session, period="all"))[channel.id]

    assert (
        row["sent"], row["answered"], row["invite_plus"], row["decline"]
    ) == (1, 0, 0, 0)
