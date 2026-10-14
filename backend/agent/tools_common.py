"""Общие инструменты агента: анкета, итог сессии, зов человека, отметка входа, неудача способа."""

import json
from collections.abc import Callable

from backend.agent.confirm import ConfirmItem, ask_person
from backend.agent.jobs import (
    FINAL,
    FINAL_ANSWER,
    HUMAN_KINDS,
    RESULTS,
    ApplyJob,
    Dropped,
    Failed,
    FillJob,
    Finished,
    LoginJob,
    ScanJob,
    SeekJob,
)
from backend.agent.kit import AgentKit
from backend.agent.page_fields import field_or_none
from backend.domain.apply_order import VIA_AGGREGATOR
from backend.domain.hosts import normalize_host
from backend.repository.aggregators import set_logged_in


def common_tools(kit: AgentKit, job) -> list[Callable]:
    """Инструменты, привязанные к задаче сессии: за её пределы они не выходят.

    Подписи — с аннотациями всегда: по ним MCP строит схему инструмента для агента.
    """

    async def profile() -> str:
        """Анкета человека целиком, со стажем общим и по навыкам."""
        async with kit.pipeline.session_factory() as session:
            return await kit.profile_text(session) or "Анкета не заполнена."

    async def finish(result: str, reason: str = "") -> str:
        """Итог сессии. Искатель: done или failed. Откликатель: vacancy_closed, platform_closed, not_fit, а при резюме, названном в задании, ещё resume_missing. Проверка входа и перечень резюме: done. Заполнение резюме: done."""
        results = _results(job)
        if result not in results:
            return f"Итога «{result}» у этой задачи не бывает: {', '.join(sorted(results))}."
        if isinstance(job.outcome, FINAL):
            return FINAL_ANSWER
        # Итог записывается один раз: нехватку данных у заполнения ставит свой
        # инструмент, и «done» следом превратил бы остановку в успех.
        if isinstance(job.outcome, Finished):
            return "Итог уже записан, работа окончена."
        job.outcome = Finished(result, reason)
        return "Итог записан, работа окончена."

    tools = [profile, finish, *_human_call(kit, job)]
    aggregator_id = _login_target(job)
    if aggregator_id is not None:
        tools.append(_report_login(kit, aggregator_id))
    if isinstance(job, ApplyJob):
        tools.append(_report_failure(job))
    return tools


def _results(job) -> frozenset[str]:
    """Итоги, которыми эта сессия может кончиться. «Названного резюме нет на
    сайте» — только у отклика, где резюме названо: остановка всего прогона и
    удаление резюме иначе случились бы по слову о резюме, которого не было."""
    if isinstance(job, ApplyJob) and job.resume is None:
        return RESULTS[ApplyJob] - {"resume_missing"}
    return RESULTS[type(job)]


def _login_target(job) -> int | None:
    if isinstance(job, (LoginJob, ScanJob, SeekJob, FillJob)):
        return job.source.id if job.source.host is not None else None
    return job.way.aggregator_id if job.way.method == VIA_AGGREGATOR else None


def _human_call(kit: AgentKit, job) -> list[Callable]:
    """Зов человека, какой задаче положен.

    Проверка входа идёт, когда человек уже закрыл окно: позови она его снова,
    окно открывалось бы по кругу, пока он не войдёт. Её дело — «не вошёл».
    Отклик под подтверждением зовёт человека ещё и с пунктами страницы: решено
    при постановке задачи, и прочим задачам этот зов не выдаётся вовсе.
    """
    if isinstance(job, LoginJob):
        return []
    if isinstance(job, ApplyJob) and job.confirming:
        return [_need_human_confirming(kit, job)]
    return [_need_human(kit, job)]


def _need_human(kit: AgentKit, job) -> Callable:
    async def need_human(kind: str) -> str:
        """Нужен человек: kind — captcha или login. Вызов держится, пока человек не нажмёт «Готово». Ответ «срок вышел» — заверши работу."""
        return await _wait_in_browser(kit, job, kind)

    return need_human


