"""Следствия признака продолжения — того, по которому окно решает, просить ли ещё.

Четыре экрана грузят списки бесконечной прокруткой, и у всех четырёх один
вопрос к мосту: кончились строки или нет. Ответ на него знает только запрос —
тот, кто отрезал страницу, — а выведенный из длины страницы он врёт ровно на
полной: столько строк, сколько просили, значит «ровно столько и было» так же
часто, как «есть ещё».

Своим файлом, потому что предмет здесь один на четыре экрана. У соседей
предмет другой: `test_bridge_vacancies.py` — что умеет вакансия сама по себе,
`test_bridge_list_payload.py` — как прочитана нагрузка запроса. Здесь же
проверяется ответ, и одинаковый у всех четверых.
"""

from tests.dbio import put
from tests.factories import channel_row, company_row, hr_row, vacancy_row


async def test_a_full_page_of_vacancies_does_not_promise_more(
    api, ask, session_factory
):
    """Полная страница вакансий не обещает продолжения, которого нет.

    Обещай она — окно уйдёт за следующей страницей и получит пустую: человек
    увидит вечный «загружаем ещё» под последней вакансией.
    """
    await put(session_factory, *[vacancy_row(title=f"Вакансия {i}") for i in range(3)])

    assert (await ask(api.vacancies.list, {"limit": 3}))["ok"]["has_more"] is False

    assert (await ask(api.vacancies.list, {"limit": 2}))["ok"]["has_more"] is True


async def test_a_full_page_of_people_does_not_promise_more(
    api, ask, session_factory
):
    """То же на экране людей: страница вровень с найденным — это конец списка."""
    await put(session_factory, *[hr_row(name=f"Человек {i}") for i in range(3)])

    assert (await ask(api.hr.list, {"limit": 3}))["ok"]["has_more"] is False

    assert (await ask(api.hr.list, {"limit": 2}))["ok"]["has_more"] is True


async def test_a_full_page_of_companies_does_not_promise_more(
    api, ask, session_factory
):
    """То же на экране компаний."""
    await put(session_factory, *[company_row(name=f"Компания {i}") for i in range(3)])

    assert (await ask(api.companies.list, {"limit": 3}))["ok"]["has_more"] is False

    assert (await ask(api.companies.list, {"limit": 2}))["ok"]["has_more"] is True


async def test_a_full_page_of_channel_vacancies_does_not_promise_more(
    api, ask, session_factory
):
    """То же в карточке канала, где вакансий копятся тысячи."""
    channel = channel_row()
    await put(session_factory, channel)
    await put(
        session_factory,
        *[
            vacancy_row(title=f"Вакансия {i}", source_channel_id=channel.id)
            for i in range(3)
        ],
    )

    asked = {"channel_id": channel.id, "limit": 3}
    assert (await ask(api.channels.vacancies, asked))["ok"]["has_more"] is False

    asked = {"channel_id": channel.id, "limit": 2}
    assert (await ask(api.channels.vacancies, asked))["ok"]["has_more"] is True
