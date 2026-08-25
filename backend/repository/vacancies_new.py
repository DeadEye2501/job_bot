"""Заведение вакансии руками — набранной в окне, а не найденной в канале.

Своим модулем, а не строкой в соседних: заведение конвейером живёт в
`flows/ingest`, а `vacancies_life` объявлен про то, что случается с вакансией
уже после заведения. Общего у двух заведений нет ничего, кроме таблицы: там
пост канала с эмбеддингом и курсором, здесь — форма без источника вовсе.
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
    точно — кроме двух половин стека, которые потому и вынимаются, — а
    разложенные по доводам переписали бы тот же перечень второй раз.

    `is_parsed` ставится сразу: человеку показывают только разобранные строки
    (`vacancies_common.PARSED_ONLY`), а разбирать здесь нечего — набранное
    человеком и есть готовый разбор.

    Строка зарплаты складывается из набранных чисел: колонка `salary` хранит
    написанное автором объявления, а у заведённой руками вакансии автор — сам
    человек. Числа при этом ложатся как есть — по ним идёт отбор по вилке.

    Балл считается здесь, а не остаётся пустым: список сортируют и отбирают
    по нему, и строка без балла осела бы в хвосте рядом с теми, у кого разбор
    не удался. Считается он до склейки половин — весят они по-разному.

    Оборот открывает зовущий.
    """
    # Свой набор: половины стека из него вынимаются, а объект чужой.
    fields = dict(fields)
    required, preferred = deduped_halves(
        fields.pop("stack_required"), fields.pop("stack_preferred")
    )
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
