"""Фикстуры, общие для тестов слоя `backend`."""

import pytest

from backend.repository import list_vacancies


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
        return [v.title for v in await list_vacancies(session, **kwargs)]

    return read
