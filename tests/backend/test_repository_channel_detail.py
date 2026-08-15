"""Следствия сборки карточки канала с воронкой отбора.

Воронка отвечает на три вопроса подряд: сколько из пришедшего подошло, на
сколько подошедшего мы откликнулись и на сколько откликов ответили. Каждая
доля считается от предыдущей ступени, а не от общего числа: иначе канал с
одной удачей из тысячи и канал с одной из двух выглядели бы одинаково.
"""

import pytest

from backend.models import VacancyStatus
from backend.domain.funnel import percent_or_none
from backend.repository.channels import get_channel_detail
from tests.dbio import put
from tests.factories import (
    channel_marks,
    channel_row,
    days_ago,
    marked_channels,
    vacancy_row,
)


_FUNNEL_SET = (
    [VacancyStatus.NOT_FIT] * 2
    + [VacancyStatus.SCAM] * 2
    + [VacancyStatus.NEW] * 8
    + [
        VacancyStatus.ANSWERED,
        VacancyStatus.TEST,
        VacancyStatus.INVITATION,
        VacancyStatus.IN_PROGRESS,
        VacancyStatus.OFFER,
        VacancyStatus.DECLINE,
    ]
    + [VacancyStatus.APPLIED, VacancyStatus.GHOSTING]
)
"""Двадцать вакансий: четыре неподходящих, восемь новых, шесть с ответом, две без.

Названы поимённо все восемь статусов, считающихся откликом, и все шесть,
считающихся ответом. Доли выходят 80, 50 и 75 — и две последние не совпадают
с долями от общего числа, 40 и 30.
"""


@pytest.mark.parametrize(
    ("part", "whole", "expected"),
    [
        pytest.param(1, 0, None, id="делить не на что"),
        pytest.param(0, 0, None, id="ничего из ничего"),
        pytest.param(1, -1, None, id="отрицательное целое"),
        pytest.param(0, 5, 0, id="ноль из пяти"),
        pytest.param(5, 5, 100, id="всё"),
        pytest.param(1, 3, 33, id="округление вниз"),
        pytest.param(2, 3, 67, id="округление вверх"),
        pytest.param(1, 8, 12, id="ровно половина от чётного вниз"),
        pytest.param(3, 8, 38, id="ровно половина от нечётного вверх"),
    ],
)
def test_a_share_is_a_whole_percent_or_nothing(part, whole, expected):
    """Доля считается целыми процентами, а при пустом основании её нет вовсе.

    Ноль вместо отсутствия соврал бы: «0% откликов» у канала, откуда ещё
    ничего не подошло, читается как провал, а на деле мерить нечего.

    Ровная половина округляется к чётному, а не всегда вверх: 12,5 даёт 12,
    а 37,5 — 38. Так работает округление в питоне, и на воронке это видно
    при восьми вакансиях.
    """
    assert percent_or_none(part, whole) == expected


async def test_a_missing_channel_has_no_card(session, session_factory):
    """У несуществующего канала карточки нет, и это не ошибка."""
    await put(session_factory, channel_row())

    assert await get_channel_detail(session, 10_000) is None


async def test_an_empty_channel_has_no_shares_at_all(session, session_factory):
    """У канала без вакансий долей нет ни одной, а счётчики нулевые."""
    channel = channel_row()
    await put(session_factory, channel)

    card = await get_channel_detail(session, channel.id)

    assert card.stats.total == 0
    assert card.stats.vacancies_per_day == 0.0
    assert card.stats.fit_percent is None
    assert card.stats.apply_percent is None
    assert card.stats.response_percent is None
    assert card.blacklist_value is None


async def test_the_status_counts_cover_every_status(session, session_factory):
    """В разбивке названы все статусы, включая те, которых в канале нет.

    Экран рисует воронку постоянным набором столбцов: пропущенный статус
    сдвинул бы их и сломал сравнение каналов между собой.
    """
    channel = channel_row()
    await put(session_factory, channel)
    await put(
        session_factory,
        vacancy_row(source_channel_id=channel.id, status=VacancyStatus.NEW),
        vacancy_row(source_channel_id=channel.id, status=VacancyStatus.NEW),
        vacancy_row(source_channel_id=channel.id, status=VacancyStatus.OFFER),
    )

    card = await get_channel_detail(session, channel.id)

    assert len(card.stats.status_counts) == len(VacancyStatus)
    assert card.stats.status_counts["New"] == 2
    assert card.stats.status_counts["Offer"] == 1
    assert card.stats.status_counts["Ghosting"] == 0


