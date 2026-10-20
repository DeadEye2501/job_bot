"""Повторный разбор уже заведённой вакансии.

Зовут его двое, и предмет у обоих один — строка, которая уже лежит в базе.
Кнопка «Прогнать заново» разбирает её по просьбе человека; подбор
недоразобранного — те, у которых приговора ещё нет вовсе. Разница между ними
в одном: за какой текст зовущий ручается, и потому оба живут здесь, а не
порознь.
"""

import logging
from dataclasses import dataclass
from datetime import timedelta
from typing import Literal

from sqlalchemy import select

from backend.agent.stops import RUN_STOPPERS
from backend.flows import embeddings, handover, linked_article
from backend.flows.handover import Intake
from backend.models import TelegramChannel
from backend.models import Vacancy, VacancyStatus
from backend.repository.channels import list_named_channels
from backend.telegram_lookup import say_flood_wait
from backend.telegram_time import utc_now
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


async def _post_text(msg, where: str, vacancy_id: int) -> tuple[str, bool] | None:
    """Перечитанный пост, как его читает приём; пусто — текста нет, и это в журнал.

    Что делать с недобравшим, здесь не решают: оба ответа принадлежат зовущему.
    """
    fresh = await linked_article.post_full_text(msg)
    if fresh is None:
        logger.info(
            "rerun: vacancy %d fetched msg %s but text is empty (media-only?), keeping cached raw_text",
            vacancy_id, where,
        )
    return fresh


