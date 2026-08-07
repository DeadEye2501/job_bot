"""Следствия двух справочных запросов по вакансиям.

Первый собирает значения для выпадающих списков отбора, второй — метку
последней активности сразу для многих вакансий. Оба обслуживают экран списка,
но данных вакансий не отдают: один возвращает названия, другой — времена.
"""

from backend.repository import list_vacancy_filter_options, list_vacancy_last_activity
from tests.dbio import put
from tests.factories import (
    at,
    channel_row,
    company_row,
    status_history_row,
    vacancy_event_row,
    vacancy_row,
)


async def test_only_channels_with_a_parsed_vacancy_are_offered(session, session_factory):
    """В списке каналов только те, у кого есть хоть одна разобранная вакансия."""
    used = channel_row(username="pyjobs")
    unparsed_only = channel_row(username="halfdone")
    empty = channel_row(username="silent")
    await put(session_factory, used, unparsed_only, empty)
    await put(
        session_factory,
        vacancy_row(source_channel_id=used.id, is_parsed=True),
        vacancy_row(source_channel_id=unparsed_only.id, is_parsed=False),
    )

    options = await list_vacancy_filter_options(session)

    assert options["channels"] == ["pyjobs"]


async def test_a_channel_without_a_username_is_not_offered(session, session_factory):
    """Канал без имени пользователя в списке не появляется."""
    named = channel_row(username="pyjobs")
    nameless = channel_row(username=None, title="Закрытый канал")
    await put(session_factory, named, nameless)
    await put(
        session_factory,
        vacancy_row(source_channel_id=named.id),
        vacancy_row(source_channel_id=nameless.id),
    )

    options = await list_vacancy_filter_options(session)

    assert options["channels"] == ["pyjobs"]


async def test_two_channel_spellings_collapse_into_one_option(
    titles, session, session_factory
):
    """Два написания одного имени канала дают одну строку списка.

    Первая проверка — контрольная, и без неё вторая ничего не доказывала бы:
    одна строка вышла бы и тогда, когда второй канал просто не попал в
    выборку. Обе вакансии видны, значит обе привязки живы, и единственная
    причина одной строки — схлопывание написаний.

    Какое из написаний останется, решает порядок выдачи базы, и закреплять
    его тестом значило бы закреплять случайность.
    """
    upper = channel_row(username="PyJobs")
    lower = channel_row(username="pyjobs")
    await put(session_factory, upper, lower)
    await put(
        session_factory,
        vacancy_row(title="через заглавное", source_channel_id=upper.id),
        vacancy_row(title="через строчное", source_channel_id=lower.id),
    )

    assert len(await titles()) == 2

    options = await list_vacancy_filter_options(session)

    assert len(options["channels"]) == 1
    assert options["channels"][0].lower() == "pyjobs"


async def test_companies_come_from_both_the_linked_row_and_the_raw_name(
    session, session_factory
):
    """В списке компаний и связанные строки, и сырые названия непривязанных."""
    linked = company_row(name="Контур")
    await put(session_factory, linked)
    await put(
        session_factory,
        vacancy_row(company_id=linked.id),
        vacancy_row(company_name="Ромашка"),
    )

    options = await list_vacancy_filter_options(session)

    assert sorted(options["companies"]) == sorted(["Контур", "Ромашка"])


async def test_a_company_named_by_both_paths_appears_once(
    titles, session, session_factory
):
    """Компания, названная и связью, и сырым полем, даёт одну строку списка.

    Первая проверка контрольная: одна строка вышла бы и тогда, когда второй
    путь вовсе не просматривается. Обе вакансии видны — значит просматриваются
    оба, и единственная причина одной строки — схлопывание написаний.
    """
    linked = company_row(name="Контур")
    await put(session_factory, linked)
    await put(
        session_factory,
        vacancy_row(title="через связь", company_id=linked.id),
        vacancy_row(title="через сырое поле", company_name="контур"),
    )

    assert len(await titles()) == 2

    options = await list_vacancy_filter_options(session)

    assert len(options["companies"]) == 1