async def test_the_funnel_counts_each_step_from_the_previous_one(
    session, session_factory
):
    """Каждая ступень воронки считается от предыдущей, а не от общего числа.

    Набор: двадцать вакансий. Четыре отсеяны как неподходящие, значит
    подошло шестнадцать — 80% от двадцати. Из шестнадцати откликнулись на
    восемь — 50% от шестнадцати, а не 40% от двадцати. Из восьми ответили на
    шесть — 75% от восьми, а не 30% от двадцати.

    Доля подошедшего от общего совпадает с долей от предыдущей ступени по
    определению: предыдущей ступени у неё нет. Две остальные подобраны так,
    чтобы расходиться.

    Все восемь статусов, считающихся откликом, и все шесть, считающихся
    ответом, названы в наборе поимённо: с двумя-тремя выпадение любого
    из остальных прошло бы незамеченным.
    """
    channel = channel_row()
    await put(session_factory, channel)
    await put(
        session_factory,
        *[
            vacancy_row(source_channel_id=channel.id, status=s)
            for s in _FUNNEL_SET
        ],
    )

    card = await get_channel_detail(session, channel.id)

    assert card.stats.total == 20
    assert card.stats.fit_percent == 80
    assert card.stats.apply_percent == 50
    assert card.stats.response_percent == 75


async def test_a_neighbouring_channels_vacancies_are_not_counted(
    session, session_factory
):
    """Вакансии соседнего канала в счёт не идут."""
    mine = channel_row(username="mine")
    other = channel_row(username="other")
    await put(session_factory, mine, other)
    await put(
        session_factory,
        vacancy_row(source_channel_id=mine.id),
        vacancy_row(source_channel_id=other.id),
        vacancy_row(source_channel_id=None),
    )

    card = await get_channel_detail(session, mine.id)

    assert card.stats.total == 1


async def test_the_daily_rate_counts_only_the_last_thirty_days(
    session, session_factory
):
    """Темп считается по последним тридцати дням, а не по всей истории.

    Пятнадцать свежих вакансий за тридцать дней дают пол-вакансии в день.
    Старых столько же, и в счёт они не идут — иначе давно заглохший канал
    выглядел бы вдвое живее, чем есть.

    Проверено мутацией: с одной старой вакансией отсечка снималась молча —
    шестнадцать за тридцать дней после округления до десятых дают те же
    полвакансии, что и пятнадцать.
    """
    channel = channel_row()
    await put(session_factory, channel)
    await put(
        session_factory,
        *[
            vacancy_row(source_channel_id=channel.id, created_at=days_ago(1))
            for _ in range(15)
        ],
        *[
            vacancy_row(source_channel_id=channel.id, created_at=days_ago(200))
            for _ in range(15)
        ],
    )

    card = await get_channel_detail(session, channel.id)

    assert card.stats.total == 30
    assert card.stats.vacancies_per_day == 0.5


async def test_an_unparsed_vacancy_is_counted_nowhere_on_the_card(
    session, session_factory
):
    """Недоразобранная вакансия не идёт ни в воронку, ни в темп.

    Числа карточки обещают то же, что человек увидит в выдаче. Пока разбор
    не прошёл, у строки нет ни названия, ни оценки, а статус стоит начальный
    — посчитанная, она добавляла бы каналу и «New», и долю подошедшего, за
    которыми ничего нет.
    """
    channel = channel_row()
    await put(session_factory, channel)
    await put(
        session_factory,
        vacancy_row(source_channel_id=channel.id, created_at=days_ago(1)),
        vacancy_row(
            source_channel_id=channel.id,
            created_at=days_ago(1),
            is_parsed=False,
            title=None,
        ),
    )

    card = await get_channel_detail(session, channel.id)

    assert card.stats.total == 1
    assert card.stats.status_counts["New"] == 1
    assert card.stats.vacancies_per_day == 0.0


async def test_the_card_shows_an_active_mark_of_its_own_kind(
    session, session_factory
):
    """Отметка показывается, только если она включена и заведена для канала."""
    listed, switched_off, other_kind = marked_channels()
    await put(session_factory, listed, switched_off, other_kind)
    await put(session_factory, *channel_marks())

    assert (await get_channel_detail(session, listed.id)).blacklist_value == "@listed"
    assert (await get_channel_detail(session, switched_off.id)).blacklist_value is None
    assert (await get_channel_detail(session, other_kind.id)).blacklist_value is None
