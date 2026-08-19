"""Следствия таблицы «каналы» на экране статистики.

Таблица отвечает на вопрос «что канал приносит»: сколько прислал, сколько из
этого мусор, сколько отсеял фит-валидатор, сколько осталось годного, и что из
годного дошло по воронке.

Мусор считается из двух мест, и это не прихоть: при обычном разборе такой пост
удаляется из вакансий целиком, и след от него остаётся отдельной отметкой, а
при повторном разборе строка сохраняется с пометкой в причине отказа.
"""

from backend.domain.verdict import EMPTY_SKIP_REASON
from backend.models import TrashEvent, VacancyStatus
from backend.repository.stats_pipeline import get_stats_channels_pipeline
from tests.dbio import put
from tests.factories import channel_row, days_ago, status_history_row, vacancy_row


async def rows_by_label(session, **kwargs) -> dict[str, dict]:
    """Строки таблицы, разложенные по подписи канала."""
    got = await get_stats_channels_pipeline(session, **kwargs)
    return {row["label"]: row for row in got["channels"]}


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

    assert list(await rows_by_label(session, period="all")) == ["Работает"]


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

    assert list(await rows_by_label(session, period="week")) == ["Пишет"]
    assert sorted(await rows_by_label(session, period="all")) == sorted(
        ["Замолчал", "Пишет"]
    )


async def test_a_channel_is_labelled_by_what_it_has(session, session_factory):
    """Подпись канала — заголовок, а без него ник, а без ника номер строки."""
    titled = channel_row(username="a", title="С заголовком")
    named = channel_row(username="onlyname", title=None)
    bare = channel_row(username=None, title=None)
    await put(session_factory, titled, named, bare)
    await put(
        session_factory,
        vacancy_row(source_channel_id=titled.id),
        vacancy_row(source_channel_id=named.id),
        vacancy_row(source_channel_id=bare.id),
    )

    labels = set(await rows_by_label(session, period="all"))

    assert labels == {"С заголовком", "@onlyname", f"#{bare.id}"}


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

    row = (await rows_by_label(session, period="all"))["Шумный"]

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

    row = (await rows_by_label(session, period="all"))["Шумный"]

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

    row = (await rows_by_label(session, period="all"))["Шумный"]

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

    row = (await rows_by_label(session, period="all"))["Шумный"]

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

    rows = await rows_by_label(session, period="week")

    assert set(rows) == {"@quiet", "@loud"}
    assert (rows["@quiet"]["total"], rows["@quiet"]["trash"]) == (0, 0)
    assert rows["@quiet"]["sent"] == 1


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

    row = (await rows_by_label(session, period="all"))["@allspam"]

    assert row["total"] == 1
    assert row["trash"] == 1
    assert row["not_fit"] == 0
    assert row["fit"] == 0


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

    row = (await rows_by_label(session, period="all"))["Канал"]

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

    rows = await rows_by_label(session, period="all")

    assert (rows["Мой"]["sent"], rows["Мой"]["invite_plus"]) == (1, 0)
    assert (rows["Чужой"]["sent"], rows["Чужой"]["invite_plus"]) == (1, 1)


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

    row = (await rows_by_label(session, period="all"))["Канал"]

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

    row = (await rows_by_label(session, period="month"))["Канал"]

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

    row = (await rows_by_label(session, period="all"))["Канал"]

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

    within = (await rows_by_label(session, period="week"))["Канал"]
    lifetime = (await rows_by_label(session, period="all"))["Канал"]

    assert within["total"] == 1
    assert within["sent"] == 1
    assert lifetime["total"] == 2
    assert lifetime["sent"] == 1


async def test_the_table_leads_with_the_most_prolific_channel(
    session, session_factory
):
    """Вперёд идёт канал, приславший больше, при равенстве — по подписи.

    Порядок заведения обратен ожидаемому, а у равных подписи в разном
    регистре: сравнение по кодам символов поставило бы заглавные впереди.
    """
    few_late = channel_row(username="a", title="яблоко")
    few_early = channel_row(username="b", title="Апельсин")
    many = channel_row(username="c", title="Много")
    await put(session_factory, few_late, few_early, many)
    await put(
        session_factory,
        vacancy_row(source_channel_id=many.id),
        vacancy_row(source_channel_id=many.id),
        vacancy_row(source_channel_id=few_late.id),
        vacancy_row(source_channel_id=few_early.id),
    )

    got = await get_stats_channels_pipeline(session, period="all")

    assert [row["label"] for row in got["channels"]] == [
        "Много",
        "Апельсин",
        "яблоко",
    ]


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

    row = (await rows_by_label(session, period="all"))["Канал"]

    # Разобранных две против одной неразобранной нарочно: на равном наборе
    # перевёрнутый отбор дал бы то же число, и подмена осталась бы незаметной.
    assert row["total"] == 2


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

    row = (await rows_by_label(session, period="all"))["Канал"]

    assert (
        row["sent"], row["answered"], row["invite_plus"], row["decline"]
    ) == (1, 0, 0, 0)
