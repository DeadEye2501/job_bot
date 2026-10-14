"""Инструменты заполнения резюме: раскладка страницы и остановка за нехваткой данных.

Как `tools_letter` у отклика: агент предлагает, код решает, что примет, — здесь
пункты раскладки, вписать можно только принятое (`tools_browser._strict`).
"""

import logging
from collections.abc import Callable

from backend.agent.confirm import ConfirmItem
from backend.agent.jobs import FillJob, Finished
from backend.agent.kit import AgentKit
from backend.agent.page_fields import page_inventory
from backend.agent.tools_letter import CHECKS_ALLOWED
from backend.llm.fill_review import review_fallbacks

logger = logging.getLogger(__name__)

_ENOUGH = "проверок больше нет на этой странице: впиши эти данные в узкое поле или пропусти"
_ONE_FIELD = "одно поле — один пункт: собери всё, что идёт в это поле, в одно значение"
_NO_REASON = "поле общее: нужно обоснование, почему узкие поля страницы не подходят"


# Пункт подтверждения, а не свой вид: строгий ввод читает одну форму у
# подтверждённого человеком и у принятого раскладкой.
class LayoutItem(ConfirmItem, total=False):
    """Пункт раскладки страницы. `fallback_reason` — у данных, положенных в общее
    поле: почему узкие поля страницы им не подходят."""

    fallback_reason: str


def fill_tools(kit: AgentKit, job: FillJob) -> list[Callable]:
    """Инструменты заполнения, привязанные к своему сайту."""

    async def submit_layout(items: list[LayoutItem]) -> str:
        """Раскладка страницы целиком: каждый пункт — поле страницы и всё его значение из анкеты, одно поле — один пункт. У данных, положенных в общее текстовое поле, fallback_reason — почему узкие поля страницы им не подходят. Вписать можно только принятое."""
        page = await kit.browser.page()
        url = page.url
        inventory = await page_inventory(page)
        named = {item["selector"] for item in items}
        job.skipped[url] = [entry.label for entry in inventory
                            if not entry.required and entry.selector not in named]
        job.general |= {(url, item["selector"]) for item in items if item.get("fallback_reason")}
        refused = _unfit(job, url, items)
        fallbacks = [item for item in items
                     if (url, item["selector"]) in job.general and item["selector"] not in refused]
        refused |= await _reviewed(job, url, fallbacks, lambda pending: review_fallbacks(
            kit.pipeline.lm_client, kit.pipeline.lm_chat_model, inventory, pending))
        for item in items:
            if item["selector"] not in refused:
                job.accepted[(url, item["selector"])] = item
        return _answer(len(items) - len(refused), refused)

    async def report_required_missing(labels: list[str]) -> str:
        """Обязательные поля страницы, которые нечем заполнить по анкете: заполнение останавливается."""
        job.outcome = Finished("required_missing", ", ".join(labels))
        logger.warning("заполнение резюме на %s: не хватает данных для обязательных полей — %s",
                       job.source.host, ", ".join(labels))
        return "Заполнение остановлено: не хватает данных для обязательных полей. Заверши работу."

    return [submit_layout, report_required_missing]


def _unfit(job: FillJob, url: str, items: list[dict]) -> dict[str, str]:
    """Пункты, отбитые до проверяющего: два пункта в одно поле — поле вписывается
    целиком, и один из них потерялся бы; пункт в общее поле без обоснования."""
    selectors = [item["selector"] for item in items]
    refused = {selector: _ONE_FIELD for selector in selectors if selectors.count(selector) > 1}
    for item in items:
        if (url, item["selector"]) in job.general and not item.get("fallback_reason"):
            refused.setdefault(item["selector"], _NO_REASON)
    return refused


async def _reviewed(job: FillJob, url: str, fallbacks: list[dict], review: Callable) -> dict[str, str]:
    """Отбитые пункты запасного пути по селектору — с причиной для агента;
    `review` — вызов проверяющего над пунктами этой страницы.

    Проверок на адрес столько же, сколько у писем (`CHECKS_ALLOWED`): следующая
    раскладка с запасным путём на той же странице не проверяется и не принимается.
    """
    if not fallbacks:
        return {}
    checks = job.page_checks.get(url, 0)
    if checks >= CHECKS_ALLOWED:
        refused = {item["selector"]: _ENOUGH for item in fallbacks}
    else:
        job.page_checks[url] = checks + 1
        verdicts = await review(fallbacks)
        refused = {selector: _why(verdict.reason, verdict.field)
                   for selector, verdict in verdicts.items() if not verdict.ok}
    if refused and checks + 1 >= CHECKS_ALLOWED:
        logger.warning("заполнение резюме: проверяющий не пропустил %s на %s", ", ".join(refused), url)
    return refused


def _why(reason: str, field: str | None) -> str:
    return f"{reason}; поле: {field}" if field else reason


def _answer(accepted: int, refused: dict[str, str]) -> str:
    lines = [f"Принято пунктов: {accepted}."]
    lines += [f"Отбит {selector}: {reason}" for selector, reason in refused.items()]
    return "\n".join(lines)
