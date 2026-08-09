"""Следствия отбора значений, по которым отсеивают вакансии.

Отбор не различает рода: одно и то же слово из имени компании и из текста
вакансии отсеивает одинаково. Погашенные строки в отбор не идут.
"""

from backend.repository.blacklist import load_active_blacklist_patterns
from tests.dbio import put
from tests.factories import blacklist_row


async def test_only_active_values_reach_the_matcher(session, session_factory):
    """В отбор попадают значения только включённых строк, всех родов подряд.

    Отбор ключевых слов не различает рода: одно и то же слово из имени
    компании и из текста вакансии отсеивает одинаково.
    """
    await put(
        session_factory,
        blacklist_row("keyword", "казино", active=True),
        blacklist_row("hr", "@maria", active=True),
        blacklist_row("keyword", "передумал", active=False),
    )

    assert sorted(await load_active_blacklist_patterns(session)) == sorted(
        ["казино", "@maria"]
    )
