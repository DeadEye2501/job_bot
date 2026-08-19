"""Следствия разбивки вакансий по статусам за период.

Разбивка называет все статусы, включая те, которых сейчас нет ни у одной
вакансии: экран рисует воронку постоянным набором столбцов, и пропущенный
статус сдвинул бы их.

В отличие от сводных счётчиков в шапке, здесь считается нынешний статус, а не
история: это снимок «где всё лежит сейчас», а не «через что прошло».
"""

from backend.models import VacancyStatus
from backend.repository.stats_statuses import get_stats_status_breakdown
from tests.dbio import put
from tests.factories import days_ago, status_history_row, vacancy_row


async def test_an_empty_database_names_every_status_with_a_zero(session):
    """На пустой базе названы все статусы, у каждого ноль."""
    got = await get_stats_status_breakdown(session, period="all")

    assert got["period"] == "all"
    assert set(got["counts"]) == {s.value for s in VacancyStatus}
    assert set(got["counts"].values()) == {0}


async def test_only_parsed_vacancies_are_counted(session, session_factory):
    """Недоразобранные вакансии в разбивку не идут."""
    await put(
        session_factory,
        vacancy_row(status=VacancyStatus.NEW, is_parsed=True),
        vacancy_row(status=VacancyStatus.NEW, is_parsed=False),
    )

    counts = (await get_stats_status_breakdown(session, period="all"))["counts"]

    assert counts["New"] == 1


async def test_the_current_status_is_counted_not_the_history(
    session, session_factory
):
    """Считается нынешний статус, а не пройденные.

    Вакансия побывала в «отправлено», а сейчас снова новая: в шапке она
    останется отправленной навсегда, а здесь лежит в «новых».
    """
    vacancy = vacancy_row(status=VacancyStatus.NEW)
    await put(session_factory, vacancy)
    await put(
        session_factory,
        status_history_row(vacancy.id, status=VacancyStatus.APPLIED),
    )

    counts = (await get_stats_status_breakdown(session, period="all"))["counts"]

    assert counts["New"] == 1
    assert counts["Applied"] == 0


async def test_a_vacancy_without_history_is_cut_by_its_creation_date(
    session, session_factory
):
    """У вакансии без истории окно отсекает по дате её появления.

    В «новую» вакансия попадает самим заведением, и перехода туда никто не
    пишет: считать по переходу тут нечего.
    """
    await put(
        session_factory,
        vacancy_row(status=VacancyStatus.NEW, created_at=days_ago(1)),
        vacancy_row(status=VacancyStatus.NEW, created_at=days_ago(40)),
    )

    within = (await get_stats_status_breakdown(session, period="week"))["counts"]
    lifetime = (await get_stats_status_breakdown(session, period="all"))["counts"]

    assert within["New"] == 1
    assert lifetime["New"] == 2


async def test_the_window_counts_when_the_vacancy_entered_its_status(
    session, session_factory
):
    """Окно считает по тому, когда вакансия встала туда, где стоит сейчас.

    Соседняя карточка того же экрана — дельты в шапке — считает окно так же,
    по времени перехода. Считай разбивка по дате появления, и вакансия,
    заведённая в позапрошлом месяце и откликнутая вчера, попадала бы в
    «+1 за неделю» наверху и не попадала бы в столбик «Applied» под ним.
    """
    vacancy = vacancy_row(status=VacancyStatus.APPLIED, created_at=days_ago(40))
    await put(session_factory, vacancy)
    await put(
        session_factory,
        status_history_row(
            vacancy.id, status=VacancyStatus.APPLIED, changed_at=days_ago(1)
        ),
    )

    counts = (await get_stats_status_breakdown(session, period="week"))["counts"]

    assert counts["Applied"] == 1


async def test_a_status_entered_before_the_window_stays_out(
    session, session_factory
):
    """Вакансия, вставшая в свой статус до окна, в него не попадает.

    Иначе счёт «за неделю» отличался бы от лайфтайма только заведёнными
    заново, и любая давняя вакансия числилась бы свежей.
    """
    vacancy = vacancy_row(status=VacancyStatus.APPLIED, created_at=days_ago(1))
    await put(session_factory, vacancy)
    await put(
        session_factory,
        status_history_row(
            vacancy.id, status=VacancyStatus.APPLIED, changed_at=days_ago(40)
        ),
    )

    counts = (await get_stats_status_breakdown(session, period="week"))["counts"]

    assert counts["Applied"] == 0


async def test_the_latest_entry_into_the_status_decides(session, session_factory):
    """Считается последний вход в нынешний статус, а не первый.

    Вакансия могла побывать в «отправлено» в мае, откатиться и уйти туда же
    вчера. Возьми мы первый вход — она числилась бы майской и в свежий счёт
    не попадала бы, хотя откликнулись по ней позавчера.
    """
    vacancy = vacancy_row(status=VacancyStatus.APPLIED, created_at=days_ago(60))
    await put(session_factory, vacancy)
    await put(
        session_factory,
        status_history_row(
            vacancy.id, status=VacancyStatus.APPLIED, changed_at=days_ago(50)
        ),
        status_history_row(
            vacancy.id, status=VacancyStatus.APPLIED, changed_at=days_ago(2)
        ),
    )

    counts = (await get_stats_status_breakdown(session, period="week"))["counts"]

    assert counts["Applied"] == 1


async def test_a_comment_to_the_current_status_does_not_refresh_it(
    session, session_factory
):
    """Комментарий к нынешнему статусу свежести вакансии не прибавляет.

    Строку истории заводит и он, но вакансия никуда не двигалась: у такой
    строки снят признак «применено». Считай мы её переходом — дописанная
    вчера заметка к майскому оферу показывала бы офер сегодняшним, а верхний
    ряд того же экрана честно давал бы ноль.
    """
    vacancy = vacancy_row(status=VacancyStatus.OFFER, created_at=days_ago(60))
    await put(session_factory, vacancy)
    await put(
        session_factory,
        status_history_row(
            vacancy.id, status=VacancyStatus.OFFER, changed_at=days_ago(50)
        ),
        status_history_row(
            vacancy.id,
            status=VacancyStatus.OFFER,
            changed_at=days_ago(1),
            applied=False,
        ),
    )

    counts = (await get_stats_status_breakdown(session, period="week"))["counts"]

    assert counts["Offer"] == 0


async def test_each_status_gets_its_own_tally(session, session_factory):
    """Каждый статус получает свой счёт, а не общий."""
    await put(
        session_factory,
        vacancy_row(status=VacancyStatus.NEW),
        vacancy_row(status=VacancyStatus.NEW),
        vacancy_row(status=VacancyStatus.OFFER),
        vacancy_row(status=VacancyStatus.GHOSTING),
    )

    counts = (await get_stats_status_breakdown(session, period="all"))["counts"]

    assert counts["New"] == 2
    assert counts["Offer"] == 1
    assert counts["Ghosting"] == 1
    assert counts["Decline"] == 0
