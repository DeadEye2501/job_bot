"""Повторный разбор уже заведённой вакансии."""

import logging
from dataclasses import dataclass
from typing import Literal

from sqlalchemy import select

from backend.flows import embeddings, linked_article, parse
from backend.message_text import extract_post_text, extract_text
from backend.models import TelegramChannel
from backend.models import Vacancy, VacancyStatus
from backend.repository.channels import list_named_channels
from backend.repository.vacancy_status import (
    last_status_history_id,
    record_rerun,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class _Origin:
    """Откуда вакансия пришла и чем была до прогона.

    Статус снимается вместе с текстом: разбор поставит свой, как у только что
    заведённой строки, и сравнить его будет уже не с чем. Рядом — последняя
    строка истории: по ней потом видно, объяснил ли кто-то смену статуса, пока
    шёл прогон.
    """

    raw_text: str
    channel_username: str
    msg_id: int | None
    status: VacancyStatus
    history_id: int | None


async def _vacancy_origin(pipeline, vacancy_id: int) -> _Origin | None:
    """Что известно о происхождении вакансии; пусто — вакансии нет."""
    async with pipeline.session_factory() as session:
        v = await session.get(Vacancy, vacancy_id)
        if v is None:
            logger.warning("rerun: vacancy %d missing", vacancy_id)
            return None
        channel_username = ""
        if v.source_channel_id is not None:
            named = await list_named_channels(
                session, ids=[v.source_channel_id]
            )
            if named:
                channel_username = named[0].username
        # Снимок собирается внутри сессии нарочно: за её пределами чтение
        # полей строки уже не чтение, а поведение сессии.
        return _Origin(
            raw_text=v.raw_text or "",
            channel_username=channel_username,
            msg_id=v.source_msg_id,
            status=v.status,
            history_id=await last_status_history_id(session, vacancy_id),
        )


async def _post_text(msg, origin: _Origin, vacancy_id: int) -> tuple[str, str] | None:
    """Перечитанный пост двумя текстами; пусто — брать сохранённый.

    Первый — со статьями и адресами ссылок, он идёт в разбор и в строку.
    Второй — голый текст поста, он идёт в отпечаток: отпечатки сравнивают с
    посчитанными год назад, когда ни адресов, ни статей в тексте не было.

    Недобравший текст здесь хуже прежнего, а не лучше: сохранённый уже
    содержит статью, которую в эту минуту не отдали, и переписать его постом
    без неё — значит потерять требования, по которым вакансию и отбирали.
    """
    candidate = extract_post_text(msg)
    if not candidate:
        logger.info(
            "rerun: vacancy %d fetched msg @%s/%d but text is empty (media-only?), keeping cached raw_text",
            vacancy_id, origin.channel_username, origin.msg_id,
        )
        return None
    candidate, whole = await linked_article.with_linked_articles(candidate)
    if not whole:
        logger.info(
            "rerun: vacancy %d linked article not available, keeping cached raw_text",
            vacancy_id,
        )
        return None
    return candidate, extract_text(msg)


async def _fetch_fresh_text(pipeline, origin: _Origin, vacancy_id: int):
    """Перечитать исходный пост; пусто — берём сохранённый текст.

    Недоступность поста тут не беда, а обычный исход: канал мог закрыться,
    пост — быть удалённым, Telegram — попросить подождать. Во всех этих
    случаях повторный прогон идёт по тому, что уже лежит в базе.
    """
    from pyrogram.errors import FloodWait

    if not origin.channel_username or origin.msg_id is None:
        return None
    try:
        msg = await pipeline.client.get_messages(
            origin.channel_username, message_ids=origin.msg_id
        )
        if msg is None or getattr(msg, "empty", False):
            logger.info(
                "rerun: vacancy %d msg @%s/%d not available (deleted/empty), keeping cached raw_text",
                vacancy_id, origin.channel_username, origin.msg_id,
            )
            return None
        return await _post_text(msg, origin, vacancy_id)
    except FloodWait as e:
        logger.warning(
            "rerun: vacancy %d FloodWait %ss while fetching @%s/%d, keeping cached raw_text",
            vacancy_id, e.value, origin.channel_username, origin.msg_id,
        )
    except Exception:
        logger.exception(
            "rerun: vacancy %d failed to refetch @%s/%d, keeping cached raw_text",
            vacancy_id, origin.channel_username, origin.msg_id,
        )
    return None


async def _store(pipeline, vacancy_id: int, **fields) -> bool:
    """Записать поля вакансии своей короткой сделкой; `False` — строки нет.

    Своей, а не общей с разбором: и текст, и отпечаток пишутся до него, и
    оборвись разбор посреди, записанное всё равно останется. Исчезнувшая
    строка — обычный исход: её могли снести из окна, пока шёл прогон, — и
    зовущему это говорится ответом: у кэша отсева своя память, и та переживает
    снос строки.
    """
    async with pipeline.session_factory() as session:
        v = await session.get(Vacancy, vacancy_id)
        if v is None:
            return False
        for name, value in fields.items():
            setattr(v, name, value)
        await session.commit()
    return True


async def _refresh_embedding(pipeline, vacancy_id: int, text: str) -> None:
    """Пересчитать отпечаток вакансии под текст, с которым идёт прогон.

    Прогон заново — это весь путь заново, и отпечаток тоже: оставшийся от
    прежнего текста, он отсеивал бы будущие похожие посты по тому, чего в
    объявлении уже нет. Приходит сюда голый текст поста, тот же, по какому
    отпечаток считают на приёме, — иначе прогон уводил бы вакансию из общего
    счёта, и перепост переставал бы с ней сходиться. Кэш отсева правится
    следом за строкой — он живёт в памяти и сам из базы не перечитывается.

    Молчание поставщика отпечатков прогон не отменяет: он отдельный от
    чат-модели и лежит порознь с ней, а разбор — главное, ради чего кнопку и
    жали. Вектор в этом случае остаётся прежним до следующего прогона.

    Кэш правится только вслед за удавшейся записью: вакансию могли выбросить
    из окна, пока отвечала модель, и вернувшийся в кэш вектор отсеивал бы
    будущие посты как повторы строки, которой уже нет.
    """
    try:
        vector = await embeddings.embed_text(pipeline, text, f"vacancy {vacancy_id}")
    except embeddings.ProviderIsSilent:
        logger.warning(
            "rerun: vacancy %d поставщик отпечатков молчит, вектор остаётся прежним",
            vacancy_id,
        )
        return
    if vector is None:
        return
    if not await _store(pipeline, vacancy_id, embedding=vector):
        return
    pipeline.embeddings.drop(vacancy_id)
    pipeline.embeddings.append(vacancy_id, vector)


async def _note_rerun(pipeline, vacancy_id: int, origin: "_Origin") -> None:
    """Отметить в истории вакансии, что её прогнали заново."""
    async with pipeline.session_factory() as session:
        async with session.begin():
            await record_rerun(session, vacancy_id, origin.status, origin.history_id)


async def _text_to_parse(pipeline, origin: "_Origin", vacancy_id: int):
    """Текст для разбора заново и голый текст поста, если пост перечитан.

    Перечитанный текст тут же и записывается, пока он на руках: разбор идёт
    минутами, и оборвись он посреди, сохранённый текст остался бы от прошлого
    раза. Голый текст поста нужен только отпечатку, и без перечитывания его
    нет вовсе — сохранённый для этого не годится, в нём адреса и статьи.
    """
    fresh = await _fetch_fresh_text(pipeline, origin, vacancy_id)
    if fresh is None:
        return origin.raw_text, None
    text, plain = fresh
    if text != origin.raw_text:
        await _store(pipeline, vacancy_id, raw_text=text)
    return text, plain


RerunPipelineOutcome = Literal["ok", "missing", "no_text", "llm"]
"""Чем кончился повторный разбор вакансии на конвейере.

Исходы места прогона сюда не входят — см. `flows/channels.py:PollOutcome`.
"""


async def rerun_pipeline_for_vacancy(
    pipeline, vacancy_id: int
) -> RerunPipelineOutcome:
    """Разобрать заведённую вакансию заново — кнопка окна «Прогнать заново».

    Прогон идёт как над только что заведённой строкой: пост перечитывается из
    Telegram (при неудаче остаётся сохранённый текст — см. `_fetch_fresh_text`),
    навыки, отсев и анкета перечитываются, отпечаток считается заново — по
    голому тексту перечитанного поста, а не по сохранённому со статьями.

    Исходов четыре, а не «да/нет»: окно говорит о них разное, и «нет вакансии
    или пустой текст» на месте молчащей модели посылало бы человека искать
    запись, которая на месте.
    """
    origin = await _vacancy_origin(pipeline, vacancy_id)
    if origin is None:
        return "missing"
    text, plain = await _text_to_parse(pipeline, origin, vacancy_id)
    if not text:
        logger.warning("rerun: vacancy %d has empty raw_text", vacancy_id)
        return "no_text"
    await pipeline.reload_resources()
    if not await parse.parse_and_update_vacancy(
        pipeline, vacancy_id, text, origin.channel_username, allow_delete=False
    ):
        # Разбор не дошёл до конца по одной из двух причин, и человеку они
        # говорят разное: модель не ответила — поднимать модель, строки не
        # стало — искать нечего. Разбор идёт минутами, и выбросить вакансию
        # из окна за это время успевают.
        if await _vacancy_origin(pipeline, vacancy_id) is None:
            return "missing"
        return "llm"
    if plain is not None:
        await _refresh_embedding(pipeline, vacancy_id, plain)
    await _note_rerun(pipeline, vacancy_id, origin)
    # Вторая весть за прогон: первую шлёт сам разбор, но строка истории и
    # отпечаток ложатся уже после неё, и карточка перечитала бы себя без них.
    pipeline.fire_vacancies_changed()
    return "ok"


async def _orphan_rows(pipeline) -> list:
    """Вакансии, заведённые, но так и не разобранные, старые первыми.

    Ник канала берётся внешним соединением: канал могли снести, а вакансия
    от этого недоразобранной быть не перестаёт.
    """
    async with pipeline.session_factory() as session:
        return (
            await session.execute(
                select(
                    Vacancy.id,
                    Vacancy.raw_text,
                    TelegramChannel.username,
                )
                .outerjoin(
                    TelegramChannel,
                    Vacancy.source_channel_id == TelegramChannel.id,
                )
                .where(
                    Vacancy.is_parsed.is_(False),
                    Vacancy.raw_text.is_not(None),
                )
                .order_by(Vacancy.id.asc())
            )
        ).all()


async def recover_orphan_vacancies(pipeline) -> int:
    """Finish parsing rows that were ingested but never made it through
    the LLM pipeline (process killed between ``save_new_vacancy`` and
    ``parse_and_update_vacancy`` commits, or LLM call cancelled).

    Called once at startup before the polling loop kicks in, so the
    UI never shows half-built rows for long.

    Выбрасывать здесь нельзя ничего. Разбирают строку по сохранённому тексту, а
    целым ли он записан, не знает никто: пост со ссылкой ложится в базу и
    тогда, когда статья не доехала (`ingest._vacancy_row` пишет `post.text`
    независимо от целости). Снеси такую — и объявление пропадёт навсегда: пост
    второй раз не прочтут, отметка канала уехала. Пометка «не подходит»
    дождётся прогона заново, а тот статью и подберёт.

    Отвечает, сколько строк подобрано.
    """
    await pipeline.reload_resources()
    rows = await _orphan_rows(pipeline)
    if not rows:
        return 0
    logger.info("recovering %d orphan vacancy/vacancies", len(rows))
    processed = 0
    for idx, r in enumerate(rows, start=1):
        pipeline.emit_progress(
            "recover", r.username or "", idx - 1, len(rows)
        )
        text = r.raw_text or ""
        if not text:
            continue
        try:
            await parse.parse_and_update_vacancy(pipeline, 
                r.id, text, r.username or "", allow_delete=False
            )
            processed += 1
        except Exception:
            logger.exception(
                "recover: vacancy %d parse failed", r.id
            )
    # Clear the recovery bar once done so the next stage's progress
    # doesn't inherit the leftover count (mirrors poll_active_channels).
    pipeline.emit_progress("recover", "", 0, 0)
    logger.info("recovered %d/%d orphan vacancy/vacancies", processed, len(rows))
    return processed
