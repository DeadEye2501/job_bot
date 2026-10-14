"""Набор сессии агента без браузера, водителя и человека."""

import dataclasses
from collections.abc import Awaitable, Callable
from datetime import date

from backend.agent.human_gate import HumanGate
from backend.agent.jobs import ApplyJob, FillJob, Source
from backend.agent.kit import AgentEnd, AgentKit, SessionPlan
from backend.domain.apply_order import Way
from backend.payloads import SeenResume
from tests.factories_aggregators import aggregator_row
from tests.fakes.browser import FakeBrowser

TODAY = date(2026, 10, 9)


class LimitHit(Exception):
    """Шаг сценария: водитель упёрся в лимит подписки."""


def tool(tools, name):
    """Инструмент по имени — так его видит агент."""
    return next(t for t in tools if t.__name__ == name)


def apply_job(vacancy_id: int, *, method="form", target="https://company.test/apply",
              aggregator_id=None, **overrides) -> ApplyJob:
    """Задание откликателя: по умолчанию форма работодателя, без агрегатора, всерьёз."""
    fields = dict(vacancy_id=vacancy_id, way=Way(method, target, aggregator_id), profile_id=1,
                  simulated=False, letter_writer="app")
    fields.update(overrides)
    return ApplyJob(**fields)


def fill_job(**overrides) -> FillJob:
    """Заполнение резюме на сайте строки агрегатора по умолчанию: новое резюме."""
    return FillJob(Source.of(aggregator_row(id=4)), **overrides)


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


def finish_step(result: str = "done", reason: str = ""):
    """Шаг сценария: сессия кончается этим итогом и больше ничего не делает."""
    async def step(tools):
        await tools["finish"](result=result, reason=reason)
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


def resumes_step(resumes: list[tuple[str, str]], can_add: bool = False):
    """Шаг сценария: агент перечисляет резюме сайта (название, ссылка) и кончает сессию."""
    async def step(tools):
        await tools["report_resumes"](resumes=[SeenResume(title, url) for title, url in resumes],
                                      can_add=can_add)
        await tools["finish"](result="done")
    return step


def silent_gate(limit_sec: float = 3600.0) -> HumanGate:
    """Пауза на человека, который не придёт: окну ничего не говорится."""
    return HumanGate(lambda kind, host, payload: None, lambda: None, limit_sec=limit_sec)


def answering_gate(answer: Callable[[dict], dict | None],
                   limit_sec: float = 3600.0) -> tuple[HumanGate, list]:
    """Человек у окна подтверждения: на каждый зов сразу отвечает тем, что `answer`
    вернул на его данные; `None` — не отвечает вовсе. Второе — данные всех зовов."""
    asked = []

    def needed(kind, host, payload):
        asked.append(payload)
        reply = answer(payload)
        if reply is not None:
            gate.resolve(reply)

    gate = HumanGate(needed, lambda: None, limit_sec=limit_sec)
    return gate, asked


def page_item(selector: str, value: str, *, label="Имя", kind="text", error="") -> dict:
    """Поле страницы с ответом — пункт, которым агент подтверждает страницу."""
    return {"label": label, "kind": kind, "value": value, "error": error, "selector": selector}


def layout_item(selector: str, value: str, reason: str = "") -> dict:
    """Пункт раскладки страницы; `reason` — обоснование запасного пути, пусто — узкое поле."""
    item = page_item(selector, value, label=selector)
    return {**item, "fallback_reason": reason} if reason else item


def edited(values: dict[str, str], by: str = "label"):
    """Ответ окна: пункты, чей `by` назван в `values`, правлены, прочие — как пришли."""

    def answer(payload):
        return {"items": [{**item, "value": values.get(item[by], item["value"])}
                          for item in payload["items"]]}

    return answer


def finished(payload) -> dict:
    """Ответ окна «Закончить»."""
    return {"drop": True}


async def under_confirmation(kit: AgentKit, answer, limit_sec: float = 3600.0) -> tuple[AgentKit, list]:
    """Набор в режиме «с подтверждением» с человеком у окна (`answering_gate`)."""
    await kit.pipeline.rs.set_app("auto_apply", "confirm")
    gate, asked = answering_gate(answer, limit_sec)
    return dataclasses.replace(kit, gate=gate), asked


def scripted_kit(pipeline, steps, *, human_limit: float = 3600.0) -> AgentKit:
    """Набор обхода: браузер-подделка, человек, который не придёт, водитель по сценарию."""
    return kit_for(pipeline, browser=FakeBrowser(), gate=silent_gate(human_limit),
                   run_session=scripted(steps))


def work_kit(bot) -> AgentKit:
    """Набор работы бота на браузере-подделке — подмена `bot/work._kit`."""
    return kit_for(bot.ingestion, browser=FakeBrowser(), gate=bot.human_gate)


def kit_for(pipeline, *, browser=None, gate=None, run_session=None) -> AgentKit:
    return AgentKit(pipeline=pipeline, browser=browser, gate=gate,
                    run_session=run_session, today=TODAY)