def _need_human_confirming(kit: AgentKit, job: ApplyJob) -> Callable:
    async def need_human(kind: str, items: list[ConfirmItem] | None = None) -> str:
        """Нужен человек: kind — captcha, login или confirm. Вызов держится, пока человек не ответит. Ответ «срок вышел» — заверши работу. confirm — подтвердить поля страницы перед вводом: items — все поля с ответами."""
        if kind == "confirm":
            return await _confirm_page(kit, job, items) if items else "items — все поля страницы с ответами."
        return await _wait_in_browser(kit, job, kind)

    return need_human


async def _wait_in_browser(kit: AgentKit, job, kind: str) -> str:
    """Капча или вход: человек работает в браузере агента."""
    if kind not in HUMAN_KINDS:
        return "kind — captcha или login."
    return await kit.gate.wait(kind, _host_of(job) or "сайт", kit.browser)


async def _confirm_page(kit: AgentKit, job: ApplyJob, items: list[ConfirmItem]) -> str:
    """Подтвердить поля страницы у человека и запомнить подтверждённое за этой страницей.

    После записанного отклика страница тоже подтверждается — вопросы после
    отправки уходят работодателю, — но «Закончить» на ней отклик не отменяет:
    он уже у работодателя.
    """
    if isinstance(job.outcome, Dropped):
        return FINAL_ANSWER
    page = await kit.browser.page()
    url = page.url
    shown = [{**_last_known(job.confirmed.get((url, item["selector"])), item),
              "required": await _required(page, item["selector"])} for item in items]
    kept = await ask_person(kit, job.vacancy_id, shown)
    if isinstance(kept, Dropped):
        if not isinstance(job.outcome, FINAL):
            job.outcome = kept
        return "Человек закончил работу по этой вакансии. Больше ничего не вводи и не отправляй, заверши работу."
    for item in kept:
        job.confirmed[(url, item["selector"])] = item
        job.unscreened[(url, item["selector"], item["label"])] = item
    return "Подтверждено. Впиши ровно это:\n" + json.dumps(kept, ensure_ascii=False)


async def _required(page, selector: str) -> bool:
    """Обязательно ли поле — по разметке самой страницы, а не со слов агента.

    Поле, которого на странице не нашлось, обязательным не считается: окно
    заперло бы подтверждение на пункте, которого человек не может заполнить.
    """
    field = await field_or_none(page, selector)
    return field is not None and field.required


def _last_known(before: dict | None, item: ConfirmItem) -> ConfirmItem:
    """Значение пункта — последнее известное для поля: подтверждённое человеком
    важнее ответа модели, и сайт, отвергший отправленное, показывает человеку его
    же правку рядом с ошибкой. Поле считается тем же по подписи: у шагов формы
    бывает один адрес, и селектор следующего шага совпадает с прежним."""
    if before is not None and before["label"] == item["label"]:
        return {**item, "value": before["value"]}
    return item


def _host_of(job) -> str | None:
    """Сайт, на котором нужен человек: источник поиска или адрес способа отклика."""
    if isinstance(job, ApplyJob):
        return normalize_host(job.way.target) or None
    return job.source.host


def _report_login(kit: AgentKit, aggregator_id: int) -> Callable:
    async def report_login(logged_in: bool) -> str:
        """Вошёл ли человек на сайт: true — вошёл, false — нет."""
        await kit.written(lambda session: set_logged_in(session, aggregator_id, logged_in))
        return "Отметка входа записана."

    return report_login


def _report_failure(job: ApplyJob) -> Callable:
    async def report_failure(reason: str) -> str:
        """Отклик этим способом не удался; причина — коротко, по-русски."""
        if isinstance(job.outcome, FINAL):
            return FINAL_ANSWER
        job.outcome = Failed(reason)
        return "Неудача записана. Приложение попробует другой способ."

    return report_failure
