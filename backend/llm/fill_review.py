"""Проверка запасного пути при заполнении резюме: убедительно ли обоснование.

Отличие от сверки письма (`factcheck`): вердикт там один на всё письмо, здесь —
по каждому пункту раскладки, поэтому и разбор ответа свой. Приём общий:
модель чата, ответ JSON и «сбой пропускает» — заполнение из-за сбоя проверки
не стоит, как и отправка письма.
"""

import logging
from typing import NamedTuple

import httpx

from adapters.lm_chat import CUT_BY_LIMIT, ChatRequest, chat
from backend.llm.answers import ONLY_JSON, json_object, log_unparseable, str_or_none
from backend.llm.external import external_block
from backend.payloads import FieldEntry

logger = logging.getLogger(__name__)

_PURPOSE = "fill_review"
MAX_FILL_REVIEW_TOKENS = 1500

FILL_REVIEW_PROMPT = """Ты проверяешь, как помощник раскладывает данные анкеты по полям формы резюме на сайте. Правило раскладки: каждая часть анкеты идёт в самое узкое подходящее поле формы; в общее текстовое поле («О себе», описание) она спускается, только если узкого подходящего поля на странице нет.

Тебе дают опись полей страницы (селектор, подпись, вид, варианты) и пункты, которые помощник кладёт в общее поле, — с его обоснованием, почему узкие поля не подходят.

По каждому пункту реши:
- ok=true — узкого поля для этих данных в описи нет, или такие поля не подходят по смыслу и вариантам;
- ok=false — в описи есть узкое поле, куда эти данные ложатся; reason — коротко, какое поле и почему; field — селектор этого поля из описи.

Пример для калибровки: в описи есть поле «Город» со списком, где есть «Тверь»; пункт кладёт «Город: Тверь» в «О себе» с обоснованием «поля города нет» — ok=false, field — селектор поля «Город».

Ответ — объект JSON: {"verdicts": [{"selector": "...", "ok": true, "reason": "...", "field": null}]}, по одному вердикту на каждый пункт.
""" + ONLY_JSON


class Verdict(NamedTuple):
    """Вердикт пункту запасного пути: пропустить ли, почему нет и куда лучше."""

    ok: bool
    reason: str
    field: str | None


async def review_fallbacks(
    lm: httpx.AsyncClient, model: str, inventory: list[FieldEntry], items: list[dict]
) -> dict[str, Verdict]:
    """Вердикт по селектору каждого пункта. Беда — сеть, обрыв, непонятный
    ответ — пропускает все пункты, а в журнал идёт строка о ней; пункт, о
    котором модель промолчала, тоже пропущен."""
    passed = {item["selector"]: Verdict(True, "", None) for item in items}
    reply = await chat(lm, model, _request(inventory, items), logger)
    if reply.text is None or reply.finish_reason == CUT_BY_LIMIT:
        logger.warning("проверка запасного пути не состоялась — запасной путь разрешён")
        return passed
    answer = json_object(reply.text, logger, _PURPOSE)
    verdicts = answer.get("verdicts") if answer is not None else None
    if not isinstance(verdicts, list):
        log_unparseable(reply.text, logger, _PURPOSE)
        logger.warning("проверка запасного пути не разобрана — запасной путь разрешён")
        return passed
    said = {one["selector"]: _verdict(one) for one in verdicts
            if isinstance(one, dict) and str_or_none(one.get("selector")) in passed}
    return {**passed, **said}


def _verdict(one: dict) -> Verdict:
    """Отбит только явный отказ: невнятное «ok» пропускает, как и вся беда."""
    return Verdict(one.get("ok") is not False, str_or_none(one.get("reason")) or "",
                   str_or_none(one.get("field")))


def _request(inventory: list[FieldEntry], items: list[dict]) -> ChatRequest:
    fields = "\n".join(
        f"- {entry.selector} | {entry.label or 'без подписи'} | {entry.kind}"
        + (f" | варианты: {', '.join(entry.options)}" if entry.options else "")
        for entry in inventory
    )
    fallbacks = "\n".join(
        f"- {item['selector']} | {item['value']} | обоснование: {item['fallback_reason']}"
        for item in items
    )
    user = external_block(
        f"Опись полей страницы:\n{fields}\n\nПункты в общее поле:\n{fallbacks}",
        "данные для проверки",
        'Верни JSON {"verdicts": [...]}.',
    )
    return ChatRequest(
        purpose=_PURPOSE,
        messages=[{"role": "system", "content": FILL_REVIEW_PROMPT},
                  {"role": "user", "content": user}],
        max_tokens=MAX_FILL_REVIEW_TOKENS,
    )
