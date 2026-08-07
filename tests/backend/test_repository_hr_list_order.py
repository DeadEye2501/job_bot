"""Следствия порядка в списке HR.

Список обслуживает два экрана, и порядок у них разный: в выборщике «связать с
HR» вперёд идут те, у кого вакансий больше, в контактах — те, с кем недавно
переписывались. Спор при равенстве решает имя.
"""

from backend.repository import list_hr_with_counts
from tests.dbio import put
from tests.factories import at, hr_row, message_row, vacancy_row


async def names(session, **kwargs) -> list[str]:
    """Имена HR в порядке выдачи."""
    return [row.hr.name for row in await list_hr_with_counts(session, **kwargs)]


async def test_the_picker_leads_with_the_most_prolific_hr(session, session_factory):
    """В выборщике вперёд идёт тот, у кого вакансий больше.

    Порядок вставки обратен ожидаемому нарочно: совпади они — и выдача без
    всякой сортировки прошла бы проверку.
    """
    none_at_all = hr_row(name="Виктор")
    few = hr_row(name="Анна")
    many = hr_row(name="Борис")
    await put(session_factory, none_at_all, few, many)
    await put(
        session_factory,
        vacancy_row(hr_id=many.id),
        vacancy_row(hr_id=many.id),
        vacancy_row(hr_id=few.id),
    )

    assert await names(session) == ["Борис", "Анна", "Виктор"]


async def test_an_equal_count_is_broken_by_name(session, session_factory):
    """При равном числе вакансий порядок решает имя.

    Имена выбраны так, чтобы алфавит спорил с порядком заведения: без
    разрешителя список вышел бы в порядке вставки.
    """
    await put(
        session_factory,
        hr_row(name="Яна"),
        hr_row(name="Анна"),
        hr_row(name="Борис"),
    )

    assert await names(session) == ["Анна", "Борис", "Яна"]


async def test_contacts_lead_with_the_latest_conversation(session, session_factory):
    """В контактах вперёд идёт тот, с кем переписывались позже.

    Число вакансий здесь спорит с давностью переписки: у самого свежего
    собеседника вакансий меньше всех, и совпадение с порядком выборщика этим
    исключено.
    """
    recent = hr_row(name="Анна")
    older = hr_row(name="Борис")
    await put(session_factory, recent, older)
    await put(
        session_factory,
        vacancy_row(hr_id=older.id),
        vacancy_row(hr_id=older.id),
        message_row(hr_id=recent.id, sent_at=at(50)),
        message_row(hr_id=older.id, sent_at=at(10)),
    )

    assert await names(session, sort_by="last_activity") == ["Анна", "Борис"]
    assert await names(session) == ["Борис", "Анна"]


async def test_an_hr_without_any_conversation_goes_last(session, session_factory):
    """В контактах те, с кем не переписывались, уходят в хвост."""
    talked = hr_row(name="Яна")
    silent = hr_row(name="Анна")
    await put(session_factory, talked, silent)
    await put(session_factory, message_row(hr_id=talked.id, sent_at=at(10)))

    assert await names(session, sort_by="last_activity") == ["Яна", "Анна"]


async def test_a_deleted_message_does_not_count_as_a_conversation(
    session, session_factory
):
    """Удалённое сообщение свежести переписке не добавляет."""
    only_deleted = hr_row(name="Анна")
    alive = hr_row(name="Яна")
    await put(session_factory, only_deleted, alive)
    await put(
        session_factory,
        message_row(hr_id=only_deleted.id, sent_at=at(50), is_deleted=True),
        message_row(hr_id=alive.id, sent_at=at(10)),
    )

    assert await names(session, sort_by="last_activity") == ["Яна", "Анна"]
