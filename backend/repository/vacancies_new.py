"""Запись заведённой вакансии: строка с событием заведения, форма окна, признак ручной.

Своим модулем, а не строкой в соседних: `vacancies_life` объявлен про то, что
случается с вакансией уже после заведения. Строку из текста объявления
собирают `flows/ingest`, `flows/pasted` и искатель, а ложится она отсюда же,
одной связкой со своим событием; форма окна, в которой человек всё назвал
сам, собирается здесь целиком.
"""

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.domain.salary import salary_text
from backend.domain.scoring import score_stack
from backend.domain.stack import deduped_halves, joined_stack
from backend.models import Vacancy, VacancyEvent
from backend.repository.profile_skills import list_skills
from backend.repository.vacancies_life import add_vacancy_event, vacancy_at_address

logger = logging.getLogger(__name__)

HAND_MADE = "created_by_hand"
"""Род события ленты у заведённой руками.

Именем, а не литералом у места записи: в окне тот же род переводится в слова
(`state/vacancy_card.js`), и когда роды разъезжаются, лента показывает
человеку латиницу вместо фразы. Сторожа на это нет — есть одно имя здесь, по
которому расхождение видно поиском.
"""


async def made_by_hand(session: AsyncSession, vacancy_id: int) -> bool:
    """Заведена ли вакансия человеком — по событию её заведения в ленте.

    Признак живёт у самой строки, а не в окне: разбор, подбор недоразобранного
    и прогон заново узнают его отсюда, когда окна давно нет.
    """
    found = await session.scalar(select(VacancyEvent.id).where(
        VacancyEvent.vacancy_id == vacancy_id, VacancyEvent.kind == HAND_MADE
    ).limit(1))
    return found is not None


async def add_with_event(
    session: AsyncSession, vacancy: Vacancy, kind: str, payload: dict | None = None
) -> None:
    """Записать строку вместе с событием её заведения; номер ложится в строку.

    Одно место на всех, кто заводит: событие и строка ложатся одной сделкой, и
    строка без события выглядела бы взявшейся ниоткуда. Оборот — зовущего.
    """
    session.add(vacancy)
    await session.flush()
    await add_vacancy_event(session, vacancy.id, kind, payload)


async def create_vacancy(session: AsyncSession, fields: dict) -> tuple[int, bool]:
    """Завести вакансию по набранному в окне; номер и заведена ли она.

    «Ссылка на объявление» ведёт на страницу уже заведённой вакансии — это
    повтор: строка не пишется, в ответ номер существующей и `False`.

    Поля приходят одним объектом, каким их прочитала форма
    (`bridge/form_payloads.read_new_vacancy_fields`): колонки они называют
    точно — кроме двух половин стека, которые потому и вынимаются.
    `is_parsed` ставится сразу: человеку показывают только разобранные строки
    (`vacancies_common.PARSED_ONLY`), а разбирать здесь нечего — набранное
    человеком и есть готовый разбор.

    Строка зарплаты складывается из набранных чисел: колонка `salary` хранит
    написанное автором объявления, а у заведённой руками вакансии автор — сам
    человек. Балл считается здесь же и до склейки половин: список сортируют и
    отбирают по нему, а половины весят по-разному.

    Оборот открывает зовущий.
    """
    if fields.get("source_url"):
        existing = await vacancy_at_address(session, fields["source_url"])
        if existing is not None:
            logger.info("vacancy by hand: page %s is vacancy %d", fields["source_url"], existing)
            return existing, False
    # Свой набор: половины стека из него вынимаются, а объект чужой.
    fields = dict(fields)
    required, preferred = deduped_halves(
        fields.pop("stack_required"), fields.pop("stack_preferred")
    )
    # Исходный текст остаётся пустым: набранное человеком описание — пересказ,
    # а не объявление, и выдай его за исходник, повторный разбор пересказал бы
    # пересказ, стирая набранное поверх собственной догадки.
    vacancy = Vacancy(
        **fields,
        stack=joined_stack(required, preferred),
        score=score_stack(required, preferred, await list_skills(session)),
        salary=salary_text(
            fields["salary_min"], fields["salary_max"], fields["salary_currency"]
        ),
        is_parsed=True,
    )
    await add_with_event(session, vacancy, HAND_MADE)
    logger.info("Created vacancy id=%d by hand title=%r", vacancy.id, fields["title"])
    return vacancy.id, True
