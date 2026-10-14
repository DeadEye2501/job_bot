"""Арбитр: та же это компания, что уже заведена, или новая."""


import logging

import httpx

from adapters.lm_chat import CUT_BY_LIMIT, ChatRequest, chat
from backend.llm.answers import ONLY_JSON, TRUNCATED_TROUBLE, json_object, log_unparseable
from backend.llm.external import external_block
from backend.llm.rules import AGGREGATOR_HOSTS_LINE
from backend.incoming import str_list

logger = logging.getLogger(__name__)


# Бюджет токенов на решение о склейке компаний. Прежних двухсот пятидесяти
# рассуждающей модели хватало только на размышление, и до номера со ссылкой на
# кандидата дело не доходило — обрыв же здесь вырождается в «завести новую».
MAX_DEDUPE_TOKENS = 1200


DEDUPE_COMPANY_PROMPT = """Ты определяешь, является ли распарсенная из вакансии компания одной из существующих в БД, или это новая компания.

Разобранное имя, сайт и список кандидатов придут отдельным сообщением как данные.

Жёсткие правила (применяй строго):
1. Указаны оба сайта и их домены разные — это РАЗНЫЕ компании, выбери null. Домен сравнивается без поддоменов (www., careers., jobs., hr.).
   Ссылки на агрегаторы вакансий, мессенджеры и соцсети ({AGGREGATOR_HOSTS} и т.п.) — не корпоративный сайт, а ссылка на канал или профиль: для правила 1 такой сайт считается не указанным.
2. Отдельный бренд, под которым нанимают от своего имени (своё название в вакансии, свой сайт), — отдельная компания, даже при общем владельце. Продукт, сервис или команда, названные внутри имени компании («X Pay», «команда Y в X»), — та же компания. Примеры: «X» и «X Bank» со своим сайтом — разные; «X» и «X Cloud» как продукт X — одна.
3. Транслитерация имени между алфавитами (кириллица, латиница, иероглифы и т.п.) — ОДНА компания. Примеры: «Компания Икс» / «Kompaniya Iks»; Huawei / 华为.
4. Бренд и юридическое название — ОДНА компания; юр-формы (LLC, GmbH, S.A., SARL, Inc., N.V., Ltd., ООО, ПАО, АО) при сравнении не учитываются. Примеры: «X» / «X, Inc.» / ООО «X»; «Y» / «Y GmbH».
5. Ребрендинг — ОДНА компания: «X» → «Z», если прежнее имя названо среди прозвищ кандидата.
6. В случае любых сомнений выбирай null. Лучше создать дубликат (поправимо вручную), чем неверно склеить две разные компании (необратимо).

Верни JSON-объект такого вида:
{"matched_id": <id одного из кандидатов или null>, "reasoning": "<краткое пояснение НА ТОМ ЖЕ ЯЗЫКЕ, что и parsed_name (русское имя → русский reasoning; English/Latin name → English reasoning), 1-2 предложения>"}
"""
# Местодержателем, как у соседнего наставления разбора: `format` здесь не
# годится вовсе — образец ответа выше написан фигурными скобками, и они
# читались бы как поля подстановки.
DEDUPE_COMPANY_PROMPT = (
    DEDUPE_COMPANY_PROMPT.replace("{AGGREGATOR_HOSTS}", AGGREGATOR_HOSTS_LINE)
    + ONLY_JSON
)


def _shown_candidates(
    parsed_name: str, parsed_website: str | None, candidates: list
) -> str:
    """Разобранное и кандидаты одним куском данных — тем, что увидит арбитр.

    Порядковых номеров у списка нет нарочно: при пяти кандидатах модель путала
    «третий» с `id=3` и приклеивала вакансию к чужой компании.
    """
    cand_lines = []
    for c in candidates:
        aliases = ", ".join(str_list(c.aliases)) or "—"
        cand_lines.append(
            f'id={c.id}, name="{c.name}", aliases=[{aliases}], '
            f'website="{c.website or "—"}"'
        )
    return (
        f'Распарсено из вакансии:\n- name: "{parsed_name}"\n'
        f'- website: "{parsed_website or "—"}"\n\n'
        "Кандидаты в БД:\n" + "\n".join(cand_lines)
    )


def _dedupe_request(
    parsed_name: str, parsed_website: str | None, candidates: list
) -> ChatRequest:
    """Что спросить у модели: разобранное имя и все кандидаты списком.

    Прозвища кандидатов идут в тот же список: компания, названная в
    вакансии прозвищем, иначе не свелась бы со своей строкой.

    Имя, сайт и кандидаты уезжают отдельным сообщением, обёрнутые как данные, а
    не вклеиваются в наставление: всё это пришло из чужих постов, а вклеенное в
    правила читается моделью как её собственные правила. Цена ошибки тут выше,
    чем у соседей — арбитр решает, к какой компании приклеить вакансию, и
    склеивание необратимо. Заслон «номер должен быть из списка» не спасает:
    подсказывают как раз номер из списка.
    """
    user_content = external_block(
        _shown_candidates(parsed_name, parsed_website, candidates),
        "разобранное имя компании и кандидаты из базы",
        "Реши по правилам system prompt'а.",
    )
    return ChatRequest(
        purpose="dedupe_company",
        messages=[
            {"role": "system", "content": DEDUPE_COMPANY_PROMPT},
            {"role": "user", "content": user_content},
        ],
        max_tokens=MAX_DEDUPE_TOKENS,
    )


def _matched_id(answer: str) -> tuple[int | None, str | None]:
    """Разобрать ответ модели: номер сведённой строки и пояснение.

    Непригодный номер не роняет сведение, а вырождает его в «завести
    новую»: неверно склеенные компании поправить нельзя, лишнюю — можно.
    """
    obj = json_object(answer, logger, "dedupe_company")
    if obj is None:
        log_unparseable(answer, logger, "dedupe_company")
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


async def dedupe_company_with_llm(
    client: httpx.AsyncClient,
    model: str,
    *,
    parsed_name: str,
    parsed_website: str | None,
    candidates: list,
) -> tuple[int | None, str | None]:
    """Номер сведённой компании и пояснение к решению; пусто — не свелось.

    Номер приходит от модели и проверяется здесь только на целость: что он из
    показанного списка, знает уже зовущий (`repository/companies_matching`), и
    чужой номер он превращает в «завести новую». Так же вырождается и всякая
    беда — молчание провайдера, обрыв ответа, номер не числом: лишняя строка
    поправима руками, а неверно склеенные компании — нет.
    """
    logger.debug(
        "dedupe_company: parsed=%r website=%r candidates=%d",
        parsed_name,
        parsed_website,
        len(candidates),
    )
    if not candidates:
        return None, "no_candidates"
    reply = await chat(
        client,
        model,
        _dedupe_request(parsed_name, parsed_website, candidates),
        logger,
    )
    if reply.text is None:
        # Причина уходит в решение и доходит до человека: её показывают в
        # разборе сведения компаний, поэтому она остаётся строкой провайдера,
        # а не сводится к общему «не получилось».
        return None, reply.error
    if reply.finish_reason == CUT_BY_LIMIT:
        # Обрыв решением о склейке быть не может: сведённые компании обратно
        # не разводятся, а лишняя заведённая запись поправима.
        logger.warning("dedupe_company: ответ оборван, свожу как «не та»")
        return None, TRUNCATED_TROUBLE
    return _matched_id(reply.text)