async def test_a_blank_or_dashed_company_name_is_not_offered(session, session_factory):
    """Пустое название и прочерк в списке компаний не появляются."""
    await put(
        session_factory,
        vacancy_row(company_name="   Контур  "),
        vacancy_row(company_name="—"),
        vacancy_row(company_name="   "),
        vacancy_row(company_name=None),
    )

    options = await list_vacancy_filter_options(session)

    assert options["companies"] == ["Контур"]


async def test_an_unparsed_vacancy_contributes_no_company(session, session_factory):
    """Недоразобранная вакансия своего названия компании в список не отдаёт."""
    await put(
        session_factory,
        vacancy_row(company_name="Разобранная", is_parsed=True),
        vacancy_row(company_name="Брошенная", is_parsed=False),
    )

    options = await list_vacancy_filter_options(session)

    assert options["companies"] == ["Разобранная"]


async def test_no_ids_asked_means_no_activity_returned(session, session_factory):
    """Пустой запрос активности не идёт в базу и возвращает пустой ответ."""
    await put(session_factory, vacancy_row())

    assert await list_vacancy_last_activity(session, []) == {}
    assert await list_vacancy_last_activity(session, [None]) == {}


async def test_an_unknown_id_is_simply_absent_from_the_answer(session, session_factory):
    """Идентификатор, которого нет в базе, в ответе просто отсутствует."""
    known = vacancy_row(created_at=at(10))
    await put(session_factory, known)

    got = await list_vacancy_last_activity(session, [known.id, known.id + 1000])

    assert list(got) == [known.id]


async def test_activity_is_the_latest_of_the_four_sources(session, session_factory):
    """Метка активности — наибольшее из четырёх времён, каждое умеет победить."""
    by_created = vacancy_row(created_at=at(10))
    by_posted = vacancy_row(created_at=at(10), posted_at=at(20))
    by_event = vacancy_row(created_at=at(10))
    by_status = vacancy_row(created_at=at(10))
    await put(session_factory, by_created, by_posted, by_event, by_status)
    await put(
        session_factory,
        vacancy_event_row(by_event.id, created_at=at(30)),
        status_history_row(by_status.id, changed_at=at(40)),
    )

    got = await list_vacancy_last_activity(
        session, [by_created.id, by_posted.id, by_event.id, by_status.id]
    )

    assert got == {
        by_created.id: at(10),
        by_posted.id: at(20),
        by_event.id: at(30),
        by_status.id: at(40),
    }


async def test_the_latest_event_wins_when_there_is_no_status_history(
    session, session_factory
):
    """Из нескольких событий берётся самое позднее и тогда, когда истории нет вовсе.

    Проверено мутацией: в соседнем тесте, где есть и события, и история,
    сведение событий подменялось наименьшим молча — итог всё равно решала
    история, чьё время было позже. Здесь истории нет, и подмена видна.
    """
    vacancy = vacancy_row(created_at=at(0))
    await put(session_factory, vacancy)
    await put(
        session_factory,
        vacancy_event_row(vacancy.id, created_at=at(30)),
        vacancy_event_row(vacancy.id, created_at=at(10)),
    )

    assert await list_vacancy_last_activity(session, [vacancy.id]) == {
        vacancy.id: at(30)
    }


async def test_the_latest_is_taken_from_each_group_of_records(
    session, session_factory
):
    """Из каждой группы записей берётся самая поздняя, а не первая и не последняя.

    Сведение идёт двумя отдельными запросами — по событиям и по сменам
    статуса, — и оба здесь нагружены двумя записями сразу. Время создания
    вакансии выбрано раньше всех четырёх нарочно: будь оно позже, ответ
    совпал бы при любом сведении, и проверять было бы нечего. Поздние записи
    вставлены раньше ранних, поэтому наибольшее, наименьшее и последнее
    вставленное дают три разных ответа: 40, 10 и 20.
    """
    vacancy = vacancy_row(created_at=at(0))
    await put(session_factory, vacancy)
    await put(
        session_factory,
        vacancy_event_row(vacancy.id, created_at=at(30)),
        vacancy_event_row(vacancy.id, created_at=at(10)),
        status_history_row(vacancy.id, changed_at=at(40)),
        status_history_row(vacancy.id, changed_at=at(20)),
    )

    got = await list_vacancy_last_activity(session, [vacancy.id])

    assert got == {vacancy.id: at(40)}
