"""Следствия подсчёта срока ответа на отклик.

Отсчёт идёт от первого перехода вакансии в «отправлено», а ответом считается
первый после него переход в статус, которого без ответа работодателя не бывает:
Answered, Test, Invitation, In Progress, Offer, Decline. Откуда пришёл ответ —
из Telegram, с сайта, по почте, — неважно: важно, что статус сменился.
"""

from datetime import timedelta

import pytest

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


async def test_an_application_without_an_answer_is_counted_as_silence(session, applied):
    """Отклик без ответа считается молчанием, а не пропускается."""
    await applied(days_ago(10))

    got = await get_stats_hr_responses(session, period="all")

    assert got["applied_count"] == 1
    assert got["responded_count"] == 0
    assert got["no_response_pct"] == 100
    assert got["median_seconds"] is None


async def test_an_unparsed_vacancy_moves_neither_the_silence_nor_the_median(session, applied):
    """Неразобранная вакансия ни долю молчания, ни медиану срока не двигает.

    Соседние ступени — шапка, разбивка по статусам, теги, таблица каналов —
    считают только разобранные. Ступень, считающая по своему множеству,
    разводит числа двух экранов молча: правдоподобно они выглядят на обоих.

    На неразобранную нарочно отвечают, и с другим сроком: без ответа она
    двигала бы одну лишь долю молчания, а медиана в имени не сторожилась бы.
    """
    applied_at = days_ago(30)
    await applied(applied_at, answered_after=timedelta(days=1))
    await applied(applied_at, answered_after=timedelta(days=9), is_parsed=False)

    got = await get_stats_hr_responses(session, period="all")

    assert got["applied_count"] == 1
    assert got["responded_count"] == 1
    assert got["median_seconds"] == timedelta(days=1).total_seconds()


@pytest.mark.parametrize(
    "answer",
    [
        VacancyStatus.ANSWERED,
        VacancyStatus.TEST,
        VacancyStatus.INVITATION,
        VacancyStatus.IN_PROGRESS,
        VacancyStatus.OFFER,
        VacancyStatus.DECLINE,
    ],
)
async def test_any_step_the_employer_had_to_take_counts_as_an_answer(session, applied, answer):
    """Отклик, сразу ушедший дальше «ответили», — тоже ответ.

    Позвали на тест, на собеседование, прислали оффер или отказ — без ответа
    работодателя ни один такой переход не случается, и молчанием его не
    назовёшь.
    """
    await applied(days_ago(10), answered_after=timedelta(days=2), answer=answer)

    got = await get_stats_hr_responses(session, period="all")

    assert got["responded_count"] == 1
    assert got["median_seconds"] == timedelta(days=2).total_seconds()


async def test_ghosting_is_silence_not_an_answer(session, applied):
    """Переход в Ghosting ответом не считается: это и есть молчание."""
    await applied(days_ago(10), answered_after=timedelta(days=7), answer=VacancyStatus.GHOSTING)

    got = await get_stats_hr_responses(session, period="all")

    assert got["responded_count"] == 0
    assert got["no_response_pct"] == 100


async def test_a_letter_without_a_change_of_status_is_not_an_answer(
    session, session_factory, applied
):
    """Входящее письмо без смены статуса ответом не считается.

    Ответ меряется по статусу, а не по переписке: иначе отклики с сайта и по
    почте, о которых приложение писем не видит, навсегда числились бы
    молчанием, а телеграмные — нет.
    """
    hr = hr_row()
    await put(session_factory, hr)
    vacancy = await applied(days_ago(10), hr_id=hr.id)
    await put(
        session_factory,
        message_row(hr_id=hr.id, vacancy_id=vacancy.id, is_incoming=True, sent_at=days_ago(9)),
    )

    assert (await get_stats_hr_responses(session, period="all"))["responded_count"] == 0


async def test_an_answer_older_than_the_application_does_not_count(
    session, session_factory, applied
):
    """Ответный переход раньше отклика ответом на этот отклик не является."""
    vacancy = await applied(days_ago(10))
    await put(
        session_factory,
        status_history_row(vacancy.id, status=VacancyStatus.ANSWERED, changed_at=days_ago(20)),
    )

    assert (await get_stats_hr_responses(session, period="all"))["responded_count"] == 0


