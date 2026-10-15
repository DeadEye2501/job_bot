"""Инструменты заполнения резюме: раскладка страницы и остановки — за нехваткой
данных и за отказом сайта завести ещё одно резюме.

Как `tools_letter` у отклика: агент предлагает, код решает, что примет, — здесь
пункты раскладки, вписать можно только принятое (`tools_browser._strict`).
Раскладка же — единственная дверь ввода, и потому именно она решает, то ли
резюме открыто.
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
_OFF_TARGET_EDIT = "это страница другого резюме — открой редактор резюме из задания"
_OFF_TARGET_NEW = "это страница другого резюме — открой создание нового резюме"


# Пункт подтверждения, а не свой вид: строгий ввод читает одну форму у
# подтверждённого человеком и у принятого раскладкой.
class LayoutItem(ConfirmItem, total=False):
    """Пункт раскладки страницы. `fallback_reason` — у данных, положенных в общее
    поле: почему узкие поля страницы им не подходят."""

    fallback_reason: str


def fill_tools(kit: AgentKit, job: FillJob) -> list[Callable]:
    """Инструменты заполнения, привязанные к своему сайту."""

    async def submit_layout(items: list[LayoutItem]) -> str:
        """Раскладка страницы целиком: каждый пункт — поле страницы и всё его значение из анкеты, одно поле — один пункт. label — подпись поля; kind — text, choice (список, переключатель) или check; value — значение, у галочки true или false; error — пусто; selector — тот, которым будешь вписывать. У данных, положенных в общее текстовое поле, fallback_reason — почему узкие поля страницы им не подходят. Вписать можно только принятое."""
        page = await kit.browser.page()
        url = page.url
        if job.off_target(url):
            logger.warning("заполнение резюме на %s: раскладка на странице другого резюме отбита — %s",
                           job.source.host, url)
            return _OFF_TARGET_EDIT if job.editor_url else _OFF_TARGET_NEW
        inventory = await page_inventory(page)
        job.general |= {(url, item["selector"]) for item in items if item.get("fallback_reason")}
        refused = _unfit(job, url, items)
        fallbacks = [item for item in items if (url, item["selector"]) in job.general
                     and item["selector"] not in refused and not _known(job, url, item)]
        refused |= await _reviewed(job, url, fallbacks, lambda pending: review_fallbacks(
            kit.pipeline.lm_client, kit.pipeline.lm_chat_model, inventory, pending))
        for item in items:
            if item["selector"] not in refused:
                job.accepted[(url, item["selector"])] = item
        job.skipped[url] = _skipped(job, url, inventory)
        return _answer(len(items) - len(refused), refused)

    async def report_required_missing(labels: list[str]) -> str:
        """Обязательные поля страницы, которые нечем заполнить по анкете: заполнение останавливается."""
        return _stopped(job, Finished("required_missing", ", ".join(labels)),
                        "не хватает данных для обязательных полей")

    async def report_no_new_resume(reason: str) -> str:
        """Сайт не даёт завести ещё одно резюме; reason — почему, словами. Создание останавливается."""
        return _stopped(job, Finished("no_new_resume", reason), "сайт не даёт завести ещё одно резюме")

    if job.editor_url:
        return [submit_layout, report_required_missing]
    return [submit_layout, report_required_missing, report_no_new_resume]


def _stopped(job: FillJob, outcome: Finished, why: str) -> str:
    """Остановить заполнение итогом с причиной: запись в журнал и ответ агенту."""
    job.outcome = outcome
    logger.warning("заполнение резюме на %s: %s — %s", job.source.host, why, outcome.reason)
    return f"Заполнение остановлено: {why}. Заверши работу."


def _known(job: FillJob, url: str, item: dict) -> bool:
    """Пункт уже принят с тем же значением: новые поля на странице дают новую
    раскладку, и принятое в ней проверок не тратит."""
    return job.accepted.get((url, item["selector"]), {}).get("value") == item["value"]


def _skipped(job: FillJob, url: str, inventory: list) -> list[str]:
    """Необязательные поля страницы, которым за всю работу на ней не нашлось
    пункта. Поле узнаётся по селектору или подписи: селектор описи и селектор
    агента бывают разной записи одного поля."""
    taken = [item for (where, _), item in job.accepted.items() if where == url]
    selectors = {item["selector"] for item in taken}
    labels = {item["label"] for item in taken if item["label"]}
    return [entry.label for entry in inventory if not entry.required
            and entry.selector not in selectors and entry.label not in labels]


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

    Проверок на поле столько же, сколько у писем (`CHECKS_ALLOWED`): поле, чьи
    проверки кончились, не проверяется и не принимается. Счёт по полю, а не по
    странице: в одностраничном редакторе каждое место работы — своё поле, и
    общий счёт молча оставил бы третье без проверки и без записи.
    """
    spent = [item for item in fallbacks if job.page_checks.get((url, item["selector"]), 0) >= CHECKS_ALLOWED]
    asked = [item for item in fallbacks if item not in spent]
    refused = {item["selector"]: _ENOUGH for item in spent}
    if asked:
        for item in asked:
            key = (url, item["selector"])
            job.page_checks[key] = job.page_checks.get(key, 0) + 1
        verdicts = await review(asked)
        refused |= {selector: _why(verdict.reason, verdict.field)
                    for selector, verdict in verdicts.items() if not verdict.ok}
    exhausted = [selector for selector in refused if job.page_checks.get((url, selector), 0) >= CHECKS_ALLOWED]
    if exhausted:
        logger.warning("заполнение резюме: проверяющий не пропустил %s на %s", ", ".join(exhausted), url)
    return refused


def _why(reason: str, field: str | None) -> str:
    return f"{reason}; поле: {field}" if field else reason


def _answer(accepted: int, refused: dict[str, str]) -> str:
    lines = [f"Принято пунктов: {accepted}."]
    lines += [f"Отбит {selector}: {reason}" for selector, reason in refused.items()]
    return "\n".join(lines)
