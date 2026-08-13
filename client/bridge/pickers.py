"""Списки кандидатов, которые окно показывает в модалке выбора.

Их две породы, и обе написаны по многу раз. Подборщик слияния спрашивает, в
кого влить эту карточку, — он одинаков у человека и у компании до последней
строки, включая правило «поглощаемого в списке не показывать». Подборщик
привязки спрашивает, кого прицепить к вакансии, — его нагрузка собрана
четырьмя телами в одном файле, причём формы двух из них обязаны сходиться:
они уезжают в один и тот же сигнал.

Отличие от `mark.py` по соседству: там предмет отмечают, здесь его выбирают,
и предметы описаны таблицей по той же причине — своё у них только имя ключа,
объявление перечня и то, чем строка называет себя. Таблица при этом одна на
предмет, а не по одной на породу подборщика: обе породы рисует одна и та же
модалка.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from backend.repository import companies_list, hr_list
from client.bridge.wire import _company_picker_row_to_dict, _hr_picker_row_to_dict


@dataclass(frozen=True)
class PickerSubject:
    """Чем предмет называет себя подборщику — обоим сразу.

    Таблица одна на предмет, а не по одной на породу подборщика: тройка
    «имя ключа, перечень, во что превращается строка» у них общая, и
    разъехаться ей нельзя — модалка выбора у слияния и у привязки одна и та
    же.
    """

    key: str
    rows: Callable
    row_to_dict: Callable
    id_of: Callable
    current: str
    linked_id: Callable


HR_PICKER = PickerSubject(
    key="hrs",
    rows=hr_list.list_hr_with_counts,
    row_to_dict=_hr_picker_row_to_dict,
    id_of=lambda row: row.hr.id,
    current="current_hr_id",
    linked_id=lambda vacancy: vacancy.hr_id,
)

COMPANY_PICKER = PickerSubject(
    key="companies",
    rows=companies_list.list_companies_with_counts,
    row_to_dict=_company_picker_row_to_dict,
    id_of=lambda row: row.company.id,
    current="current_company_id",
    linked_id=lambda vacancy: vacancy.company_id,
)


async def merge_picker(
    session, subject: PickerSubject, absorbed_id: int, search: str | None
) -> dict:
    """Кандидаты, в которых можно влить эту карточку.

    Поглощаемый из списка убирается: влить карточку в саму себя нельзя, а
    показанная строка выглядит как разрешённый выбор.

    Строка поиска эхом уезжает обратно — окно рисует её в поле над списком, и
    без эха оно затирало бы набранное человеком на каждом ответе.
    """
    rows, _ = await subject.rows(session, search=search)
    return {
        "absorbed_id": absorbed_id,
        "search": search or "",
        subject.key: [
            subject.row_to_dict(row)
            for row in rows
            if subject.id_of(row) != absorbed_id
        ],
    }


async def link_picker(
    session, subject: PickerSubject, vacancy, search: str | None
) -> dict:
    """Кандидаты на привязку к вакансии и то, кто привязан сейчас.

    Уже привязанный отдаётся отдельным полем, а не отметкой в строке: окно
    подсвечивает его в списке, не спрашивая карточку вакансии второй раз.

    Вакансии может не быть вовсе — так бывает у заведения из подборщика,
    когда карточку успели удалить в соседнем окне; тогда привязанного нет, а
    список показать всё равно есть смысл.
    """
    rows, _ = await subject.rows(session, search=search)
    return {
        subject.current: subject.linked_id(vacancy) if vacancy is not None else None,
        "search": search or "",
        subject.key: [subject.row_to_dict(row) for row in rows],
    }
