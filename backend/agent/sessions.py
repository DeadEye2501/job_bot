"""Сессия агента под надзором: сервер, водитель, срок человека и общий срок."""

import asyncio

from adapters.agent_mcp import serve_tools
from adapters.claude_code_agent import AgentEnd, AgentRun, run_agent
from backend.agent.kit import AgentKit, RunSession, SessionPlan
from backend.task_stop import put_out

# Зависший процесс Claude Code иначе держал бы место прогона, а с ним и обход
# каналов, бессрочно. Час из срока может уйти на ожидание человека.
SESSION_LIMIT_SEC = 3 * 3600


class HumanTimeout(Exception):
    """Человек не справился с капчей или входом за час — обход снимается."""


class LimitExhausted(Exception):
    """Исчерпан лимит подписки водителя — следующий источник упёрся бы в то же."""


async def run_guarded(kit: AgentKit, plan: SessionPlan) -> AgentEnd:
    """Сессия наперегонки со сроками. Отмена снаружи гасит сессию и ждёт её конца:
    агент не успеет записать отклик после остановки. Исключение — письмо,
    которое сервер почты уже принимает: оно дойдёт и запишется (`ApplyJob.delivery`)."""
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
