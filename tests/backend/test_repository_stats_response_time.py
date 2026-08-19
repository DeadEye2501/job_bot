"""Следствия подсчёта срока ответа на отклик.

Отсчёт идёт от первого перехода вакансии в «отправлено», а ответом считается
первое входящее сообщение после него — своих писем, удалённых и пришедших
раньше отправки в счёт не берут.
"""

from datetime import timedelta

from backend.models import VacancyStatus
from backend.repository.stats_responses import get_stats_hr_responses
from tests.dbio import put
from tests.factories import (
    days_ago,
    hr_row,
    message_row,
    status_history_row,
)


async def test_without_any_application_everything_is_empty(session):
    """Без единого отклика считать нечего, и это видно по ответу."""
    got = await get_stats_hr_responses(session, period="all")

    assert got["by_weekday"] == [0, 0, 0, 0, 0, 0, 0]
    assert got["median_seconds"] is None
    assert got["no_response_pct"] is None
    assert got["applied_count"] == 0
    assert got["responded_count"] == 0


async def test_an_application_without_an_answer_is_counted_as_silence(
    session, applied
):
    """Отклик без ответа считается молчанием, а не пропускается."""
    await applied(days_ago(10))

    got = await get_stats_hr_responses(session, period="all")

    assert got["applied_count"] == 1
    assert got["responded_count"] == 0
    assert got["no_response_pct"] == 100
    assert got["median_seconds"] is None


async def test_an_unparsed_vacancy_moves_neither_the_silence_nor_the_median(
    session, session_factory, applied
):
    """Неразобранная вакансия ни долю молчания, ни медиану срока не двигает.

    Соседние ступени — шапка, разбивка по статусам, теги, таблица каналов —
    считают только разобранные. Ступень, считающая по своему множеству,
    разводит числа двух экранов молча: правдоподобно они выглядят на обоих.

    На неразобранную нарочно отвечают, и с другим сроком: без ответа она
    двигала бы одну лишь долю молчания, а медиана в имени не сторожилась бы.
    """
    hr = hr_row()
    await put(session_factory, hr)
    applied_at = days_ago(30)
    await applied(applied_at, hr=hr, answered_after=timedelta(days=1))
    await applied(
        applied_at, hr=hr, answered_after=timedelta(days=9), is_parsed=False
    )

    got = await get_stats_hr_responses(session, period="all")

    assert got["applied_count"] == 1
    assert got["responded_count"] == 1
    assert got["median_seconds"] == timedelta(days=1).total_seconds()


async def test_our_own_letter_is_not_an_answer(session, session_factory, applied):
    """Наше собственное письмо ответом не считается."""
    hr = hr_row()
    await put(session_factory, hr)
    vacancy = await applied(days_ago(10), hr=hr)
    await put(
        session_factory,
        message_row(
            hr_id=hr.id, vacancy_id=vacancy.id, is_incoming=False, sent_at=days_ago(9)
        ),
    )

    assert (await get_stats_hr_responses(session, period="all"))["responded_count"] == 0


async def test_a_deleted_message_is_not_an_answer(session, session_factory, applied):
    """Удалённое сообщение ответом не считается."""
    hr = hr_row()
    await put(session_factory, hr)
    vacancy = await applied(days_ago(10), hr=hr)
    await put(
        session_factory,
        message_row(
            hr_id=hr.id,
            vacancy_id=vacancy.id,
            is_incoming=True,
            is_deleted=True,
            sent_at=days_ago(9),
        ),
    )

    assert (await get_stats_hr_responses(session, period="all"))["responded_count"] == 0


async def test_a_message_older_than_the_application_is_not_an_answer(
    session, session_factory, applied
):
    """Сообщение, пришедшее до отправки отклика, ответом на него не является.

    Переписка с HR могла идти и раньше — по другой вакансии или просто так.
    """
    hr = hr_row()
    await put(session_factory, hr)
    vacancy = await applied(days_ago(10), hr=hr)
    await put(
        session_factory,
        message_row(
            hr_id=hr.id, vacancy_id=vacancy.id, is_incoming=True, sent_at=days_ago(20)
        ),
    )

    assert (await get_stats_hr_responses(session, period="all"))["responded_count"] == 0