async def test_an_answer_at_the_moment_of_the_application_counts(session, applied):
    """Ответ, записанный в ту же секунду, что и отклик, — ответ.

    Метки в базе секундные, и отклик с мгновенной сменой статуса ложатся в одну
    секунду. Ответа раньше отклика не бывает, а одновременный — бывает.
    """
    await applied(days_ago(10), answered_after=timedelta(0))

    got = await get_stats_hr_responses(session, period="all")

    assert got["responded_count"] == 1
    assert got["median_seconds"] == 0


async def test_the_first_answer_after_the_application_is_the_one(
    session, session_factory, applied
):
    """Ответом считается первый ответный переход после отправки.

    Самый ранний лежит в базе средним из трёх: выбор по первой попавшейся
    строке и выбор по последней дали бы другой срок.
    """
    applied_at = days_ago(10)
    vacancy = await applied(applied_at, answered_after=timedelta(days=3))
    await put(
        session_factory,
        status_history_row(
            vacancy.id,
            status=VacancyStatus.TEST,
            changed_at=applied_at + timedelta(days=1),
        ),
        status_history_row(
            vacancy.id,
            status=VacancyStatus.INVITATION,
            changed_at=applied_at + timedelta(days=5),
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
    first_applied = days_ago(31)
    vacancy = await applied(first_applied, answered_after=timedelta(days=30))
    await put(
        session_factory,
        status_history_row(vacancy.id, status=VacancyStatus.APPLIED, changed_at=days_ago(2)),
    )

    got = await get_stats_hr_responses(session, period="all")

    assert got["median_seconds"] == timedelta(days=30).total_seconds()


async def test_the_median_of_an_odd_count_is_the_middle_one(session, applied):
    """Срединный срок при нечётном числе ответов — средний из них.

    Пять ответов, а не один: на одном сдвиг указателя на соседний элемент
    некуда было бы заметить, и ошибка в выборе середины прошла бы молча.
    Сроки нарочно неравномерны — среднее арифметическое дало бы другое
    число.

    Заводятся они вперемешку, а не по возрастанию: проверено мутацией, что
    на упорядоченном наборе саму сортировку перед взятием середины можно
    снять незаметно.
    """
    applied_at = days_ago(60)
    for waited in (20, 1, 40, 4, 2):
        await applied(applied_at, answered_after=timedelta(days=waited))

    got = await get_stats_hr_responses(session, period="all")

    assert got["median_seconds"] == timedelta(days=4).total_seconds()


async def test_the_median_of_an_even_count_is_the_middle_of_two(session, applied):
    """Срединный срок при чётном числе ответов — среднее двух средних."""
    applied_at = days_ago(30)
    for waited in (1, 2, 3, 10):
        await applied(applied_at, answered_after=timedelta(days=waited))

    got = await get_stats_hr_responses(session, period="all")

    assert got["median_seconds"] == timedelta(days=2.5).total_seconds()


async def test_the_share_of_silence_is_a_whole_percent(session, applied):
    """Доля молчания считается целыми процентами от числа откликов."""
    applied_at = days_ago(30)
    for answered in (True, False, False):
        await applied(
            applied_at,
            answered_after=timedelta(days=1) if answered else None,
        )

    got = await get_stats_hr_responses(session, period="all")

    assert got["applied_count"] == 3
    assert got["responded_count"] == 1
    assert got["no_response_pct"] == 67


async def test_the_window_cuts_by_the_first_application(session, applied):
    """Окно отсекает по первой отправке отклика, а не по ответу.

    Считается работа, сделанная в этот период: отклик, отправленный месяц
    назад, в недельную сводку не входит, даже если ответ пришёл вчера.
    """
    await applied(days_ago(3))
    await applied(days_ago(40), answered_after=timedelta(days=39))

    within = await get_stats_hr_responses(session, period="week")
    lifetime = await get_stats_hr_responses(session, period="all")

    assert within["applied_count"] == 1
    assert within["responded_count"] == 0
    assert lifetime["applied_count"] == 2
    assert lifetime["responded_count"] == 1
