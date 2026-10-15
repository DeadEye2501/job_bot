"""Сессия агента под надзором: сервер, водитель, срок человека и общий срок."""

import asyncio
from dataclasses import replace

from adapters.agent_mcp import serve_tools
from adapters.claude_code_agent import AgentEnd, AgentRun, run_agent
from backend.agent.jobs import Finished
from backend.agent.kit import AgentKit, RunSession, SessionPlan
from backend.agent.prompts.frame import system_prompt
from backend.agent.stops import HumanTimeout, LimitExhausted
from backend.agent.tools_common import common_tools
from backend.llm.candidate import in_user_language
from backend.repository.profile_languages import read_user_language
from backend.task_stop import put_out

# Зависший процесс Claude Code иначе держал бы место прогона, а с ним и обход
# каналов, бессрочно. Час из срока может уйти на ожидание человека.
SESSION_LIMIT_SEC = 3 * 3600




async def run_guarded(kit: AgentKit, plan: SessionPlan) -> AgentEnd:
    """Сессия наперегонки со сроками. Отмена снаружи гасит сессию и ждёт её конца:
    агент не успеет записать отклик после остановки.

    Язык человека вписывается в рамку здесь: сюда приходит каждая сессия, а
    собирают рамку синхронно, без базы."""
    language = await kit.read(read_user_language)
    plan = replace(plan, system_prompt=in_user_language(plan.system_prompt, language))
    session = asyncio.create_task(kit.run_session(plan))
    expiry = asyncio.create_task(kit.gate.expired.wait())
    try:
        done, _ = await asyncio.wait(
            {session, expiry}, timeout=SESSION_LIMIT_SEC, return_when=asyncio.FIRST_COMPLETED
        )
    except asyncio.CancelledError:
        await put_out(session)
        raise
    finally:
        expiry.cancel()
    if session not in done:
        await put_out(session)
    # Флаг, а не победитель гонки: получив «срок вышел», агент сам кончает
    # сессию, и она бывает готова раньше, чем ожидание срока проснётся.
    if kit.gate.expired.is_set():
        raise HumanTimeout
    if session in done:
        return session.result()
    return AgentEnd(False, "сессия агента превысила срок", False)


async def run_to_limit(kit: AgentKit, plan: SessionPlan) -> AgentEnd:
    """Сессия, после которой исчерпанный лимит модели обрывает всю работу.

    Обход источника проверяет лимит позже, после разбора найденного, и зовёт
    `run_guarded` сам."""
    end = await run_guarded(kit, plan)
    if end.limit_exhausted:
        raise LimitExhausted
    return end


async def run_on_site(kit: AgentKit, job, prompt: str, task: str, *own_tools) -> AgentEnd:
    """Сессия агента на сайте источника — у входа, перечня и заполнения резюме:
    общие инструменты задачи и её собственные, браузер среди них; веб-поиск
    сайту не нужен. Браузер задача приносит сама: заполнению он нужен со
    строгим вводом и файлами, прочим — простой."""
    tools = [*common_tools(kit, job), *own_tools]
    plan = SessionPlan(system_prompt(prompt, tools), task, tools, web_search=False)
    return await run_to_limit(kit, plan)


def end_reason(job, end: AgentEnd) -> str:
    """Почему сессия кончилась не тем, чего ждали, — для журнала: причина итога
    агента, иначе слово конца сессии, иначе «без итога»."""
    reason = job.outcome.reason if isinstance(job.outcome, Finished) else end.detail
    return reason or "без итога"


def live_session(model: str) -> RunSession:
    """Боевая сессия: свой MCP-сервер с инструментами плана и свой процесс Claude Code."""

    async def run(plan: SessionPlan) -> AgentEnd:
        server = await serve_tools(plan.tools)
        try:
            return await run_agent(AgentRun(plan.system_prompt, plan.task, server.url,
                                            model, plan.web_search))
        finally:
            await server.close()

    return run
