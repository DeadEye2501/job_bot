"""Следствия сводных счётчиков в шапке экрана статистики.

Все счётчики, кроме общего, считаются по истории: вакансия попадает в них,
если когда-либо доходила до нужного статуса. Такой счётчик только растёт —
ручной откат статуса назад его не уменьшает, и «отправлено 40» не превращается
в «отправлено 38» оттого, что две вакансии вернули в новые.

Прибавка за период считается по первому переходу, а не по последнему: вакансия
считается отправленной в тот день, когда её отправили.
"""

from backend.models import VacancyStatus
from backend.repository.stats_kpi import get_stats_kpi
from tests.dbio import put
from tests.factories import days_ago, status_history_row, vacancy_row


async def test_an_empty_database_gives_zeroes(session):
    """На пустой базе все счётчики нулевые, а прибавки — отсутствуют."""
    kpi = await get_stats_kpi(session, period="all")

    assert kpi["total"] == 0
    assert kpi["applied_total"] == 0
    assert kpi["total_period"] is None


async def test_the_total_counts_only_parsed_vacancies(session, session_factory):
    """Общий счётчик считает только разобранные вакансии."""
    await put(
        session_factory,
        vacancy_row(is_parsed=True),
        vacancy_row(is_parsed=True),
        vacancy_row(is_parsed=False),
    )

    assert (await get_stats_kpi(session, period="all"))["total"] == 2


async def test_an_unparsed_vacancy_stays_out_of_every_counter(
    session, session_factory
):
    """Неразобранная вакансия не попадает ни в один счётчик, даже с историей.

    Общий счётчик считает только разобранные, а ступени воронки идут по
    истории статусов — и если их не соединить с вакансией, неразобранная
    попадёт в «откликнулись», не попав в «всего». На экране это выглядит
    как воронка, где первая ступень шире входа в неё.

    Разобранная в наборе одна и до отклика доходила, неразобранных две и
    обе доходили: без отбора «откликнулись» было бы три при «всего» один.
    """
    parsed = vacancy_row(is_parsed=True)
    unparsed_one = vacancy_row(is_parsed=False)
    unparsed_two = vacancy_row(is_parsed=False)
    await put(session_factory, parsed, unparsed_one, unparsed_two)
    await put(
        session_factory,
        status_history_row(parsed.id, changed_at=days_ago(1)),
        status_history_row(unparsed_one.id, changed_at=days_ago(1)),
        status_history_row(unparsed_two.id, changed_at=days_ago(1)),
    )

    kpi = await get_stats_kpi(session, period="week")

    assert kpi["total"] == 1
    assert kpi["applied_total"] == 1
    assert kpi["applied_period"] == 1


async def test_a_vacancy_from_the_applied_fixture_counts_in_the_period(
    session, applied
):
    """Отклик, собранный общей фикстурой, виден и в прибавке за период.

    Прибавка `total` идёт по `created_at` вакансии, а не по её истории.
    Заводи фикстура вакансию задним числом, каждая проверка периода на ней
    получала бы ноль и указывала бы на отбор, хотя виновата обстановка.
    """
    await applied(days_ago(2))

    kpi = await get_stats_kpi(session, period="week")

    assert kpi["applied_period"] == 1
    assert kpi["total_period"] == 1


async def test_a_reverted_status_does_not_shrink_the_counter(
    session, session_factory
):
    """Откат статуса назад счётчик не уменьшает.

    Счёт идёт по истории: вакансия побывала в «отправлено», и это уже не
    отменить. Сейчас она снова новая, но из счётчика не пропала.
    """
    vacancy = vacancy_row(status=VacancyStatus.NEW)
    await put(session_factory, vacancy)
    await put(
        session_factory,
        status_history_row(
            vacancy.id, status=VacancyStatus.APPLIED, changed_at=days_ago(2)
        ),
        status_history_row(
            vacancy.id, status=VacancyStatus.NEW, changed_at=days_ago(1)
        ),
    )

    assert (await get_stats_kpi(session, period="all"))["applied_total"] == 1


async def test_a_vacancy_is_counted_once_however_often_it_moved(
    session, session_factory
):
    """Вакансия считается один раз, сколько бы раз ни возвращалась в статус."""
    vacancy = vacancy_row()
    await put(session_factory, vacancy)
    await put(
        session_factory,
        status_history_row(
            vacancy.id, status=VacancyStatus.APPLIED, changed_at=days_ago(3)
        ),
        status_history_row(
            vacancy.id, status=VacancyStatus.APPLIED, changed_at=days_ago(1)
        ),
    )

    assert (await get_stats_kpi(session, period="all"))["applied_total"] == 1


