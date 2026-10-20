"""Повтор ручного заведения: заведена ли уже вакансия, которую приносит человек.

Отдельно от потока ручного заведения (`hand_made`), потому что правило зовут и
те, кого поток сам ввозит, — приём вставленного текста и искатель страницы.
"""

from collections.abc import Awaitable, Callable
from functools import partial

from backend.flows import cleanup, parse
from backend.flows.hand_outcome import tell
from backend.repository.vacancies_life import vacancies_at_address


async def addressed(session_factory, url: str | None) -> list[int]:
    """Вакансии с этим собственным адресом; без адреса — ни одной."""
    if not url:
        return []
    async with session_factory() as session:
        return await vacancies_at_address(session, url)


async def known_among(
    session_factory, vacancy_ids: list[int], forget: Callable[[int], Awaitable[object]]
) -> int | None:
    """Первая разобранная из этих вакансий; недоразобранные до неё снесены.

    Разобранная — повтор: окно переходит на неё. Недоразобранная прав не имеет
    — в списке её не видно, и переходить было бы некуда, — её сносят (`forget`),
    а заведение идёт заново тем, что принёс человек. Сносят разные руки: у бота
    — вместе с отпечатком в его кэше, у моста без бота кэша нет вовсе.
    """
    for vacancy_id in vacancy_ids:
        state = await parse.is_parsed(session_factory, vacancy_id)
        if state:
            return vacancy_id
        if state is False:
            await forget(vacancy_id)
    return None


async def known_and_told(pipeline, vacancy_ids: list[int]) -> bool:
    """Повтор ли это у бота (`known_among`); да — окну сказано."""
    known = await known_among(pipeline.session_factory, vacancy_ids, partial(cleanup.forget_vacancy, pipeline))
    if known is not None:
        tell(pipeline, "duplicate", known)
    return known is not None
