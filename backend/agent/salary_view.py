"""Какую зарплату видит агент в анкете — по своей задаче.

Откликатель — только названную сумму этой вакансии (её ставит
`AgentKit.vacancy_profile_text`); заполнитель резюме — минимальную и желаемую;
прочим зарплата не нужна. Порознь потому, что модель, видя все суммы разом,
называла не ту.
"""

from sqlalchemy.ext.asyncio import AsyncSession

from backend.agent.jobs import FillJob
from backend.domain.named_salary import SalaryAsk, money_text, salary_ask_of
from backend.repository.profile import get_profile


async def salary_lines(session: AsyncSession, job) -> list[str]:
    """Строки зарплаты агента, кроме откликателя: его анкету собирает
    `AgentKit.vacancy_profile_text`."""
    if isinstance(job, FillJob):
        return _ask_lines(salary_ask_of(await get_profile(session)))
    return []


def _ask_lines(ask: SalaryAsk) -> list[str]:
    """Минимальная и желаемая — для заполнения резюме на сайте."""
    return [
        f"Минимальная зарплата: {_sum(ask.minimum, ask)}",
        f"Желаемая зарплата: {_sum(ask.desired, ask)}",
    ]


def _sum(amount: int | None, ask: SalaryAsk) -> str:
    return "не указана" if amount is None else money_text(amount, ask.currency, ask.period)
