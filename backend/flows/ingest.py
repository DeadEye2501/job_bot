"""Приём объявления из канала с отсевом перепостов."""

import logging

from sqlalchemy.exc import IntegrityError

from backend.flows import handover, intake, linked_article
from backend.flows.handover import Intake
from backend.models import Vacancy
from backend.payloads import ChannelPost
from backend.telegram_time import tg_moment

from backend.flows import sameness

logger = logging.getLogger(__name__)


async def _post_match(pipeline, post: ChannelPost) -> sameness.Match | None:
    """Отпечаток поста и похожая заведённая вакансия; пусто — модель отпечатков не дала.

    Пост без отпечатка пропускается, курсор идёт дальше, и следующий проход по
    каналу его не увидит — но это дешевле, чем встать на одном посте.

    Считается по тому же тексту, что уходит в разбор и ложится в строку: с
    адресами ссылок и с дописанными статьями. В таких объявлениях статья и
    есть содержание — у поста-шапки своего текста нет вовсе, — и по одной
    шапке два разных объявления неразличимы: отпечаток объявил бы второе
    повтором первого, и оно пропало бы молча.

    Плата за это видна на посте, чья статья не собралась: отпечаток у него от
    шапки, а у того же поста, перепощенного с собравшейся статьёй, — от
    полного текста, и сойтись они могут не всегда. Тогда вместо дочитывания
    заводится вторая строка. Подбор недоразобранного это окно закрывает —
    дочитав статью, он пересчитывает отпечаток, — но пока строка ждёт, оно
    открыто.
    """
    return await sameness.known_or_new(
        pipeline, post.text, f"[@{post.channel_username}] {post.msg.id}"
    )


def _waits_to_be_read_out(vacancy_id: int, post: ChannelPost) -> None:
    """Отметить в журнале, что приговор объявлению отложен до полного текста."""
    logger.info(
        "[@%s] %d vacancy %d ждёт дочитывания статьи, приговора нет",
        post.channel_username, post.msg.id, vacancy_id,
    )


async def _resume_or_skip(
    pipeline, match: sameness.Match, post: ChannelPost, whole: bool
) -> None:
    """Что делать с постом, похожим на уже заведённую вакансию.

    Похожая строка бывает двух родов: настоящий перепост — такой
    пропускается, — и вакансия, брошенная недоразобранной на прошлом
    прогоне. Вторую здесь и дорзабирают: иначе она пропускалась бы вечно.
    """
    similar_id = match.vacancy_id
    if match.kind == "parsed":
        logger.info(
            "[@%s] %d duplicate of vacancy %d, skipping",
            post.channel_username, post.msg.id, similar_id,
        )
        return
    if not whole:
        _waits_to_be_read_out(similar_id, post)
        return
    logger.info(
        "[@%s] %d matched orphan vacancy %d, finishing parse",
        post.channel_username, post.msg.id, similar_id,
    )
    # Брошенная строка могла прийти из другого канала (перепост): разбираем
    # по тексту нынешнего поста и его каналу, а кладём в ту строку.
    # Совпадение отпечатков ручается, что тексты почти дословны.
    intake = await handover.orphan_intake(
        pipeline, similar_id, Intake(channel=post.channel_username)
    )
    await handover.judge_and_hand_over(pipeline, similar_id, post.text, intake)


async def ingest_post(
    pipeline, channel_id: int, channel_username: str, msg
) -> None:
    # Cursor advance'ится в `poll_channel` (батчами), не здесь.
    if msg.service is not None or msg.poll is not None:
        return
    read = await linked_article.post_full_text(msg)
    if read is None:
        return
    text, whole = read
    post = ChannelPost(channel_id, channel_username, msg, text)
    match = await _post_match(pipeline, post)
    if match is None:
        return
    if match.kind != "new":
        await _resume_or_skip(pipeline, match, post, whole)
        return

    new_vacancy_id = await save_new_vacancy(pipeline, post, match.embedding)
    if new_vacancy_id is None:
        return
    # Сперва полный текст, потом приговор. Пока статья не пришла по причине,
    # которая пройдёт, разбору видна одна шапка со ссылкой: он сочиняет по ней
    # описание, а оценщик судит о том, чего не видел. Строка всё равно
    # заводится — курсор канала уже уехал, и второй раз этот пост не прочтут, —
    # но остаётся недоразобранной, и подбор недоразобранного дочитает её.
    if not whole:
        _waits_to_be_read_out(new_vacancy_id, post)
        return
    await handover.judge_and_hand_over(
        pipeline, new_vacancy_id, text, Intake(channel=channel_username)
    )


def _vacancy_row(post: ChannelPost, embedding: list[float]) -> Vacancy:
    """Строка вакансии из поста канала — ещё не разобранная.

    Ссылка собирается из ника и номера поста: по ней человек открывает
    исходное объявление прямо из карточки.
    """
    return Vacancy(
        source_channel_id=post.channel_id,
        source_msg_id=post.msg.id,
        raw_text=post.text,
        embedding=embedding,
        source_url=f"https://t.me/{post.channel_username}/{post.msg.id}",
        posted_at=tg_moment(post.msg.date),
    )


async def save_new_vacancy(
    pipeline,
    post: ChannelPost,
    embedding: list[float],
) -> int | None:
    try:
        return await intake.save_new_vacancy(
            pipeline,
            _vacancy_row(post, embedding),
            "ingested",
            {"channel": post.channel_username, "msg_id": post.msg.id},
        )
    except IntegrityError as trouble:
        # Целостность нарушается тут по-разному, и какое правило сработало —
        # говорит сама беда: обычное дело это тот же пост, заведённый
        # встречным обходом (`uq_vacancy_source`), но сюда же приходит и
        # ссылка на канал, которого уже нет. Своя эта беда только посту:
        # у вставленного текста нет ни канала, ни номера поста, и столкнуться
        # с уникальностью источника ему нечем.
        logger.info(
            "[@%s] %d строка не завелась, целостность нарушена: %s",
            post.channel_username,
            post.msg.id,
            trouble.orig,
        )
        return None
