"""Названная сумма вакансии: по её вилке, анкете и кэшу курсов.

Отличие от `agent_profile`: тот собирает анкету и ставит строки зарплаты как
даны, а здесь сумму считают. Откликатель видит только её: увидев рядом
минимальную и желаемую, модель путала их и называла не ту.
"""

from sqlalchemy.ext.asyncio import AsyncSession

from backend.domain.named_salary import Offer, Pay, judge_salary, money_text, salary_ask_of
from backend.models import Vacancy
from backend.repository.currency_rates import load_rates
from backend.repository.profile import get_profile


async def pay_for_vacancy(session: AsyncSession, vacancy_id: int) -> Pay | None:
    """Что назвать работодателю этой вакансии; пусто — нечего или вакансии нет."""
    vacancy = await session.get(Vacancy, vacancy_id)
    if vacancy is None:
        return None
    ask = salary_ask_of(await get_profile(session))
    offer = Offer(vacancy.salary_min, vacancy.salary_max, vacancy.salary_currency, vacancy.salary_period)
    return judge_salary(offer, ask, await load_rates(session)).pay


async def vacancy_salary_lines(session: AsyncSession, vacancy_id: int) -> list[str]:
    """Строка названной суммы — для откликателя и писем к этой вакансии."""
    pay = await pay_for_vacancy(session, vacancy_id)
    named = "не указана" if pay is None else money_text(pay.amount, pay.currency, pay.period)
    return [f"Зарплата для этой вакансии: {named}"]