async def _fetch_fresh_text(
    pipeline, channel_username: str, msg_id: int | None, vacancy_id: int
):
    """Перечитать исходный пост; пусто — перечитать не вышло.

    Недоступность поста тут не беда, а обычный исход: канал мог закрыться,
    пост — быть удалённым, Telegram — попросить подождать. Во всех этих
    случаях зовущему остаётся то, что уже лежит в базе.
    """
    from pyrogram.errors import FloodWait

    if not channel_username or msg_id is None:
        return None
    where = f"@{channel_username}/{msg_id}"
    try:
        msg = await pipeline.client.get_messages(
            channel_username, message_ids=msg_id
        )
        if msg is None or getattr(msg, "empty", False):
            logger.info(
                "rerun: vacancy %d msg %s not available (deleted/empty), keeping cached raw_text",
                vacancy_id, where,
            )
            return None
        return await _post_text(msg, where, vacancy_id)
    except FloodWait as e:
        say_flood_wait(logger, f"rerun: vacancy {vacancy_id} {where}, keeping cached raw_text", e)
    except Exception:
        logger.exception(
            "rerun: vacancy %d failed to refetch %s, keeping cached raw_text",
            vacancy_id, where,
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
    """Пересчитать отпечаток вакансии под текст, с которым идёт разбор.

    Зовут отсюда двое, и обоим текст объявления меняется под руками: прогон
    заново перечитывает пост, который могли отредактировать за месяцы, а
    подбор недоразобранного дочитывает статью, которой на приёме не было.
    Отпечаток, оставшийся от прежнего текста, отсеивал бы будущие похожие
    посты по тому, чего в объявлении уже нет.

    Приходит сюда тот же текст, с каким идёт разбор, — тем же он считается и
    на приёме, иначе строка уходила бы из общего счёта, и её же перепост
    перестал бы с ней сходиться. Кэш отсева правится следом за строкой — он
    живёт в памяти и сам из базы не перечитывается.

    Молчание поставщика отпечатков работу зовущего не отменяет: он отдельный
    от чат-модели и лежит порознь с ней, а разбор — главное, ради чего сюда и
    шли. Вектор в этом случае остаётся прежним до следующего раза.

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


async def _reread_and_store(
    pipeline, vacancy_id: int, was: str, where: tuple[str, int | None]
):
    """Перечитанный пост двумя значениями; пусто — перечитать не вышло.

    Целый текст тут же и записывается, пока он на руках: разбор идёт минутами,
    и оборвись он посреди, сохранённый остался бы от прошлого раза. Недобравший
    не записывается никогда — в сохранённом статья уже может быть, и переписать
    его постом без неё значит потерять требования.

    Толковать недобор здесь нечем: у двух зовущих он значит разное.
    """
    username, msg_id = where
    fresh = await _fetch_fresh_text(pipeline, username, msg_id, vacancy_id)
    if fresh is None:
        return None
    text, whole = fresh
    if whole and text != was:
        await _store(pipeline, vacancy_id, raw_text=text)
    return text, whole


async def _text_to_parse(pipeline, origin: "_Origin", vacancy_id: int) -> str:
    """Текст, с которым идёт прогон: перечитанный пост или сохранённый.

    Недобравший перечитанный текст здесь хуже сохранённого, а не лучше: в
    сохранённом статья уже есть, и переписать его постом без неё — значит
    потерять требования, по которым вакансию и отбирали.
    """
    fresh = await _reread_and_store(
        pipeline, vacancy_id, origin.raw_text,
        (origin.channel_username, origin.msg_id),
    )
    if fresh is None:
        return origin.raw_text
    text, whole = fresh
    if whole:
        return text
    logger.info(
        "rerun: vacancy %d linked article not available, keeping cached raw_text",
        vacancy_id,
    )
    return origin.raw_text


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
    тому же тексту, что уходит в разбор.

    Исходов четыре, а не «да/нет»: окно говорит о них разное, и «нет вакансии
    или пустой текст» на месте молчащей модели посылало бы человека искать
    запись, которая на месте.
    """
    origin = await _vacancy_origin(pipeline, vacancy_id)
    if origin is None:
        return "missing"
    text = await _text_to_parse(pipeline, origin, vacancy_id)
    if not text:
        logger.warning("rerun: vacancy %d has empty raw_text", vacancy_id)
        return "no_text"
    await pipeline.reload_resources()
    if not await handover.judge_and_hand_over(
        pipeline, vacancy_id, text, Intake(channel=origin.channel_username, allow_delete=False)
    ):
        # Разбор не дошёл до конца по одной из двух причин, и человеку они
        # говорят разное: модель не ответила — поднимать модель, строки не
        # стало — искать нечего. Разбор идёт минутами, и выбросить вакансию
        # из окна за это время успевают.
        if await _vacancy_origin(pipeline, vacancy_id) is None:
            return "missing"
        return "llm"
    await _refresh_embedding(pipeline, vacancy_id, text)
    await _note_rerun(pipeline, vacancy_id, origin)
    # Вторая весть за прогон: первую шлёт сам разбор, но строка истории и
    # отпечаток ложатся уже после неё, и карточка перечитала бы себя без них.
    pipeline.fire_vacancies_changed()
    return "ok"


async def _orphan_rows(pipeline) -> list:
    """Вакансии, заведённые, но так и не разобранные, старые первыми.

    Ник канала и номер поста берутся вместе с текстом: по ним объявление
    перечитывают заново. Ник — внешним соединением: канал могли снести, а
    вакансия от этого недоразобранной быть не перестаёт.
    """
    async with pipeline.session_factory() as session:
        return (
            await session.execute(
                select(
                    Vacancy.id,
                    Vacancy.raw_text,
                    Vacancy.source_msg_id,
                    Vacancy.created_at,
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


RECOVERED_PER_TURN = 10
"""Сколько недоразобранных строк подбирают за один оборот цикла.

Подбор идёт перед обходом каналов, и каждая строка стоит похода в Telegram и
до трёх обращений к чужому сайту со сроком ожидания в двадцать секунд.
Накопившаяся сотня отложила бы свежие объявления на часы, а отметки каналов за
это время уехали бы дальше. Остаток дождётся следующего оборота: строки идут
старыми вперёд, и ни одна не пропускается насовсем.
"""

LONGEST_WAIT = timedelta(days=1)
"""Сколько объявление ждёт статью, прежде чем его осудят по тому, что есть.

Срок нужен затем, чтобы ожидание вообще кончалось. Отличить «сайт лежит до
утра» от «сайт закрылся от нас навсегда» по одному отказу нельзя: и защита от
ботов, и умерший домен, и оборванная сеть приходят одинаковой бедой. Без срока
такая строка осталась бы невидимой до конца своих дней — ни в списке, ни в
отказах, нигде.

Сутки, потому что перебои у Telegraph идут минутами, а починка домена — часами;
объявление живёт дольше, и день ожидания ему не в убыток.

Считаются они по часам, а тикают по оборотам: подбор недоразобранного зовётся
с полного обхода каналов, а тот идёт только в режиме «Полный». Простоявший
неделю в «Только ЛС» бот отсудит переждавшие строки первым же обходом — новых
постов за это время он тоже не читал.
"""


def _wait_is_over(created_at) -> bool:
    """Ждало ли объявление статьи дольше срока.

    Сравнение наивное, по UTC — тот же уговор, что у срока молчания HR;
    держит его `telegram_time.utc_now`.
    """
    if created_at is None:
        return True
    return utc_now() - created_at >= LONGEST_WAIT


async def _text_to_judge_by(pipeline, row) -> tuple[str, bool] | None:
    """Текст, по которому судить недоразобранную строку, и можно ли удалять.

    Ссылок на статью в тексте нет — ждать нечего и перечитывать незачем:
    объявление собрано целиком, и непригодное можно убирать.

    Иначе пост перечитывается: только так видно, собралась ли наконец статья,
    которой не хватило на приёме. Собралась — судим по свежему тексту, и
    непригодную строку опять же можно убирать: полнее он уже не станет.

    Не собралась — пусто в ответ, строка ждёт дальше. Сюда же приходит и
    неперечитавшийся пост: просьба Telegram подождать проходит так же, как
    лежащий сайт, а по одному отказу их всё равно не различить.

    Ждать не бесконечно: прождавшую дольше `LONGEST_WAIT` судят по
    сохранённому, но удалять по нему не дают — целым он так и не собрался.
    """
    if not linked_article.article_urls(row.raw_text):
        return row.raw_text, True
    fresh = await _reread_and_store(
        pipeline, row.id, row.raw_text, (row.username or "", row.source_msg_id)
    )
    if fresh is not None:
        text, whole = fresh
        if whole:
            return text, True
    return (row.raw_text, False) if _wait_is_over(row.created_at) else None


async def _recover_one(pipeline, row) -> bool:
    """Дочитать и разобрать одну недоразобранную строку; сказать, разобрали ли.

    Отпечаток пересчитывается вместе с разбором: на приёме его посчитали по
    одной шапке со ссылкой — статьи тогда не было, — а теперь она дочитана, и
    в отсеве повторов строка так и осталась бы шапкой. Своё же объявление,
    пришедшее из соседнего канала уже со статьёй, с ней бы не сошлось и
    завелось второй строкой.

    Заведённую человеком подбор дочитывает, но откликателю не отдаёт
    (`handover.orphan_intake`).
    """
    judged = await _text_to_judge_by(pipeline, row)
    if judged is None:
        logger.info("recover: vacancy %d ждёт дочитывания статьи", row.id)
        return False
    text, allow_delete = judged
    intake = await handover.orphan_intake(
        pipeline, row.id, Intake(channel=row.username or "", allow_delete=allow_delete)
    )
    if not await handover.judge_and_hand_over(pipeline, row.id, text, intake):
        return False
    await _refresh_embedding(pipeline, row.id, text)
    return True


async def recover_orphan_vacancies(pipeline) -> int:
    """Подобрать строки, заведённые, но так и не разобранные.

    Недоразобранной строка остаётся по двум причинам: работу оборвали между
    записью строки и записью разбора, или статья по ссылке не пришла и
    приговор был отложен до полного текста. Обе лечатся одинаково — пост
    перечитывается заново (`_text_to_judge_by`), и что из этого вышло, решает
    судьбу строки: дочитанную судят с правом убрать непригодную, ждущую
    оставляют ждать.

    Идёт на каждом полном обороте, до обхода каналов: статья возвращается
    посреди рабочего дня, а ждущей строки человек не видит вовсе. За оборот
    берётся не больше `RECOVERED_PER_TURN`, старые первыми.

    Отвечает, сколько строк разобрано: ждущие дальше и те, на которых разбор
    сдался, в счёт не идут.
    """
    await pipeline.reload_resources()
    rows = await _orphan_rows(pipeline)
    if not rows:
        return 0
    logger.info("recovering %d orphan vacancy/vacancies", len(rows))
    taken = rows[:RECOVERED_PER_TURN]
    processed = 0
    for idx, r in enumerate(taken, start=1):
        pipeline.emit_progress(
            "recover", "Разбор отложенных", idx - 1, len(taken)
        )
        if not r.raw_text:
            continue
        try:
            if await _recover_one(pipeline, r):
                processed += 1
        except RUN_STOPPERS:
            raise
        except Exception:
            logger.exception(
                "recover: vacancy %d parse failed", r.id
            )
    # Clear the recovery bar once done so the next stage's progress
    # doesn't inherit the leftover count (mirrors poll_active_channels).
    pipeline.emit_progress("recover", "", 0, 0)
    logger.info(
        "recovered %d/%d orphan vacancy/vacancies (waiting: %d)",
        processed, len(taken), len(rows) - len(taken),
    )
    return processed
