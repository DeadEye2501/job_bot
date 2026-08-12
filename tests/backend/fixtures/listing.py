"""Перечни репозитория, сведённые к опознавательному знаку строки."""

import pytest

from backend.repository.channels import list_telegram_channels
from backend.repository.hr_list import list_hr_with_counts
from backend.payloads import VacancyFilter
from backend.repository.vacancies_list import list_vacancies


@pytest.fixture
def titles(session):
    """Заголовки отобранных `list_vacancies` вакансий в порядке выдачи.

    Список вакансий проверяется тремя слайсами — отбор, порядок, зарплата, —
    и каждый смотрит на одно и то же: какие строки вернулись и в каком
    порядке. Заголовок здесь опознавательный знак строки, а не предмет
    проверки, поэтому тесты задают его словами, называющими причину, по
    которой строка должна попасть в ответ или не попасть.
    """

    async def read(**kwargs) -> list[str]:
        return [
            v.title
            for v in await list_vacancies(session, VacancyFilter(**kwargs))
        ]

    return read


@pytest.fixture
def hr_names(session):
    """Имена HR в порядке выдачи — по прецеденту `titles`.

    Перечень HR проверяется отбором и порядком, и обоим нужно одно: кто
    вернулся и в каком порядке. Список компаний свёл бы сюда же, но у
    него другой предмет и другое объявление в репозитории.
    """

    async def read(**kwargs) -> list[str]:
        return [row.hr.name for row in await list_hr_with_counts(session, **kwargs)]

    return read


@pytest.fixture
def channel_titles(session):
    """Заголовки каналов в порядке выдачи — по тому же прецеденту."""

    async def read(**kwargs) -> list[str]:
        return [
            row.channel.title
            for row in await list_telegram_channels(session, **kwargs)
        ]

    return read
