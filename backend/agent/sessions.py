"""Сессия агента под надзором: сервер, водитель, срок человека и общий срок."""

import asyncio
from dataclasses import replace

import anyio

from adapters.agent_mcp import serve_tools
from adapters.claude_code_agent import AgentEnd, AgentRun, run_agent
from backend.agent.jobs import Finished, SeekJob
from backend.agent.kit import AgentKit, RunSession, SessionPlan
from backend.agent.prompts.frame import system_prompt
from backend.agent.stops import HumanTimeout, LimitExhausted
from backend.agent.tools_common import common_tools
from backend.llm.rules import in_user_language
from backend.repository.profile_languages import read_user_language
from backend.task_stop import put_out

# Зависший процесс Claude Code иначе держал бы место прогона, а с ним и обход
# каналов, бессрочно. Час из срока может уйти на ожидание человека.
SESSION_LIMIT_SEC = 3 * 3600

# Шаг, которым отсчитывается срок: стоящая сессия (`SessionPlan.paused`) за
# шаг не тратит ничего, и мельче он нужен только тестам.
_TICK_SEC = 1.0

# Срок вызова инструмента у искателя — снят: внутри вызова идёт весь цикл
# находки до отклика и ожидания человека, у каждого способа отклика свой срок,
# и верхней границы у их суммы нет. Выход из зависшего — «Стоп».
SEEKER_TOOL_TIMEOUT_MS = 2**31 - 1


async def run_guarded(kit: AgentKit, plan: SessionPlan) -> AgentEnd:
    """Сессия наперегонки со сроками. Отмена снаружи гасит сессию и ждёт её конца:
    агент не успеет записать отклик после остановки.

    Ждётся конец под щитом: вложенную сессию — отклик посреди вызова инструмента
    искателя — гасит закрытие его сервера, а отмена оттуда повторяется на каждом
    ожидании, и без щита сессию отклика никто бы не дождался — она дорабатывала
    бы в том же браузере, что и следующий поиск.

    Язык человека вписывается в рамку здесь: сюда приходит каждая сессия, а
    собирают рамку синхронно, без базы."""
    language = await kit.read(read_user_language)
    plan = replace(plan, system_prompt=in_user_language(plan.system_prompt, language))
    session = asyncio.create_task(kit.run_session(plan))
    expiry = asyncio.create_task(kit.gate.expired.wait())
    try:
        done = await _raced(session, expiry, plan.paused)
    except asyncio.CancelledError:
        await _shielded_put_out(session)
        raise
    finally:
        expiry.cancel()
    if session not in done:
        # Под щитом и здесь: истёкший срок человека гасит и сессию искателя, и
        # вложенную в его вызов — гашение сверху застало бы нас посреди этого.
        await _shielded_put_out(session)
    # Флаг, а не победитель гонки: получив «срок вышел», агент сам кончает
    # сессию, и она бывает готова раньше, чем ожидание срока проснётся.
    if kit.gate.expired.is_set():
        raise HumanTimeout
    if session in done:
        return session.result()
    return AgentEnd(False, "сессия агента превысила срок", False)


async def _shielded_put_out(session: asyncio.Task) -> None:
    with anyio.CancelScope(shield=True):
        await put_out(session)


async def _raced(session: asyncio.Task, expiry: asyncio.Task, paused) -> set:
    """Дождаться сессии или истёкшего ожидания человека; пусто — срок вышел.

    Срок отсчитывается шагами и тратится только на шаги, когда сессия не
    стоит: стоящую ждут, сколько бы она ни стояла.
    """
    loop = asyncio.get_running_loop()
    left = SESSION_LIMIT_SEC
    while left > 0:
        began = loop.time()
        done, _ = await asyncio.wait(
            {session, expiry}, timeout=min(_TICK_SEC, left), return_when=asyncio.FIRST_COMPLETED
        )
        if done:
            return done
        if not paused():
            left -= loop.time() - began
    return set()


async def run_to_limit(kit: AgentKit, plan: SessionPlan) -> AgentEnd:
    """Сессия, после которой исчерпанный лимит модели обрывает всю работу."""
    end = await run_guarded(kit, plan)
    if end.limit_exhausted:
        raise LimitExhausted
    return end


async def run_seeker(kit: AgentKit, job: SeekJob, plan: SessionPlan) -> AgentEnd:
    """Сессия искателя; беда, снявшая работу посреди цикла находки, поднимается
    после её конца — агент к тому времени закончил сессию сам.

    Срок искателя не течёт, пока идёт цикл находки или ждут человека, и вызов
    инструмента сроком не ограничен. Ожидание человека — общее у искателя и
    вложенного в его вызов откликателя: набор у них один (`bot.kit`), и капча,
    вход и подтверждение равно не работа искателя.
    """
    plan = replace(plan, paused=lambda: job.nested or kit.gate.waiting,
                   tool_timeout_ms=SEEKER_TOOL_TIMEOUT_MS)
    try:
        end = await run_to_limit(kit, plan)
    except Exception as trouble:
        # Сессия упала уже после беды: та важнее — без неё обход счёл бы
        # снятую работу сбоем одного источника и пошёл к следующему.
        raise job.stopper or trouble
    if job.stopper is not None:
        raise job.stopper
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
                                            model, plan.web_search, plan.tool_timeout_ms))
        finally:
            await server.close()

    return run
