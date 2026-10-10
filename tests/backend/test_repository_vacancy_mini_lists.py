"""Следствия трёх коротких списков вакансий, привязанных к одному владельцу.

Их показывают в боковой панели рядом с HR, компанией и каналом. Неразобранные
вакансии отсеивают все трое. Расхождение у них одно и намеренное: списки
HR и компании идут по времени, а список канала — по тому, насколько
горяч статус.
"""

from backend.models import VacancyStatus
from backend.repository.vacancies_mini import list_vacancies_for_company, list_vacancies_for_hr, list_vacancies_from
from tests.dbio import put
from tests.factories_aggregators import aggregator_row
from tests.factories import (
    at,
    channel_row,
    company_row,
    hr_row,
    vacancy_row,
)


async def test_the_hr_list_holds_only_that_hrs_parsed_vacancies(
    session, session_factory
):
    """В списке HR только его вакансии и только разобранные."""
    mine = hr_row(name="Мария")
    other = hr_row(name="Ольга")
    await put(session_factory, mine, other)
    await put(
        session_factory,
        vacancy_row(title="моя разобранная", hr_id=mine.id, is_parsed=True),
        vacancy_row(title="моя недоразобранная", hr_id=mine.id, is_parsed=False),
        vacancy_row(title="чужая", hr_id=other.id, is_parsed=True),
        vacancy_row(title="ничья", hr_id=None, is_parsed=True),
    )

    got = await list_vacancies_for_hr(session, mine.id)

    assert [v.title for v in got] == ["моя разобранная"]


async def test_the_hr_list_is_newest_first_and_breaks_ties_by_id(
    session, session_factory
):
    """Список HR идёт от новой вакансии к старой, а при равенстве — по идентификатору.

    Обе проверки нужны вместе: на одних только разных временах порядок по
    идентификатору совпал бы с порядком по времени, и разрешитель спора
    остался бы непроверенным.
    """
    hr = hr_row()
    await put(session_factory, hr)
    await put(
        session_factory,
        vacancy_row(title="старая", hr_id=hr.id, created_at=at(10)),
        vacancy_row(title="новая", hr_id=hr.id, created_at=at(30)),
        vacancy_row(title="одновременная первая", hr_id=hr.id, created_at=at(20)),
        vacancy_row(title="одновременная вторая", hr_id=hr.id, created_at=at(20)),
    )

    got = await list_vacancies_for_hr(session, hr.id)

    assert [v.title for v in got] == [
        "новая",
        "одновременная вторая",
        "одновременная первая",
        "старая",
    ]


async def test_the_company_list_holds_only_that_companys_parsed_vacancies(
    session, session_factory
):
    """В списке компании только её вакансии и только разобранные."""
    mine = company_row(name="Контур")
    other = company_row(name="Ромашка")
    await put(session_factory, mine, other)
    await put(
        session_factory,
        vacancy_row(title="моя разобранная", company_id=mine.id, is_parsed=True),
        vacancy_row(title="моя недоразобранная", company_id=mine.id, is_parsed=False),
        vacancy_row(title="чужая", company_id=other.id, is_parsed=True),
    )

    got = await list_vacancies_for_company(session, mine.id)

    assert [v.title for v in got] == ["моя разобранная"]


async def test_the_company_list_is_newest_first_and_breaks_ties_by_id(
    session, session_factory
):
    """Список компании идёт от новой вакансии к старой, а при равенстве — по идентификатору.

    Запрос у обоих списков теперь общий, а вот привязка своя: этот тест
    стережёт, что список компании отбирает по своей колонке и своим
    порядком, а не достался списку HR по случайности.
    """
    company = company_row(name="Контур")
    await put(session_factory, company)
    await put(
        session_factory,
        vacancy_row(title="старая", company_id=company.id, created_at=at(10)),
        vacancy_row(title="новая", company_id=company.id, created_at=at(30)),
        vacancy_row(title="одновременная первая", company_id=company.id, created_at=at(20)),
        vacancy_row(title="одновременная вторая", company_id=company.id, created_at=at(20)),
    )

    got = await list_vacancies_for_company(session, company.id)

    assert [v.title for v in got] == [
        "новая",
        "одновременная вторая",
        "одновременная первая",
        "старая",
    ]


async def test_the_channel_list_holds_only_the_parsed_ones(
    session, session_factory
):
    """В списке канала только разобранные вакансии — как и в двух других.

    Заведение и разбор — два шага конвейера, и между ними строка живёт без
    названия и без оценки. В выдачу она не попадает, поэтому её не показывает
    и мини-список: счётчик канала и его сводка считают ровно то же множество.
    """
    channel = channel_row(username="pyjobs")
    await put(session_factory, channel)
    await put(
        session_factory,
        vacancy_row(title="разобранная", source_channel_id=channel.id, is_parsed=True),
        vacancy_row(
            title="недоразобранная", source_channel_id=channel.id, is_parsed=False
        ),
    )

    got, _ = await list_vacancies_from(session, "channel", channel.id)

    assert [v.title for v in got] == ["разобранная"]


