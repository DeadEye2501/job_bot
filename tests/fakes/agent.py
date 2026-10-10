"""Набор сессии агента без браузера, водителя и человека."""

from collections.abc import Awaitable, Callable
from datetime import date

from backend.agent.human_gate import HumanGate
from backend.agent.jobs import ApplyJob
from backend.agent.kit import AgentEnd, AgentKit, SessionPlan
from tests.fakes.browser import FakeBrowser

TODAY = date(2026, 10, 9)


class LimitHit(Exception):
    """Шаг сценария: водитель упёрся в лимит подписки."""


def tool(tools, name):
    """Инструмент по имени — так его видит агент."""
    return next(t for t in tools if t.__name__ == name)


def apply_job(vacancy_id: int, **overrides) -> ApplyJob:
    """Задание откликателя: по умолчанию форма работодателя, без агрегатора, всерьёз."""
    fields = dict(vacancy_id=vacancy_id, method="form", target="https://company.test/apply",
                  aggregator_id=None, profile_id=1, simulated=False,
                  letter_writer="app")
    fields.update(overrides)
    return ApplyJob(**fields)


def scripted(steps: list[Callable[[dict[str, Callable]], Awaitable]]):
    """Водитель по сценарию: на каждую сессию — следующий шаг с инструментами плана по имени.

    Планы сессий копятся в `run.plans`: по ним видно, с каким наставлением,
    заданием и поиском в сети сессия была поднята.
    """
    queue = list(steps)

    async def run(plan: SessionPlan) -> AgentEnd:
        run.plans.append(plan)
        step = queue.pop(0)
        try:
            await step({t.__name__: t for t in plan.tools})
        except LimitHit:
            return AgentEnd(False, "лимит", True)
        return AgentEnd(True, "", False)

    run.plans = []
    return run


def finish_step(result: str = "done"):
    """Шаг сценария: сессия кончается этим итогом и больше ничего не делает."""
    async def step(tools):
        await tools["finish"](result=result)
    return step


def fail_step(reason: str):
    """Шаг сценария: способ отклика не сработал по этой причине."""
    async def step(tools):
        await tools["report_failure"](reason=reason)
    return step


def record_step(target: str, via: str = "form"):
    """Шаг сценария: отклик записан этим способом на этот адрес."""
    async def step(tools):
        await tools["record_application"](via=via, target=target)
    return step


def captcha_step():
    """Шаг сценария: агент упёрся в капчу и зовёт человека."""
    async def step(tools):
        await tools["need_human"](kind="captcha")
    return step


def login_step(logged_in: bool):
    """Шаг сценария: агент говорит, вошёл ли человек, и кончает сессию."""
    async def step(tools):
        await tools["report_login"](logged_in=logged_in)
        await tools["finish"](result="done")
    return step


def silent_gate(limit_sec: float = 3600.0) -> HumanGate:
    """Пауза на человека, который не придёт: окну ничего не говорится."""
    return HumanGate(lambda kind, host: None, lambda: None, limit_sec=limit_sec)


def scripted_kit(pipeline, steps, *, human_limit: float = 3600.0) -> AgentKit:
    """Набор обхода: браузер-подделка, человек, который не придёт, водитель по сценарию."""
    return kit_for(pipeline, browser=FakeBrowser(), gate=silent_gate(human_limit),
                   run_session=scripted(steps))


def kit_for(pipeline, *, browser=None, gate=None, run_session=None) -> AgentKit:
    return AgentKit(pipeline=pipeline, browser=browser, gate=gate,
                    run_session=run_session, today=TODAY)