async def test_the_first_answer_after_the_application_is_the_one(
    session, session_factory, applied
):
    """Ответом считается первое входящее после отправки, а не последнее.

    Второе сообщение вставлено раньше первого: без выбора наименьшего срок
    ответа считался бы по тому, что попалось.
    """
    hr = hr_row()
    await put(session_factory, hr)
    applied_at = days_ago(10)
    vacancy = await applied(applied_at, hr=hr, answered_after=timedelta(days=3))
    await put(
        session_factory,
        message_row(
            hr_id=hr.id,
            vacancy_id=vacancy.id,
            is_incoming=True,
            sent_at=applied_at + timedelta(days=1),
        ),
    )

    got = await get_stats_hr_responses(session, period="all")

    assert got["responded_count"] == 1
    assert got["median_seconds"] == timedelta(days=1).total_seconds()


async def test_the_countdown_starts_at_the_first_application_not_the_last(
    session, session_factory, applied
):
    """Отсчёт идёт от первой отправки отклика, а не от последней.

    Вакансию отправляли дважды: месяц назад и на днях. Ответ пришёл вчера.
    Считать срок от последней отправки значило бы записать месяц ожидания в
    один день.
    """
    hr = hr_row()
    await put(session_factory, hr)
    first_applied = days_ago(31)
    vacancy = await applied(first_applied, hr=hr, answered_after=timedelta(days=30))
    await put(
        session_factory,
        status_history_row(
            vacancy.id, status=VacancyStatus.APPLIED, changed_at=days_ago(2)
        ),
    )

    got = await get_stats_hr_responses(session, period="all")

    assert got["median_seconds"] == timedelta(days=30).total_seconds()


async def test_the_median_of_an_odd_count_is_the_middle_one(
    session, session_factory, applied
):
    """Срединный срок при нечётном числе ответов — средний из них.

    Пять ответов, а не один: на одном сдвиг указателя на соседний элемент
    некуда было бы заметить, и ошибка в выборе середины прошла бы молча.
    Сроки нарочно неравномерны — среднее арифметическое дало бы другое
    число.

    Заводятся они вперемешку, а не по возрастанию: проверено мутацией, что
    на упорядоченном наборе саму сортировку перед взятием середины можно
    снять незаметно.
    """
    hr = hr_row()
    await put(session_factory, hr)
    applied_at = days_ago(60)
    for waited in (20, 1, 40, 4, 2):
        await applied(applied_at, hr=hr, answered_after=timedelta(days=waited))

    got = await get_stats_hr_responses(session, period="all")

    assert got["median_seconds"] == timedelta(days=4).total_seconds()


async def test_the_median_of_an_even_count_is_the_middle_of_two(
    session, session_factory, applied
):
    """Срединный срок при чётном числе ответов — среднее двух средних."""
    hr = hr_row()
    await put(session_factory, hr)
    applied_at = days_ago(30)
    for waited in (1, 2, 3, 10):
        await applied(applied_at, hr=hr, answered_after=timedelta(days=waited))

    got = await get_stats_hr_responses(session, period="all")

    assert got["median_seconds"] == timedelta(days=2.5).total_seconds()


async def test_the_share_of_silence_is_a_whole_percent(
    session, session_factory, applied
):
    """Доля молчания считается целыми процентами от числа откликов."""
    hr = hr_row()
    await put(session_factory, hr)
    applied_at = days_ago(30)
    for answered in (True, False, False):
        await applied(
            applied_at,
            hr=hr,
            answered_after=timedelta(days=1) if answered else None,
        )

    got = await get_stats_hr_responses(session, period="all")

    assert got["applied_count"] == 3
    assert got["responded_count"] == 1
    assert got["no_response_pct"] == 67


async def test_the_window_cuts_by_the_first_application(
    session, session_factory, applied
):
    """Окно отсекает по первой отправке отклика, а не по ответу.

    Считается работа, сделанная в этот период: отклик, отправленный месяц
    назад, в недельную сводку не входит, даже если ответ пришёл вчера.
    """
    hr = hr_row()
    await put(session_factory, hr)
    await applied(days_ago(3), hr=hr)
    await applied(days_ago(40), hr=hr, answered_after=timedelta(days=39))

    within = await get_stats_hr_responses(session, period="week")
    lifetime = await get_stats_hr_responses(session, period="all")

    assert within["applied_count"] == 1
    assert within["responded_count"] == 0
    assert lifetime["applied_count"] == 2
    assert lifetime["responded_count"] == 1
