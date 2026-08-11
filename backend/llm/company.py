"""Арбитр: та же это компания, что уже заведена, или новая."""


import logging

import httpx

from adapters.lm_studio import ChatRequest, chat
from backend.llm.answers import json_object

logger = logging.getLogger(__name__)


DEDUPE_COMPANY_PROMPT = """Ты определяешь, является ли распарсенная из вакансии компания одной из существующих в БД, или это новая компания.

Распарсено из вакансии:
- name: "{parsed_name}"
- website: "{parsed_website}"

Кандидаты в БД:
{candidates_block}

Жёсткие правила (применяй строго):
1. Если у компаний указаны ОБА websites и хосты разные (без учёта www.) — это РАЗНЫЕ компании, выбери для них null.
   ВАЖНО: ссылки на агрегаторы вакансий, мессенджеры и соцсети (t.me/..., telegram.me/..., linkedin.com/..., x.com/..., twitter.com/..., instagram.com/..., facebook.com/..., vk.com/..., github.com/..., medium.com/..., behance.net/..., dribbble.com/..., xing.com/..., hh.ru/..., habr.com/..., getmatch.ru/... и т.п.) — это НЕ корпоративный сайт, а ссылка на канал/профиль. Обращайся с такими URL'ами как с «website не указан» при применении правила 1.
2. Subsidiary'и и дочерние юрлица (отдельные юридические лица под общим брендом или материнской компанией) — это РАЗНЫЕ компании. Примеры:
   - Alphabet (материнская) и Google LLC (дочка); Alphabet и Waymo LLC; Alphabet и Verily;
   - Microsoft и LinkedIn Corp.; Microsoft и GitHub, Inc.; Microsoft и ZeniMax Media;
   - Yandex и Yandex.Pay; Сбер и СберТех; МТС и МТС-Банк; Тинькофф и Тинькофф Инвестиции.
   ВАЖНО — НЕ путать с этим:
   - Внутренние подразделения / продукты / сервисы внутри ОДНОГО юрлица (Amazon и AWS, Apple и iCloud, Microsoft и Azure, Stripe и Stripe Atlas, Stripe и Stripe Connect) — это ОДНА компания, а не две.
   - Платформы внутри одной материнской компании, которые в публичной речи звучат как отдельные бренды, но юридически принадлежат одному и тому же ЛК (Google и YouTube, Meta и Instagram, Meta и WhatsApp) — для целей дедупа считаем их ОДНОЙ компанией, чтобы не плодить лишние карточки. Если пост явно про вакансию «в Instagram-команду внутри Meta» — это Meta.
3. Транслитерация имени между разными алфавитами (кириллица/латиница/иероглифы и т.п.) — это ОДНА компания. Примеры:
   - МТС / MTS / MTC; Сбер / Sber; Яндекс / Yandex; Тинькофф / Tinkoff;
   - Huawei / 华为; Toyota / トヨタ; Hyundai / 현대.
4. Бренд и юридическое название — это ОДНА компания. Сюда же относятся юр-формы (LLC, GmbH, S.A., SARL, Inc., N.V., Ltd., Pty Ltd, ООО, ПАО, АО) — игнорируй их при сравнении. Примеры:
   - Stripe / Stripe, Inc.; SAP / SAP SE; Bosch / Robert Bosch GmbH; Alphabet / Google / Google LLC;
   - Сбер / Сбербанк / ПАО Сбербанк; Яндекс / Яндекс.Технологии / Yandex N.V.
5. Ребрендинг под одной материнской компанией — это ОДНА компания, если речь идёт о замене одного публичного бренда на другой (а не о новой дочке). Примеры: Facebook → Meta (одна компания), Twitter → X (одна компания).
6. В случае любых сомнений выбирай null. Лучше создать дубликат (поправимо вручную), чем неверно склеить две разные компании (необратимо).

Верни ТОЛЬКО JSON-объект без обрамлений:
{{"matched_id": <id одного из кандидатов или null>, "reasoning": "<краткое пояснение НА ТОМ ЖЕ ЯЗЫКЕ, что и parsed_name (русское имя → русский reasoning; English/Latin name → English reasoning), 1-2 предложения>"}}
"""


async def dedupe_company_with_llm(
    client: httpx.AsyncClient,
    model: str,
    *,
    parsed_name: str,
    parsed_website: str | None,
    candidates: list,
) -> tuple[int | None, str | None]:
    """Возвращает (matched_id, reasoning). matched_id — id одной из
    компаний-кандидатов, либо None, если LLM решил, что подходящей нет
    (или произошла техническая ошибка — вырождаемся в «создать новую»,
    чтобы не блокировать пайплайн).
    """
    logger.debug(
        "dedupe_company: parsed=%r website=%r candidates=%d",
        parsed_name,
        parsed_website,
        len(candidates),
    )
    if not candidates:
        return None, "no_candidates"
    cand_lines = []
    for i, c in enumerate(candidates, start=1):
        aliases = ", ".join(c.aliases or []) or "—"
        cand_lines.append(
            f'{i}. id={c.id}, name="{c.name}", aliases=[{aliases}], '
            f'website="{c.website or "—"}"'
        )
    prompt = DEDUPE_COMPANY_PROMPT.format(
        parsed_name=parsed_name,
        parsed_website=parsed_website or "—",
        candidates_block="\n".join(cand_lines),
    )
    reply = await chat(
        client,
        model,
        ChatRequest(
            purpose="dedupe_company",
            messages=[
                {"role": "system", "content": prompt},
            ],
            max_tokens=250,
        ),
        logger,
    )
    if reply.text is None:
        # Причина уходит в решение и доходит до человека: её показывают в
        # разборе сведения компаний, поэтому она остаётся строкой провайдера,
        # а не сводится к общему «не получилось».
        return None, reply.error
    answer = reply.text

    obj = json_object(answer, logger, "dedupe_company")
    if obj is None:
        logger.warning(
            "dedupe_company: ответ модели не даёт объекта %r", answer[:200]
        )
        return None, f"unparseable_json: {answer[:120]}"

    matched_id = obj.get("matched_id")
    reasoning = obj.get("reasoning") or ""

    if matched_id is None:
        return None, reasoning
    try:
        return int(matched_id), reasoning
    except (TypeError, ValueError):
        logger.warning(
            "dedupe_company: invalid matched_id %r in LLM response",
            matched_id,
        )
        return None, f"invalid_id: {matched_id!r}"
