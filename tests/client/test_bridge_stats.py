"""Следствия слотов статистики: чей ответ и за какой срок приходит в окно.

**Своего дела у этих пяти слотов нет** — они пересказывают окну то, что
посчитал бэкенд, и каждый подсчёт уже сторожит свой файл в `tests/backend/`.
Проверять здесь числа значило бы держать те же сторожа дважды: два рецензента
разобрали первую редакцию этого файла и нашли в ней семь таких повторов.

Мосту принадлежит другое, и ломается оно молча: **кому уходит ответ и за какой
срок он посчитан.** Перепутанный сигнал приведёт числа в чужой обработчик —
кольцо нарисуется по воронке; потерянное эхо срока не даст окну отличить
свежий ответ от опоздавшего, и на экране за неделю окажутся числа за год.
"""

from tests.dbio import put
from tests.factories import channel_row, vacancy_row


async def test_the_totals_come_back_on_their_own_signal(main_api, watch):
    """Показатели приходят своим сигналом и со своим сроком."""
    caught = watch(main_api.stats_kpi_loaded)

    main_api.request_stats_kpi("week")

    answer = await caught.next()
    assert answer["period"] == "week"
    assert "applied_total" in answer


async def test_the_breakdown_comes_back_on_its_own_signal(main_api, watch):
    """Разбивка по положениям приходит своим сигналом и со своим сроком."""
    caught = watch(main_api.stats_status_breakdown_loaded)

    main_api.request_stats_status_breakdown("month")

    answer = await caught.next()
    assert answer["period"] == "month"
    assert "counts" in answer


async def test_the_replies_come_back_on_their_own_signal(main_api, watch):
    """Ответы HR приходят своим сигналом и со своим сроком."""
    caught = watch(main_api.stats_hr_responses_loaded)

    main_api.request_stats_hr_responses("quarter")

    answer = await caught.next()
    assert answer["period"] == "quarter"
    assert "by_weekday" in answer


async def test_the_skills_come_back_on_their_own_signal(main_api, watch):
    """Спрос на навыки приходит своим сигналом и со своим сроком."""
    caught = watch(main_api.stats_skills_loaded)

    main_api.request_stats_skills("today")

    answer = await caught.next()
    assert answer["period"] == "today"
    assert "skills" in answer


async def test_the_funnel_comes_back_on_its_own_signal(main_api, watch):
    """Воронка каналов приходит своим сигналом и со своим сроком."""
    caught = watch(main_api.stats_channels_pipeline_loaded)

    main_api.request_stats_channels_pipeline("all")

    answer = await caught.next()
    assert answer["period"] == "all"
    assert "channels" in answer


async def test_an_unknown_period_answers_instead_of_falling_silent(main_api, watch):
    """Незнакомый срок не роняет ответ, а считается «за всё время».

    Срок приходит строкой из окна, и разойдись наборы — экран остался бы с
    вечным ожиданием вместо чисел. Молчание тут хуже неточности: числа за всё
    время человек хотя бы увидит.
    """
    caught = watch(main_api.stats_kpi_loaded)

    main_api.request_stats_kpi("позавчера")

    answer = await caught.next()
    assert answer["ok"] is True
    assert answer["period"] == "позавчера"


async def test_the_counted_records_reach_the_window(
    main_api, watch, session_factory
):
    """Посчитанное доезжает до окна, а не теряется по дороге.

    Числа считает бэкенд, но между ним и экраном лежит сборка ответа: она
    складывает словарь и переводит его в строку. Сложись он пустым — экран
    показал бы нули на непустой базе, и человек решил бы, что работа за
    месяц пропала.
    """
    caught = watch(main_api.stats_channels_pipeline_loaded)
    channel = channel_row(username="pyjobs", title="Питон-вакансии")
    await put(session_factory, channel)
    await put(session_factory, vacancy_row(source_channel_id=channel.id))

    main_api.request_stats_channels_pipeline("all")

    channels = (await caught.next())["channels"]
    assert [row["label"] for row in channels] == ["Питон-вакансии"]