async def test_in_progress_covers_all_three_of_its_statuses(session, session_factory):
    """«В работе» считает приглашения, тестовые задания и сам «In Progress».

    Статуса, названного тем же словом, в наборе не было. Пока вакансию двигает
    автоматика, разницы почти не видно: по графу в «In Progress» приходят из
    приглашения и теста, то есть вакансия уже засчитана. Но прямое нажатие
    человека графу не подчиняется — и поставленный рукой «In Progress» не
    попадал в шапку вовсе: в кольце под ней строка горела, а счётчик над
    кольцом показывал ноль.

    Рядом лежит вакансия в статусе, к «в работе» не относящемся: без неё
    счётчик мог бы считать всё подряд.
    """
    invited = vacancy_row()
    tested = vacancy_row()
    working = vacancy_row()
    declined = vacancy_row()
    await put(session_factory, invited, tested, working, declined)
    await put(
        session_factory,
        status_history_row(invited.id, status=VacancyStatus.INVITATION),
        status_history_row(tested.id, status=VacancyStatus.TEST),
        status_history_row(working.id, status=VacancyStatus.IN_PROGRESS),
        status_history_row(declined.id, status=VacancyStatus.DECLINE),
    )

    kpi = await get_stats_kpi(session, period="all")

    assert kpi["in_progress_total"] == 3
    assert kpi["decline_total"] == 1


async def test_each_counter_watches_its_own_status(session, session_factory):
    """Каждый счётчик следит за своим статусом и чужие не считает."""
    applied = vacancy_row()
    offered = vacancy_row()
    declined = vacancy_row()
    await put(session_factory, applied, offered, declined)
    await put(
        session_factory,
        status_history_row(applied.id, status=VacancyStatus.APPLIED),
        status_history_row(offered.id, status=VacancyStatus.OFFER),
        status_history_row(declined.id, status=VacancyStatus.DECLINE),
    )

    kpi = await get_stats_kpi(session, period="all")

    assert (
        kpi["applied_total"],
        kpi["offer_total"],
        kpi["decline_total"],
        kpi["in_progress_total"],
    ) == (1, 1, 1, 0)


async def test_over_all_time_there_are_no_period_gains(session, session_factory):
    """За всё время прибавки не считаются: сравнивать не с чем."""
    vacancy = vacancy_row()
    await put(session_factory, vacancy)
    await put(session_factory, status_history_row(vacancy.id, status=VacancyStatus.APPLIED))

    kpi = await get_stats_kpi(session, period="all")

    assert kpi["total_period"] is None
    assert kpi["applied_period"] is None
    assert kpi["in_progress_period"] is None
    assert kpi["offer_period"] is None
    assert kpi["decline_period"] is None


async def test_the_total_gain_counts_vacancies_created_in_the_window(
    session, session_factory
):
    """Прибавка к общему счётчику — вакансии, появившиеся в окне."""
    await put(
        session_factory,
        vacancy_row(created_at=days_ago(1)),
        vacancy_row(created_at=days_ago(3)),
        vacancy_row(created_at=days_ago(40)),
    )

    kpi = await get_stats_kpi(session, period="week")

    assert kpi["total"] == 3
    assert kpi["total_period"] == 2


async def test_a_gain_counts_the_first_move_not_the_latest(
    session, session_factory
):
    """Прибавка считается по первому переходу, а не по последнему.

    Вакансию отправили давно, а потом возвращали в тот же статус уже в
    окне. Считать её отправленной на этой неделе значило бы приписать
    работу не тому дню.
    """
    vacancy = vacancy_row(created_at=days_ago(40))
    await put(session_factory, vacancy)
    await put(
        session_factory,
        status_history_row(
            vacancy.id, status=VacancyStatus.APPLIED, changed_at=days_ago(40)
        ),
        status_history_row(
            vacancy.id, status=VacancyStatus.APPLIED, changed_at=days_ago(1)
        ),
    )

    kpi = await get_stats_kpi(session, period="week")

    assert kpi["applied_total"] == 1
    assert kpi["applied_period"] == 0


def _four_steps(vacancy_id: int, when):
    """Все четыре ступени воронки, пройденные одной вакансией в один день."""
    return [
        status_history_row(vacancy_id, status=status, changed_at=when)
        for status in (
            VacancyStatus.APPLIED,
            VacancyStatus.TEST,
            VacancyStatus.OFFER,
            VacancyStatus.DECLINE,
        )
    ]


async def test_every_gain_respects_the_window(session, session_factory):
    """Окно действует на все четыре прибавки, а не на одну."""
    fresh = vacancy_row(created_at=days_ago(1))
    stale = vacancy_row(created_at=days_ago(40))
    await put(session_factory, fresh, stale)
    await put(
        session_factory,
        *_four_steps(fresh.id, days_ago(1)),
        *_four_steps(stale.id, days_ago(40)),
    )

    kpi = await get_stats_kpi(session, period="week")

    assert (
        kpi["applied_total"],
        kpi["in_progress_total"],
        kpi["offer_total"],
        kpi["decline_total"],
    ) == (2, 2, 2, 2)
    assert (
        kpi["applied_period"],
        kpi["in_progress_period"],
        kpi["offer_period"],
        kpi["decline_period"],
    ) == (1, 1, 1, 1)
