"""Заведение вакансии руками — набранной в окне, а не найденной в канале.

Своим модулем, а не строкой в соседних: заведение из текста живёт в
`flows/ingest` и `flows/pasted`, а `vacancies_life` объявлен про то, что
случается с вакансией уже после заведения. Общего у них нет ничего, кроме
таблицы: там текст объявления с отпечатком и разбором, здесь — форма, в
которой человек всё назвал сам.
"""

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from backend.domain.salary import salary_text
from backend.domain.scoring import score_stack
from backend.domain.stack import deduped_halves, joined_stack
from backend.models import Vacancy
from backend.repository.profile_skills import list_skills
from backend.repository.vacancies_life import add_vacancy_event

logger = logging.getLogger(__name__)

HAND_MADE = "created_by_hand"
"""Род события ленты у заведённой руками.

Именем, а не литералом у места записи: в окне тот же род переводится в слова
(`state/vacancy_card.js`), и когда роды разъезжаются, лента показывает
человеку латиницу вместо фразы. Сторожа на это нет — есть одно имя здесь, по
которому расхождение видно поиском.
"""


async def create_vacancy(session: AsyncSession, fields: dict) -> int:
    """Завести вакансию по набранному в окне и назвать её номер.

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
    session.add(vacancy)
    await session.flush()
    await add_vacancy_event(session, vacancy.id, HAND_MADE)
    logger.info("Created vacancy id=%d by hand title=%r", vacancy.id, fields["title"])
    return vacancy.id