_HOTTEST_FIRST = [
    VacancyStatus.OFFER,
    VacancyStatus.IN_PROGRESS,
    VacancyStatus.INVITATION,
    VacancyStatus.TEST,
    VacancyStatus.ANSWERED,
    VacancyStatus.APPLIED,
    VacancyStatus.NEW,
    VacancyStatus.SCAM,
    VacancyStatus.GHOSTING,
    VacancyStatus.DECLINE,
    VacancyStatus.NOT_FIT,
]
"""Порядок, в котором статусы должны выйти из списка канала — все одиннадцать.

Названы поимённо все: на четырёх любую перестановку среди остальных семи
прогон бы не заметил.
"""


async def test_the_channel_list_leads_with_the_hottest_status(
    session, session_factory
):
    """Список канала идёт от самого горячего статуса к самому холодному.

    Вакансии кладутся в обратном ожидаемому порядке нарочно: если ранг
    статуса перестанет участвовать в сортировке вовсе, список выйдет в
    порядке появления, то есть ровно наоборот — и проверка покраснеет,
    а не совпадёт с ожидаемым по случайности.
    """
    channel = channel_row(username="pyjobs")
    await put(session_factory, channel)
    await put(
        session_factory,
        *[
            vacancy_row(
                title=status.value, source_channel_id=channel.id, status=status
            )
            for status in reversed(_HOTTEST_FIRST)
        ],
    )

    got, _ = await list_vacancies_from(session, "channel", channel.id)

    assert [v.title for v in got] == [s.value for s in _HOTTEST_FIRST]


async def test_inside_one_status_the_channel_list_prefers_the_posting_date(
    session, session_factory
):
    """Внутри одного статуса вперёд идёт вакансия с более поздней датой публикации.

    Дата появления — это дата публикации, если она есть, иначе дата создания.
    Здесь у первой она есть и она поздняя, у второй её нет вовсе, а создана та
    позже — значит совпадение с порядком по созданию исключено.
    """
    channel = channel_row(username="pyjobs")
    await put(session_factory, channel)
    await put(
        session_factory,
        vacancy_row(
            title="опубликована позже",
            source_channel_id=channel.id,
            created_at=at(10),
            posted_at=at(50),
        ),
        vacancy_row(
            title="создана позже",
            source_channel_id=channel.id,
            created_at=at(30),
            posted_at=None,
        ),
    )

    got, _ = await list_vacancies_from(session, "channel", channel.id)

    assert [v.title for v in got] == ["опубликована позже", "создана позже"]


async def test_the_channel_list_pages(session, session_factory):
    """Список канала выдаётся страницами: предел режет, смещение сдвигает.

    Порядок вставки нарочно не совпадает с порядком по времени. Совпади они —
    и тест не отличал бы страницы отсортированного списка от страниц выдачи
    вообще без сортировки: обе дали бы один ответ.
    """
    channel = channel_row(username="pyjobs")
    await put(session_factory, channel)
    await put(
        session_factory,
        vacancy_row(title="пятая", source_channel_id=channel.id, created_at=at(10)),
        vacancy_row(title="первая", source_channel_id=channel.id, created_at=at(50)),
        vacancy_row(title="четвёртая", source_channel_id=channel.id, created_at=at(20)),
        vacancy_row(title="вторая", source_channel_id=channel.id, created_at=at(40)),
        vacancy_row(title="третья", source_channel_id=channel.id, created_at=at(30)),
    )

    first, _ = await list_vacancies_from(session, "channel", channel.id, limit=2)
    second, _ = await list_vacancies_from(session, "channel", channel.id, limit=2, offset=2)

    assert [v.title for v in first] == ["первая", "вторая"]
    assert [v.title for v in second] == ["третья", "четвёртая"]


async def test_a_neighbouring_channels_vacancies_stay_out(session, session_factory):
    """Вакансии соседнего канала в список не попадают."""
    mine = channel_row(username="pyjobs")
    other = channel_row(username="jsjobs")
    await put(session_factory, mine, other)
    await put(
        session_factory,
        vacancy_row(title="моя", source_channel_id=mine.id),
        vacancy_row(title="чужая", source_channel_id=other.id),
        vacancy_row(title="ничья", source_channel_id=None),
    )

    got, _ = await list_vacancies_from(session, "channel", mine.id)

    assert [v.title for v in got] == ["моя"]


async def test_an_aggregators_list_holds_its_own_vacancies_not_a_channels(
    session, session_factory
):
    """Источник называют родом и номером: номер агрегатора не путается с номером канала."""
    channel = channel_row(username="pyjobs")
    site = aggregator_row(host="board.test")
    await put(session_factory, channel, site)
    await put(
        session_factory,
        vacancy_row(title="с агрегатора", source_aggregator_id=site.id),
        vacancy_row(title="из канала", source_channel_id=channel.id),
    )

    got, _ = await list_vacancies_from(session, "aggregator", site.id)

    assert [v.title for v in got] == ["с агрегатора"]
