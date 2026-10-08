"""Следствия домена статистики: чей ответ и за какой срок приходит в окно.

**Своего дела у этих пяти методов нет** — они пересказывают окну то, что
посчитал бэкенд, и каждый подсчёт уже сторожит свой файл в `tests/backend/`.
Проверять здесь числа значило бы держать те же сторожа дважды: два рецензента
разобрали первую редакцию этого файла и нашли в ней семь таких повторов.

Мосту принадлежит другое, и ломается оно молча: **кому уходит ответ и за какой
срок он посчитан.** Перепутанное чтение приведёт числа не туда — кольцо
нарисуется по воронке; потерянное эхо срока не даст окну отличить свежий ответ
от опоздавшего, и на экране за неделю окажутся числа за год.

Зовётся мост из чужого потока, потому что ответ он теперь отдаёт значением и
ждёт его: pywebview зовёт метод так же, из своего потока, а не из цикла мотора.
"""

from tests.dbio import put
from tests.factories import channel_row, vacancy_row


async def test_the_totals_come_back_with_their_own_period(api, ask):
    """Показатели приходят своим чтением и со своим сроком."""
    answer = await ask(api.stats.kpi, "week")

    assert answer["ok"]["period"] == "week"
    assert "applied_total" in answer["ok"]


async def test_the_breakdown_comes_back_with_its_own_period(api, ask):
    """Разбивка по положениям приходит своим чтением и со своим сроком."""
    answer = await ask(api.stats.status_breakdown, "month")

    assert answer["ok"]["period"] == "month"
    assert "counts" in answer["ok"]


async def test_the_replies_come_back_with_their_own_period(api, ask):
    """Ответы HR приходят своим чтением и со своим сроком."""
    answer = await ask(api.stats.hr_responses, "quarter")

    assert answer["ok"]["period"] == "quarter"
    assert "by_weekday" in answer["ok"]


async def test_the_skills_come_back_with_their_own_period(api, ask):
    """Спрос на навыки приходит своим чтением и со своим сроком."""
    answer = await ask(api.stats.skills, "today")

    assert answer["ok"]["period"] == "today"
    assert "skills" in answer["ok"]


async def test_the_funnel_comes_back_with_its_own_period(api, ask):
    """Воронка каналов приходит своим чтением и со своим сроком."""
    answer = await ask(api.stats.channels_pipeline, "all")

    assert answer["ok"]["period"] == "all"
    assert "channels" in answer["ok"]


async def test_an_unknown_period_answers_instead_of_falling_silent(api, ask):
    """Незнакомый срок не роняет ответ и возвращается эхом.

    Срок приходит строкой из окна, и разойдись наборы — экран остался бы с
    вечным ожиданием вместо чисел. Молчание тут хуже неточности. Во что
    репозиторий сводит незнакомое слово, сторожит он сам; мосту принадлежит то,
    что ответ вообще есть и что в нём то самое слово, которое спрашивали.
    """
    answer = await ask(api.stats.kpi, "позавчера")

    assert "fail" not in answer
    assert answer["ok"]["period"] == "позавчера"


async def test_the_counted_records_reach_the_window(api, ask, session_factory):
    """Посчитанное доезжает до окна, а не теряется по дороге.

    Числа считает бэкенд, но между ним и экраном лежит сборка ответа: она
    складывает словарь и заворачивает его в конверт. Сложись он пустым — экран
    показал бы нули на непустой базе, и человек решил бы, что работа за месяц
    пропала.
    """
    channel = channel_row(username="pyjobs", title="Питон-вакансии")
    await put(session_factory, channel)
    await put(session_factory, vacancy_row(source_channel_id=channel.id))

    answer = await ask(api.stats.channels_pipeline, "all")

    assert [row["title"] for row in answer["ok"]["channels"]] == ["Питон-вакансии"]
