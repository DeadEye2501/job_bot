"""Общее у слияния двух записей об одном предмете.

Сюда переехало то, что у слияния HR и слияния компаний совпадало дословно:
оба отказа, перенацеливание вакансий и склейка примечаний. Удаление строки со
сбросом и запись в журнал остались у потребителей — они короткие, а текст
записи у каждого свой.

Предметные поля сюда не затянуты вовсе: переписка и учётная запись Telegram у
HR, написания и сайт у компании остаются по местам.
"""

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import Vacancy


async def load_merge_pair(
    session: AsyncSession, model, *, absorbed_id: int, survivor_id: int, subject: str
):
    """Обе строки слияния, с отказом на слиянии записи самой с собой.

    `subject` попадает в текст обоих отказов: он доходит до окна подсказкой,
    и «not found» без предмета человек прочёл бы как беду неизвестно с чем.
    """
    if absorbed_id == survivor_id:
        raise ValueError(f"{subject}: absorbed_id == survivor_id")
    absorbed = await session.get(model, absorbed_id)
    survivor = await session.get(model, survivor_id)
    if absorbed is None or survivor is None:
        raise ValueError(
            f"{subject}: not found "
            f"(absorbed={absorbed_id}, survivor={survivor_id})"
        )
    return absorbed, survivor


async def repoint_vacancies(
    session: AsyncSession, column, *, absorbed_id: int, survivor_id: int
) -> int:
    """Перенацеливает вакансии поглощённой строки на оставшуюся.

    Возвращает число переехавших — его пишут в журнал: слияние необратимо, и
    по записи потом видно, сколько именно вакансий сменило владельца.

    Дом здесь, а не в `vacancies_mini`, где живут списки вакансий по владельцу:
    там читают, здесь переписывают владельца, и зовут это только слияния.
    """
    return (
        await session.execute(
            update(Vacancy).where(column == absorbed_id).values({column: survivor_id})
        )
    ).rowcount or 0


def concat_notes(survivor: str | None, absorbed: str | None) -> str | None:
    """Примечания обеих записей, склеенные через разделитель.

    Слияние необратимо, поэтому заметки поглощённой не выбрасываются: пустые
    отсеиваются, единственная остаётся как есть.
    """
    parts = [p.strip() for p in (survivor, absorbed) if p and p.strip()]
    if not parts:
        return None
    if len(parts) == 1:
        return parts[0]
    return "\n---\n".join(parts)
